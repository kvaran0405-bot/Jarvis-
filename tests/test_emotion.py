"""Mark IV P1: the Emotion Engine and Gemini voices."""
import base64
import io
import json
import urllib.error

import pytest

from jarvis import gemtts, voice
from jarvis.config import settings


def test_emote_segments_and_subtitles():
    t = "[amused] Oh, Sir. [laughs] You did not. [whispers] Don't tell Pepper."
    assert voice.segments(t) == [("amused", "Oh, Sir."), ("!laughs", ""), ("amused", "You did not."),
                                 ("whisper", "Don't tell Pepper.")]
    assert voice.strip_moods(t) == "Oh, Sir. (laughs) You did not. Don't tell Pepper."


def test_gemini_direction_turns_tags_into_stage_directions():
    d = gemtts.direction("FRIDAY", "[excited] You got it! [laughs] Told you.")
    assert "Irish" in d and "(excited) You got it! (laughs) Told you." in d and "[" not in d.split("\n\n")[1]


@pytest.fixture
def gem(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "gemini_key", "test-key")
    monkeypatch.setattr(settings, "tts", "auto")
    monkeypatch.setattr(settings, "elevenlabs_key", "")
    monkeypatch.setattr(voice, "CACHE", tmp_path)
    gemtts._state.update(down_until=0.0, model=None, secs=0.0, chars=0, why="")
    return tmp_path


def test_gemini_voice_writes_wav(gem, monkeypatch):
    pcm = b"\x00\x01" * 2400
    body = {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "audio/L16;codec=pcm;rate=24000",
                                                                   "data": base64.b64encode(pcm).decode()}}]}}]}
    sent = {}

    def fake(req, timeout=45):
        sent.update(json.loads(req.data))
        return io.BytesIO(json.dumps(body).encode())
    monkeypatch.setattr("urllib.request.urlopen", fake)
    assert voice.provider() == "gemini"
    p = voice.synthesize("PEPPER", "[sighs] Fine. I'll chase Nexus.")
    assert p.suffix == ".wav" and p.stat().st_size > 4000
    assert sent["generationConfig"]["speechConfig"]["voiceConfig"]["prebuiltVoiceConfig"]["voiceName"] == "Kore"


def test_gemini_refusal_falls_back_to_free_voices(gem, monkeypatch):
    def refuse(req, timeout=45):
        raise urllib.error.HTTPError(req.full_url, 429, "quota", {}, None)
    monkeypatch.setattr("urllib.request.urlopen", refuse)
    used = []
    monkeypatch.setattr(voice, "_edge", lambda text, agent, path: (used.append(agent), path.write_bytes(b"mp3")))
    p = voice.synthesize("JARVIS", "Splendid, Sir. [chuckles]")
    assert used == ["JARVIS"] and p.suffix == ".mp3"
    assert not gemtts.enabled() and "free limit" in gemtts.status()["paused_reason"]
    assert voice.provider() != "gemini"     # paused for a while, free voices carry on
