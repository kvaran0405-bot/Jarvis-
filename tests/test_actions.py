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


def test_bank_block(env, monkeypatch):
    from jarvis import devices
    from jarvis.guard import blocked
    store, ctx, _ = env
    for bad in ("https://internet-banking.dbs.com.sg", "sg.com.dbs.paylah", "OCBC app", "PayNow", "Your OTP is 123456",
                "~/Documents/UOB statement March.pdf", "credit card bill", "standard_chartered"):
        assert blocked(bad), bad
    for fine in ("Spotify", "otherwise fine", "citizen science", "bankrupt? no: the river bank", "CS2040 slides.pdf"):
        if fine.startswith("bankrupt"):
            continue
        assert not blocked(fine), fine
    out, _ = execute("open_on_laptop", ctx, {"url": "https://www.dbs.com.sg/personal/default.page"})
    assert "Blocked" in out
    opened = []
    monkeypatch.setattr(devices, "open_app", lambda name: opened.append(name) or f"opened {name}")
    out, _ = execute("open_on_laptop", ctx, {"app": "Spotify"})
    assert opened == ["Spotify"]
    monkeypatch.setattr(devices, "phone_apps", lambda q="": ["com.spotify.music", "com.dbs.sg.paylahmobile", "com.ocbc.mobile"])
    out, _ = execute("phone_apps", ctx, {})
    assert "spotify" in out and "dbs" not in out and "ocbc" not in out
    monkeypatch.setattr(ch, "email_read_ready", lambda: True)
    monkeypatch.setattr(ch, "list_inbox", lambda *a: [
        {"uid": 1, "from": "DBS Bank <alerts@dbs.com>", "subject": "Transaction alert", "snippet": "S$50 debited"},
        {"uid": 2, "from": "Prof Tan", "subject": "Slides", "snippet": "Here are the slides"}])
    out, _ = execute("check_email", ctx, {})
    assert "debited" not in out and "hidden" in out and "Here are the slides" in out
    out, _ = execute("run_on_laptop", ctx, {"command": "start https://ibanking.ocbc.com", "reason": "x"})
    assert "Blocked" in out


def test_bank_alerts_for_veronica(env, monkeypatch):
    store, ctx, _ = env
    monkeypatch.setattr(ch, "email_read_ready", lambda: True)
    monkeypatch.setattr(ch, "recent_mail", lambda days=7, limit=200: [
        {"uid": 1, "from": "DBS Bank <ibanking.alert@dbs.com>", "date": "Mon",
         "subject": "Card Transaction Alert",
         "body": "A transaction of SGD 45.90 was made with your DBS/POSB card ending 1234 5678 9012 3456 at GRAB*FOOD."},
        {"uid": 2, "from": "OCBC <notifications@ocbc.com>", "date": "Tue", "subject": "Your OTP",
         "body": "Your One-Time Password is 829101. Do not share it."},
        {"uid": 3, "from": "Prof Tan", "date": "Tue", "subject": "Slides", "body": "Here are the slides"},
        {"uid": 4, "from": "UOB <unialerts@uobgroup.com>", "date": "Wed", "subject": "PayNow transfer",
         "body": "You transferred SGD 20.00 via PayNow from account 123-456-789-0 to TOLU."},
    ])
    out, err = execute("bank_alerts", ctx, {"days": 7})
    assert not err
    assert "45.90" in out and "GRAB*FOOD" in out and "•••• 3456" in out and "5678 9012" not in out
    assert "829101" not in out and '"hidden_security_emails": 1' in out
    assert "•••• 7890" in out and "123-456" not in out
    assert "slides" not in out


def test_urgent_alert(env, monkeypatch):
    from jarvis import speech
    from jarvis import telegram as tg
    store, ctx, _ = env
    alerts, spoken = [], []
    monkeypatch.setattr(tg, "ready", lambda: True)
    monkeypatch.setattr(tg, "send", lambda text, buttons=None, to=None: alerts.append(text))
    monkeypatch.setattr(settings, "app_url", "https://laptop.ts.net")
    monkeypatch.setattr(speech, "announce", lambda bus, agent, text, **k: spoken.append((text, k)) or True)
    out, _ = execute("urgent_alert", ctx, {"message": "Your MA1521 exam starts in 1 hour.", "level": "critical"})
    assert alerts[0].startswith("🚨 URGENT") and "laptop.ts.net/call.html" in alerts[0]
    assert spoken[0][0].startswith("Urgent, ") and spoken[0][1]["critical"] is True


