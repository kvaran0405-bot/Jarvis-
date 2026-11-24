"""Talk from the phone, one device answers out loud: the shared speaker switch, replies on both screens,
Telegram voice notes, and Google-quality hearing with the laptop engine as backup."""
import asyncio

from jarvis import speaker, stt
from jarvis.config import settings


def _capture(monkeypatch, server):
    events = []
    real = server.bus.publish
    monkeypatch.setattr(server.bus, "publish", lambda ev: (events.append(ev), real(ev)))
    return events


def test_speaker_switch_by_voice_and_api(monkeypatch):
    from jarvis import server
    events = _capture(monkeypatch, server)
    for said, where in [("speak on my phone", "phone"), ("Jarvis, talk on the laptop", "laptop"),
                        ("phone voice on", "phone"), ("mute both", "off"), ("speak through my computer", "laptop")]:
        reply = server.special(server.natural(said))[0]
        assert speaker.get(server.store) == where, said
        assert reply == speaker.said(where)
    assert {"type": "speaker", "where": "laptop"} in events
    assert server.speaker_set(server.SpeakerIn(where="phone"))["where"] == "phone"
    assert server.speaker_get() == {"where": "phone"}
    server.speaker_set(server.SpeakerIn(where="nonsense"))
    assert speaker.get(server.store) == "laptop"   # anything odd falls back to the laptop


def test_phone_command_reply_reaches_both_screens(monkeypatch):
    from jarvis import server
    speaker.set_to(server.store, server.bus, "laptop")
    events = _capture(monkeypatch, server)
    out = asyncio.run(server.command(server.Command(text="phone voice on", rid="abc", source="phone", voice=True)))
    spoken = [e for e in events if e.get("type") == "speak"]
    assert spoken and spoken[-1]["rid"] == "abc" and spoken[-1]["source"] == "phone"
    assert spoken[-1]["text"] == out["reply"] and spoken[-1]["where"] == "phone"
    speaker.set_to(server.store, server.bus, "laptop")


def test_telegram_voice_note_talks_on_the_chosen_device(monkeypatch, tmp_path):
    from jarvis import server, telegram
    sent, notes, aloud = [], [], []
    monkeypatch.setattr(telegram, "send", lambda t, *a, **k: sent.append(t))
    monkeypatch.setattr(telegram, "api", lambda *a, **k: {})
    monkeypatch.setattr(telegram, "chat_id", lambda: 1)
    monkeypatch.setattr(telegram, "download", lambda fid, dest: dest.write_bytes(b"OggS"))
    monkeypatch.setattr(stt, "hear_best", lambda path, hint="": ("whats on today", 0.95, "gemini"))
    monkeypatch.setattr(stt, "available", lambda: True)
    telegram.attach(server.store)
    bot = telegram.Bot(on_text=lambda t, voice=False: "ORACLE: Gym at 6, Sir.", on_decision=lambda *a: "", log=lambda m: None)
    bot.voice_reply = lambda reply: notes.append(reply)
    bot.on_spoken = lambda reply: aloud.append(reply)
    note = {"file_id": "f", "file_unique_id": "u1", "duration": 4}
    speaker.set_to(server.store, server.bus, "laptop")
    bot.handle_voice(note)
    assert aloud == ["ORACLE: Gym at 6, Sir."] and not notes and "whats on today" in sent[-1]
    speaker.set_to(server.store, server.bus, "phone")
    bot.handle_voice(note)
    assert notes == ["ORACLE: Gym at 6, Sir."] and len(aloud) == 1
    speaker.set_to(server.store, server.bus, "laptop")


def test_hearing_uses_gemini_then_falls_back(monkeypatch, tmp_path):
    clip = tmp_path / "v.ogg"
    clip.write_bytes(b"OggS-fake")
    monkeypatch.setattr(settings, "gemini_key", "AQ.test-key-1234567890123")
    seen = {}

    class Resp:
        def __init__(self, body): self.body = body
        def read(self): return self.body
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake_open(req, timeout=0):
        import json
        seen["body"] = json.loads(req.data)
        return Resp(json.dumps({"candidates": [{"content": {"parts": [{"text": "Aite, remind me gym at Tampines lah"}]}}]}).encode())
    monkeypatch.setattr("urllib.request.urlopen", fake_open)
    text, conf, engine = stt.hear_best(str(clip), "Jarvis, Tampines")
    assert engine == "gemini" and text.startswith("Aite") and conf > 0.9
    parts = seen["body"]["contents"][0]["parts"]
    assert parts[1]["inlineData"]["mimeType"] == "audio/ogg" and "Singapore English" in parts[0]["text"]

    def down(*a, **k):
        raise OSError("offline")
    monkeypatch.setattr("urllib.request.urlopen", down)
    monkeypatch.setattr(stt, "available", lambda: True)
    monkeypatch.setattr(stt, "transcribe_scored", lambda p, h="": ("local words", 0.7))
    assert stt.hear_best(str(clip)) == ("local words", 0.7, "local")   # never goes silent
    monkeypatch.setenv("JARVIS_GEMINI_HEARING", "off")
    assert not stt.gemini_hearing_on()
