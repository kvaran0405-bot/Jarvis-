"""Offline tests for messaging policy, contacts, routines and WhatsApp approvals (no network, no API)."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from jarvis import channels as ch
from jarvis.bus import Bus
from jarvis.config import settings
from jarvis.engine import Engine
from jarvis.scheduler import Scheduler, parse_schedule
from jarvis.store import Store
from jarvis.tools import ToolContext, execute


@pytest.fixture
def env(monkeypatch):
    store = Store(":memory:")
    bus = Bus(store)
    engine = Engine(store, bus, settings)
    monkeypatch.setattr(settings, "autonomy", "approve")
    monkeypatch.setattr(settings, "whatsapp_enabled", True)
    monkeypatch.setattr(settings, "owner_whatsapp", "2348000000000")
    sent = []
    monkeypatch.setattr(ch, "send_whatsapp", lambda phone, text: sent.append((phone, text)))
    ctx = ToolContext(store, bus, settings, engine, "HERALD")
    return store, ctx, sent


def test_message_to_contact_waits_for_approval(env):
    store, ctx, sent = env
    execute("add_contact", ctx, {"name": "Mum", "phone": "+234 801 111 2222"})
    out, err = execute("send_whatsapp", ctx, {"to": "mum", "message": "Home by 8", "reason": "you asked"})
    assert not err and "approval" in out
    msg = store.list_outbox("pending")[0]
    assert msg["recipient"] == "2348011112222" and msg["recipient_name"] == "Mum"
    # owner got an approval request on their own WhatsApp, nothing went to Mum
    assert sent and sent[0][0] == "2348000000000" and "yes 1" in sent[0][1]


def test_trusted_contact_sends_immediately(env, monkeypatch):
    store, ctx, sent = env
    monkeypatch.setattr(settings, "autonomy", "trusted")
    execute("add_contact", ctx, {"name": "Tolu", "phone": "2348033333333", "trusted": True})
    out, _ = execute("send_whatsapp", ctx, {"to": "Tolu", "message": "On my way", "reason": "running late"})
    assert '"status": "sent"' in out
    assert sent == [("2348033333333", "On my way")]


def test_unknown_contact_is_an_error(env):
    _, ctx, _ = env
    out, err = execute("send_whatsapp", ctx, {"to": "Bayo", "message": "hi", "reason": "x"})
    assert err and "No contact called 'Bayo'" in out


def test_shell_always_needs_approval_even_in_full_mode(env, monkeypatch):
    store, ctx, _ = env
    monkeypatch.setattr(settings, "autonomy", "full")
    out, _ = execute("run_on_laptop", ctx, {"command": "echo hi", "reason": "test"})
    assert "approval" in out and store.list_outbox("pending")[0]["channel"] == "computer"


def test_whatsapp_yes_runs_approved_command(env, monkeypatch):
    store, ctx, _ = env
    execute("run_on_laptop", ctx, {"command": "echo jarvis-ok", "reason": "test"})
    import jarvis.server as server
    monkeypatch.setattr(server, "store", store)
    monkeypatch.setattr(server, "bus", ctx.bus)
    reply = server.handle_owner_whatsapp("yes 1")
    assert "jarvis-ok" in reply and store.get_message(1)["status"] == "sent"
    assert "Nothing is waiting" in server.handle_owner_whatsapp("approve all")


def test_scheduled_reminder_goes_out_when_due(env):
    store, ctx, sent = env
    soon = (datetime.now(settings.tz) + timedelta(minutes=5)).isoformat()
    out, _ = execute("remind_me", ctx, {"text": "Call the bank", "at": soon})
    assert "scheduled" in out
    sched = Scheduler(ctx.engine)
    assert sched.dispatch_outbox() == 0
    store.set_message(1, send_at=(datetime.now(settings.tz) - timedelta(minutes=1)).isoformat(timespec="seconds"))
    assert sched.dispatch_outbox() == 1 and "Call the bank" in sent[-1][1]


def test_parse_schedule():
    tz = ZoneInfo("UTC")
    assert parse_schedule("daily 06:00")(datetime(2026, 11, 23, 6, 1, tzinfo=tz), None)
    assert parse_schedule("weekly mon 08:00")(datetime(2026, 11, 23, 8, 0, tzinfo=tz), None)  # a Monday
    assert not parse_schedule("weekly tue 08:00")(datetime(2026, 11, 23, 8, 0, tzinfo=tz), None)
    now = datetime(2026, 11, 23, 8, 0, tzinfo=tz)
    assert parse_schedule("every 30m")(now, (now - timedelta(minutes=31)).isoformat())
    for bad in ("hourly", "every 5m", "daily 25:00", "weekly funday 08:00"):
        with pytest.raises(ValueError):
            parse_schedule(bad)


def test_routine_runs_from_tick(env):
    store, ctx, _ = env
    calls = []
    ctx.engine.run = lambda agent, prompt, **kw: calls.append((agent, prompt)) or "ok"
    execute("create_routine", ctx, {"name": "Quote", "schedule": "every 1h", "agent": "jarvis",
                                    "prompt": "Send me a quote"})
    sched = Scheduler(ctx.engine)
    sched.run_routine(store.list_routines()[0])
    assert calls[0][0] == "JARVIS" and store.list_routines()[0]["last_run"]


def test_voice_synthesis_is_cached(monkeypatch, tmp_path):
    from jarvis import voice
    monkeypatch.setattr(settings, "elevenlabs_key", "k")
    monkeypatch.setattr(voice, "CACHE", tmp_path)
    monkeypatch.setenv("JARVIS_VOICE_FRIDAY", "custom123")
    calls = []

    class Resp:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return b"ID3fake-mp3"

    def fake_urlopen(req, timeout):
        calls.append(req.full_url)
        return Resp()
    monkeypatch.setattr(voice.urllib.request, "urlopen", fake_urlopen)
    p1 = voice.synthesize("friday", "Morning, Sir.")
    p2 = voice.synthesize("FRIDAY", "Morning, Sir.")
    assert p1 == p2 and p1.read_bytes() == b"ID3fake-mp3"
    assert calls == ["https://api.elevenlabs.io/v1/text-to-speech/custom123"]  # second call came from cache
    assert voice.voice_for("JARVIS") == voice.DEFAULT_VOICES["JARVIS"]