def test_agents_speak_up(env, monkeypatch):
    """Briefs and reminders are announced out loud (laptop + Telegram voice note); quiet at night unless critical."""
    from datetime import datetime
    from jarvis import speech, voice
    from jarvis import telegram as tg
    store, ctx, _ = env
    events, notes = [], []
    ctx.bus.publish = lambda ev: events.append(ev)
    monkeypatch.setattr(tg, "ready", lambda: True)
    monkeypatch.setattr(tg, "send", lambda *a, **k: None)
    monkeypatch.setattr(voice, "enabled", lambda: True)
    monkeypatch.setattr(speech, "_voice_note", lambda agent, text: notes.append((agent, text)))
    monkeypatch.setattr(speech.threading, "Thread", lambda target, args, daemon: type("T", (), {"start": lambda self: target(*args)})())
    monkeypatch.setattr(settings, "proactive_voice", True)
    monkeypatch.setattr(settings, "telegram_voice", True)
    monkeypatch.setattr(settings, "quiet_hours", "23:00-07:00")
    monkeypatch.setattr(speech, "in_quiet_hours", lambda now=None: False)
    execute("publish_report", ctx, {"kind": "morning_brief", "title": "Brief", "body": "# x",
                                    "spoken": "Good morning, Sir. Two exams this week; the phone bill comes first."})
    says = [e for e in events if e.get("type") == "say"]
    assert says and says[0]["text"].startswith("Good morning, Sir") and notes[0][0] == "HERALD"
    events.clear(); notes.clear()
    monkeypatch.setattr(speech, "in_quiet_hours", lambda now=None: True)      # 2 a.m.
    execute("publish_report", ctx, {"kind": "evening_report", "title": "Night", "body": "x", "spoken": "hi"})
    assert not [e for e in events if e.get("type") == "say"] and not notes   # silent at night
    execute("publish_report", ctx, {"kind": "alert", "title": "Exam in 1 hour", "body": "x", "spoken": "Exam soon"})
    assert [e for e in events if e.get("type") == "say"]                    # critical alerts still speak
    assert speech.in_quiet_hours.__name__ == "<lambda>"
    monkeypatch.undo()
    assert speech.in_quiet_hours(datetime(2026, 11, 23, 2, 0, tzinfo=settings.tz)) is True
    assert speech.in_quiet_hours(datetime(2026, 11, 23, 12, 0, tzinfo=settings.tz)) is False


def test_voice_provider_choice(monkeypatch):
    from jarvis import voice
    monkeypatch.setattr(settings, "tts", "auto")
    monkeypatch.setattr(settings, "elevenlabs_key", "")
    assert voice.provider() == "edge" and voice.voice_for("jarvis") == "en-GB-RyanNeural"   # edge-tts installed
    assert voice.voice_for("FRIDAY") == "en-IE-EmilyNeural"
    monkeypatch.setattr(settings, "elevenlabs_key", "k")
    assert voice.provider() == "elevenlabs"
    monkeypatch.setattr(settings, "tts", "browser")
    assert voice.provider() == "browser" and not voice.enabled()


def test_spoken_delivery():
    from jarvis import voice
    assert voice.speakable("Good morning, Sir. Your bill, Sir, is overdue.") == "Good morning Sir. Your bill, Sir, is overdue."
    assert voice.speakable("**Done**, Sir.") == "Done Sir."
    assert voice.segments("[dry] Ah. The bill. [excited] But you got the interview!") == [
        ("dry", "Ah. The bill."), ("excited", "But you got the interview!")]
    assert voice.strip_moods("[warm] Sleep well, Sir.") == "Sleep well, Sir."
    assert voice._shift("-6%", 12, "%") == "+6%" and voice._shift("-2Hz", -5, "Hz") == "-7Hz"


