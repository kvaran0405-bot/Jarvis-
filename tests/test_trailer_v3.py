"""Trailer v3: the voice drives the edit (titles = spoken words), fast rendering, and the phone keeps it up to date."""
from jarvis.config import ROOT

T = (ROOT / "web/trailer.html").read_text(encoding="utf-8")


def test_voice_drives_the_cuts():
    assert "JARVIS-TRAILER" in T
    assert "function voiceDone(" in T and "function shouldCut(" in T   # a shot ends only after its line has been said
    assert "caption(sh.vo)" in T and "prog >= o.at" in T                  # karaoke captions follow the voice
    assert 'title: t.toUpperCase()' in T                                  # the title is exactly the spoken line
    assert "AC.outputLatency" in T                                        # pictures line up with what you hear


def test_fast_on_phones():
    assert "uMorph" in T and "ShaderMaterial" in T          # particles animate on the graphics chip
    assert "drawImage(GL" not in T.split("if (recorder)")[0]  # no copying the 3D picture every frame (only when recording)
    assert "function adapt(" in T


def test_one_voice_per_character_and_phone_updates():
    assert 'engine: str = ""' in (ROOT / "jarvis/server.py").read_text(encoding="utf-8")
    assert 'laptopVoice(v.agent, v.text, "free")' in T
    java = (ROOT / "android/app/src/main/java/os/jarvis/app/Solo.java").read_text(encoding="utf-8")
    assert 'savePage(c, "trailer.html"' in java and "localPage" in java
