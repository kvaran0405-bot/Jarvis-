"""Human-like delivery: attitude, inferred feelings, natural rhythm, real pauses, and the offline voice fallback."""
from pathlib import Path

from jarvis import voice


def test_delivery_breathes_and_varies():
    rows = voice.delivery("Right. The quote went out... Want me to chase them? Brilliant work today!", "", "JARVIS", 14)
    words = [r[0] for r in rows]
    assert words == ["Right.", "The quote went out...", "Want me to chase them?", "Brilliant work today!"]
    trail, question, last = rows[1], rows[2], rows[3]
    assert trail[3] > question[3] > 0 and last[3] == 0                 # "..." pauses longest, last line no pause
    assert question[2] >= rows[0][2]                                    # questions lift
    assert voice.delivery("Same line.", "", "JARVIS", 14) == voice.delivery("Same line.", "", "JARVIS", 14)   # stable


def test_attitude_and_feelings():
    assert voice.infer_mood("Sorry Sir, the deposit is overdue.", "PEPPER") == "concerned"
    assert voice.infer_mood("Congratulations, you nailed it", "JARVIS") == "proud"
    assert voice.infer_mood("Leave now, the train is coming", "JARVIS") == "urgent"
    assert voice.infer_mood("Okay then.", "SENTINEL") == "stern"        # the agent's own attitude
    assert voice.infer_mood("Okay then.", "FRIDAY", hour=1) == "gentle"  # late at night everyone is softer
    tagged = voice.delivery("Big news.", "excited", "JARVIS", 14)[0]
    untagged = voice.delivery("Big news.", "", "ZEUS", 14)[0]
    assert tagged[1] > untagged[1] - 3                                  # a chosen mood plays stronger than an inferred one


def test_silence_is_real_audio_frames():
    s = voice.silence_mp3(480)
    assert len(s) == 20 * 144 and s[:2] == b"\xff\xf3"


def test_offline_voice_takes_over_when_online_voice_fails(tmp_path, monkeypatch):
    from jarvis import localvoice
    monkeypatch.setattr(voice, "CACHE", tmp_path)
    monkeypatch.setattr(voice, "provider", lambda: "edge")
    monkeypatch.setattr(voice, "_edge", lambda *a: (_ for _ in ()).throw(OSError("no internet")))
    monkeypatch.setattr(localvoice, "ready", lambda: True)
    got = {}

    def fake(agent, pieces, path):
        got["agent"], got["pieces"] = agent, pieces
        p = Path(path).with_suffix(".wav"); p.write_bytes(b"RIFF"); return p
    monkeypatch.setattr(localvoice, "synthesize", fake)
    out = voice.synthesize("FRIDAY", "[excited] You got the gig! [laughs] I knew it.")
    assert out.suffix == ".wav" and got["agent"] == "FRIDAY"
    assert any(p[0].startswith("Ha ha") for p in got["pieces"]) and any("gig" in p[0] for p in got["pieces"])
    monkeypatch.setattr(localvoice, "ready", lambda: False)
    import pytest
    with pytest.raises(OSError):
        voice.synthesize("JARVIS", "No voice at all this time.")
