"""Speaking Singapore names properly, and teaching new ones."""
from jarvis import voice


def test_names_are_said_properly(tmp_path, monkeypatch):
    monkeypatch.setattr(voice, "CACHE", tmp_path / "tts")
    out = voice.speakable("Good morning, Sir. Gig in Tampines, then Bukit Timah by MRT. Shaabaz-style!")
    assert "Tam-pih-neez" in out and "Boo-kit Tee-mah" in out and "M R T" in out and "Shaabaz-style" in out
    voice.teach("Kamal", "Kah-mahl")
    assert "Kah-mahl" in voice.speakable("Kamal, your table is ready")
    assert (tmp_path / "pronounce.json").exists()


def test_teach_phrase(monkeypatch, tmp_path):
    from jarvis import server
    monkeypatch.setattr(voice, "CACHE", tmp_path / "tts")
    assert "Kah-mahl" in server.special("Jarvis, pronounce Kamal as Kah-mahl")[0]
    assert voice.pronunciations()["Kamal"] == "Kah-mahl"
