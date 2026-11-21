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
    reply = server.handle_owner_message("yes 1")
    assert "jarvis-ok" in reply and store.get_message(1)["status"] == "sent"
    assert "Nothing is waiting" in server.handle_owner_message("approve all")


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


def test_telegram_pairing_commands_and_buttons(env, monkeypatch):
    store, ctx, _ = env
    from jarvis import telegram as tg
    calls = []
    monkeypatch.setattr(tg, "api", lambda method, http_timeout=30, **p: calls.append((method, p)) or {})
    monkeypatch.setattr(settings, "telegram_token", "T")
    monkeypatch.setattr(settings, "telegram_chat_id", "")
    monkeypatch.setattr(settings, "whatsapp_enabled", False)
    tg.attach(store)
    code = tg.pair_code()
    texts, decisions = [], []
    bot = tg.Bot(on_text=lambda t, voice=False: texts.append(t) or "reply", on_decision=lambda i, y: decisions.append((i, y)) or "done",
                 log=lambda m: None)
    msg = lambda chat, text: {"update_id": 1, "message": {"chat": {"id": chat}, "text": text}}

    bot.handle(msg(555, "hello"))                 # not paired: ignored
    bot.handle(msg(555, "/start 000"))            # wrong code: ignored
    assert not tg.ready() and not texts
    bot.handle(msg(555, f"/start {code}"))        # right code: linked
    assert tg.ready() and tg.chat_id() == "555"
    bot.handle(msg(999, "send all my money"))     # stranger: ignored
    bot.handle(msg(555, "What's on my plate?"))
    assert texts == ["What's on my plate?"]

    # an approval request arrives with buttons; tapping Send approves it
    execute("add_contact", ctx, {"name": "Dr. Okafor", "email": "okafor@uni.edu"})
    out, _ = execute("send_whatsapp", ctx, {"to": "Dr. Okafor", "message": "hi", "reason": "x"})
    assert "switched off" in out                  # WhatsApp is off: agents are told to use e-mail
    execute("send_email", ctx, {"to": "Dr. Okafor", "subject": "Slides", "body": "Could I get the slides?",
                                "reason": "asked"})
    sent = [p for m, p in calls if m == "sendMessage" and "reply_markup" in p][-1]
    assert sent["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == "ok:1"
    bot.handle({"update_id": 2, "callback_query": {"id": "c", "data": "ok:1",
                                                    "message": {"chat": {"id": 555}, "message_id": 7}}})
    assert decisions == [(1, True)]


def test_reminder_prefers_telegram(env, monkeypatch):
    store, ctx, _ = env
    from jarvis import telegram as tg
    monkeypatch.setattr(tg, "ready", lambda: True)
    out, _ = execute("remind_me", ctx, {"text": "Gym", "at": "2030-01-01T07:00"})
    assert "scheduled" in out and store.get_message(1)["channel"] == "telegram"
