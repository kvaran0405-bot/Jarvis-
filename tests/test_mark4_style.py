"""Mark IV P4: drag-and-drop, seasonal skins, desk AR."""
import base64
from datetime import date

import pytest

from jarvis import drop, hud
from jarvis.config import settings
from jarvis.store import Store


class FakeEngine:
    def __init__(self):
        self.prompts = []

    def run(self, agent, prompt, **kw):
        self.prompts.append((agent, prompt))
        return f"{agent} read it."


@pytest.fixture(autouse=True)
def drops(monkeypatch, tmp_path):
    monkeypatch.setattr(drop, "DROPS", tmp_path / "drops")
    monkeypatch.delenv("JARVIS_BIRTHDAY", raising=False)
    monkeypatch.setattr(settings, "profile", lambda: "")


def test_drop_reads_documents():
    e = FakeEngine()
    out = drop.handle(e, "../../evil name?.txt", b"Wedding deposit due 3 Dec. Call Mrs Tan.", "pepper")
    assert out["agent"] == "PEPPER" and out["reply"] == "PEPPER read it."
    assert "Wedding deposit due 3 Dec" in e.prompts[0][1] and "evil name_.txt" in e.prompts[0][1]
    assert drop.DROPS in __import__("pathlib").Path(out["path"]).parents


def test_drop_refuses_secrets_and_unknown_types():
    e = FakeEngine()
    assert "left it" in drop.handle(e, "notes.txt", b"my password: hunter2 OTP 123456")["reply"]
    assert "can't read" in drop.handle(e, "song.mp3", b"ID3")["reply"]
    assert drop.handle(e, "x.txt", b"hi", "guest")["agent"] == "JARVIS"
    assert len(e.prompts) == 1   # only the harmless file was read


def test_drop_images_use_vision(monkeypatch):
    from jarvis import vision
    monkeypatch.setattr(vision, "ask", lambda data, mime, prompt: "Poster: Tan wedding, 3 Dec, Raffles Hotel")
    e = FakeEngine()
    drop.handle(e, "poster.PNG", b"\x89PNG")
    assert "Raffles Hotel" in e.prompts[0][1]
    monkeypatch.setattr(vision, "ask", lambda *a: "private document")
    assert "private" in drop.handle(FakeEngine(), "card.jpg", b"x")["reply"]


@pytest.mark.parametrize("day,name", [("2026-12-20", "christmas"), ("2026-12-31", "newyear"), ("2027-01-02", "newyear"),
                                      ("2027-08-09", "national"), ("2027-02-10", "cny"), ("2027-03-12", "raya"),
                                      ("2026-11-07", "deepavali"), ("2026-11-23", None), ("2027-06-01", None)])
def test_seasons(day, name):
    s = hud.season(date.fromisoformat(day))
    assert (s or {}).get("name") == name
    if s:
        assert s["accent"].startswith("#") and s["line"] and s["fx"]


def test_season_choice_and_birthday(monkeypatch):
    st = Store(":memory:")
    assert hud.set_season(st, "Diwali") == "deepavali" and hud.season(date(2027, 6, 1), st)["name"] == "deepavali"
    assert hud.set_season(st, "off") == "off" and hud.season(date(2026, 12, 25), st) is None
    hud.set_season(st, "auto")
    monkeypatch.setenv("JARVIS_BIRTHDAY", "12-25")
    assert hud.season(date(2026, 12, 25), st)["name"] == "birthday"
    monkeypatch.setenv("JARVIS_SEASON_DATES", "deepavali=2030-10-25")
    monkeypatch.delenv("JARVIS_BIRTHDAY")
    assert hud.season(date(2030, 10, 24), st)["name"] == "deepavali"


def test_phrases_and_routes(monkeypatch):
    from fastapi.testclient import TestClient
    from jarvis import server
    assert "classic suit" in server.special("seasonal skins off")[0]
    assert "Gong Xi" in server.special("preview the chinese new year skin")[0]
    assert server.special("Jarvis, open desk AR")[0]
    server.special("seasonal skins auto")
    c = TestClient(server.app, base_url="http://127.0.0.1:7334", client=("127.0.0.1", 5))
    assert c.get("/api/season").json()["choice"] == "auto"
    assert c.get("/ar.html").status_code == 200
    monkeypatch.setattr(drop, "handle", lambda eng, name, data, agent, note: {"agent": agent.upper(), "reply": data.decode()})
    monkeypatch.setattr(server.brain, "pick", lambda *a, **k: "api")
    r = c.post("/api/drop", json={"name": "a.txt", "data": "data:text/plain;base64," + base64.b64encode(b"hello").decode(), "agent": "edith"})
    assert r.json() == {"agent": "EDITH", "reply": "hello"}
