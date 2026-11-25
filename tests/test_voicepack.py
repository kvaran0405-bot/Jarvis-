"""Solo voices: the laptop's own voice for everyday lines on the phone, and every premium voice model tried first."""
import base64
import json

from jarvis import voicepack
from jarvis.config import ROOT

SOLO = (ROOT / "android/app/src/main/assets/solo.html").read_text(encoding="utf-8")


def test_keys_match_the_phone():
    # solo.html: agent + "|" + text.toLowerCase().replace(/[^a-z0-9 ]/g, "").replace(/\s+/g, " ").trim()
    assert voicepack.vkey("JARVIS", "Sorry Sir, I didn't catch that. Once more?") == "JARVIS|sorry sir i didnt catch that once more"
    assert 'agent + "|" + text.toLowerCase().replace(/[^a-z0-9 ]/g, "").replace(/\\s+/g, " ").trim()' in SOLO


def test_pack_is_built_in_the_laptops_voice(monkeypatch, tmp_path):
    from jarvis import voice
    clip = tmp_path / "a.mp3"
    clip.write_bytes(b"ID3fake")
    monkeypatch.setattr(voice, "synthesize", lambda agent, text, live=False: clip)
    monkeypatch.setattr(voicepack, "PACK", tmp_path / "vp.json")
    out = voicepack.build()
    assert out["lines"] == len(voicepack.PHRASES) and out["version"]
    data = json.loads((tmp_path / "vp.json").read_text())
    assert base64.b64decode(data["lines"]["JARVIS|very good sir"]["b64"]) == b"ID3fake"


def test_solo_uses_the_pack_and_every_voice_model():
    assert "N?.voicePackVersion?.()" in SOLO and "VCACHE.put(key" in SOLO
    assert "hit429 = true; continue;" in SOLO
