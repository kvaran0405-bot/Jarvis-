"""Hearing: vocabulary hints, the /api/hear endpoint, and Singapore English."""
from jarvis import stt


def test_vocabulary_has_names_and_places():
    v = stt.vocabulary()
    for word in ("Jarvis", "Pepper", "Veronica", "Shaabaz", "Kaplan", "Tampines"):
        assert word in v


def test_hear_endpoint(monkeypatch):
    from fastapi.testclient import TestClient
    from jarvis import server
    monkeypatch.setattr(stt, "available", lambda: True)
    got = {}

    def fake(path, hint=""):
        got["hint"], got["size"] = hint, open(path, "rb").read()
        return "Jarvis, ask Pepper to send the Shaabaz quote", 0.91
    monkeypatch.setattr(stt, "transcribe_scored", fake)
    c = TestClient(server.app, base_url="http://127.0.0.1:7334", client=("127.0.0.1", 5))
    r = c.post("/api/hear", content=b"\x1aE\xdf\xa3fakewebm", headers={"Content-Type": "audio/webm;codecs=opus"}).json()
    assert r == {"text": "Jarvis, ask Pepper to send the Shaabaz quote", "confidence": 0.91}
    assert "Shaabaz" in got["hint"] and got["size"].startswith(b"\x1aE")
    assert c.post("/api/hear", content=b"").status_code == 400
    v = c.get("/api/voices").json()
    assert v["speech_lang"] == "en-SG" and v["hear"] is True