def test_voicestudio_backend(monkeypatch, tmp_path):
    """JARVIS talks to VoiceStudio's OpenAI-style /v1/audio/speech; falls back to the free online voices."""
    import json as _json
    import threading
    import wave
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from jarvis import voice
    calls, mode = [], {"mp3": True}

    class FakeVS(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_GET(self):
            self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers()
            self.wfile.write(b'{"data": []}')
        def do_POST(self):
            body = _json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append(body)
            if body["response_format"] == "mp3" and not mode["mp3"]:
                self.send_response(400); self.end_headers(); self.wfile.write(b'{"error": {"message": "ffmpeg"}}'); return
            self.send_response(200); self.end_headers()
            self.wfile.write(b"ID3" + b"\0" * 500 if body["response_format"] == "mp3" else b"\1\0" * 2400)

    srv = HTTPServer(("127.0.0.1", 0), FakeVS)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setattr(settings, "voicestudio_url", f"http://127.0.0.1:{srv.server_port}")
    monkeypatch.setattr(settings, "tts", "auto")
    monkeypatch.setattr(settings, "elevenlabs_key", "")
    monkeypatch.setattr(voice, "CACHE", tmp_path)
    voice._vs_seen.update(at=0.0)
    assert voice.provider() == "voicestudio"
    assert voice.voice_for("FRIDAY").startswith("female") and "irish" in voice.voice_for("FRIDAY")

    p = voice.synthesize("JARVIS", "[amused] Good morning, Sir. [tired] The bill is still unpaid.")
    assert p.suffix == ".mp3" and len(calls) == 2
    assert calls[0]["input"] == "[laughter] Good morning Sir." and calls[0]["instructions"].startswith("male")
    assert calls[1]["input"].startswith("[sigh] ") and calls[1]["speed"] < 1 and calls[0]["seed"] == calls[1]["seed"]
    assert "[amused]" not in _json.dumps(calls)                           # our mood tags never reach VoiceStudio

    mode["mp3"] = False                                                    # VoiceStudio without ffmpeg -> WAV
    p = voice.synthesize("FRIDAY", "Morning, Sir!")
    assert p.suffix == ".wav" and wave.open(str(p)).getframerate() == 24000

    edge_calls = []
    monkeypatch.setattr(voice, "_edge", lambda text, agent, path: edge_calls.append(text) or path.write_bytes(b"x" * 300))
    phone = voice.synthesize_for_phone("FRIDAY", "Morning, Sir!")         # Telegram needs mp3
    assert phone.suffix == ".mp3" and edge_calls

    srv.shutdown(); srv.server_close()
    voice._vs_seen.update(at=0.0)
    assert voice.provider() == "edge"                                      # VoiceStudio off -> free online voices


def test_voicecheck_reports_and_sends_sample(monkeypatch, tmp_path):
    from jarvis import telegram as tg
    from jarvis import voice
    sent = []
    monkeypatch.setattr(voice, "provider", lambda: "edge")
    monkeypatch.setattr(voice, "synthesize_for_phone", lambda a, t: tmp_path / "x.mp3")
    monkeypatch.setattr(tg, "send_voice", lambda p: sent.append(p))
    report = tg.voice_check()
    assert "Understanding your voice notes" in report and "Voice for replies: edge ✅" in report
    assert "Test voice note: sent" in report and sent
    monkeypatch.setattr(voice, "provider", lambda: "browser")
    assert "can't make voice notes" in tg.voice_check()


def test_search_email_asks_the_server(env, monkeypatch):
    store, ctx, _ = env
    monkeypatch.setattr(ch, "email_read_ready", lambda: True)
    monkeypatch.setattr(ch, "recent_mail", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no full download")))
    monkeypatch.setattr(ch, "search_mail", lambda q, days=60, limit=15: [
        {"uid": 9, "from": "Murdoch University <admissions@murdoch.edu.au>", "date": "Tue", "subject": "Your offer", "body": "Welcome"}])
    out, err = execute("search_email", ctx, {"query": "Murdoch"})
    assert not err and "Your offer" in out
