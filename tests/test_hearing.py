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


def test_commands_forgive_natural_wording():
    from jarvis import server
    n = server.natural
    assert n("“preview the Christmas skin”") == "preview the Christmas skin"
    assert n("Jarvis, can you preview the christmas skin please") == "Jarvis, preview the christmas skin"
    assert n("could you plan my route for me?") == "plan my route"
    assert n("fast mode on pls") == "fast mode on" and n("show me my map lah") == "show me my map"
    assert n("what's the weather?") == "what's the weather?"          # real questions keep their question mark
    assert server.special("can you preview the christmas skin")[0]
    server.special("seasonal skins auto")


def test_audio_is_decoded_by_jarvis(tmp_path):
    import wave
    import numpy as np
    p = tmp_path / "a.wav"
    with wave.open(str(p), "wb") as w:
        w.setnchannels(2); w.setsampwidth(2); w.setframerate(48000)
        w.writeframes((np.sin(np.linspace(0, 200, 48000 * 2)) * 8000).astype("<i2").tobytes())
    a = stt.load_audio(str(p))
    assert a.dtype == np.float32 and abs(len(a) - 16000) < 5 and 0.1 < float(abs(a).max()) < 1


def test_every_tool_is_valid_for_gemini():
    """Gemini rejects ALL tools if one list has no item type, which broke every Gemini reply once."""
    from jarvis import server  # noqa: F401  (registers every tool)
    from jarvis.brains import _gemini_schema
    from jarvis.tools import REGISTRY
    bad = []

    def walk(n, path):
        if isinstance(n, dict):
            if n.get("type") == "array" and not n.get("items"):
                bad.append(path)
            for k, v in n.items():
                walk(v, path + "." + k)
    for name, t in REGISTRY.items():
        if t.properties:
            walk(_gemini_schema(t.schema()["input_schema"]), name)
    assert not bad
    assert _gemini_schema({"type": "array"}) == {"type": "array", "items": {"type": "string"}}


def test_spreadsheet_numbers_become_numbers():
    from jarvis.desktop import _cell
    assert _cell("12.50") == 12.5 and _cell("1,200") == 1200 and _cell("Tan wedding") == "Tan wedding" and _cell(3) == 3
