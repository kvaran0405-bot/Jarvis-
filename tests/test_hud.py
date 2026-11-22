"""Mark III phase 1: orb state, greeting, quips, themes, guest mode, birthday, device token, orb actions."""
from datetime import date

import pytest
from fastapi.testclient import TestClient

from jarvis import hud, server
from jarvis.config import settings


@pytest.fixture
def client():
    return TestClient(server.app, base_url="http://127.0.0.1:7334", client=("127.0.0.1", 50000))


def test_orb_state_tracks_who_is_speaking(client):
    server.bus.publish({"type": "say", "agent": "PEPPER", "say": "Nexus replied, Sir."})
    st = client.get("/api/orb").json()
    assert st["speaking"] and st["agent"] == "PEPPER" and st["color"] == "#e8b04b"
    assert "Nexus replied" in st["text"]


def test_greeting_and_quips_need_no_ai(client):
    g = client.get("/api/greet").json()["text"]
    assert g.startswith("Good ") and settings.owner_name in g
    q = client.get("/api/quips").json()
    assert set(q) >= {"JARVIS", "PEPPER", "STEVE", "SENTINEL"} and all(isinstance(v, str) and v for v in q.values())


def test_poke_says_something(client):
    assert client.post("/api/poke").json()["say"] in hud.POKES


def test_theme_and_guest_phrases(client, monkeypatch):
    d, a, _ = server.special("Jarvis, stealth mode")
    assert "Stealth" in d and hud.theme(server.store) == "stealth"
    server.special("theme classic")
    assert hud.theme(server.store) == "classic"
    assert server.special("guest mode on")[0].startswith("Guest mode on") and hud.guest_on(server.store)
    seen = []
    monkeypatch.setattr(server.engine, "run", lambda agent, prompt, **k: seen.append(agent) or "Hello there.")
    r = client.post("/api/command", json={"text": "what's on his calendar?", "agent": "JARVIS", "rid": "t"}).json()
    assert seen == ["GUEST"] and r["agent"] == "GUEST"
    server.special("end guest mode")
    assert not hud.guest_on(server.store)
    assert server.special("stark expo")[0].startswith("Ladies and gentlemen")
    assert server.special("first contact")[1] == "JARVIS"


def test_guest_persona_sees_nothing_private():
    from jarvis.agents import AGENTS, roster
    g = AGENTS["GUEST"]
    assert g.tools == [] and g.hidden and "GUEST" not in [a["name"] for a in roster()]
    prompt = server.engine.system_prompt(g)
    assert "profile" not in prompt.lower() and server.engine._context_block(g) == ""


def test_birthday_from_profile(monkeypatch):
    monkeypatch.delenv("JARVIS_BIRTHDAY", raising=False)
    monkeypatch.setattr(type(settings), "profile", lambda self: "- Birthday: 4 May\n- Name: Kamal")
    assert hud.birthday() == (5, 4)
    assert hud.is_birthday(date(2027, 5, 4)) and not hud.is_birthday(date(2027, 5, 5))
    monkeypatch.setenv("JARVIS_BIRTHDAY", "12-25")
    assert hud.birthday() == (12, 25)


def test_orb_actions(client, monkeypatch):
    assert "Focus until" in client.post("/api/orb/action", json={"action": "focus"}).json()["say"]
    client.post("/api/orb/action", json={"action": "focus"})
    from jarvis.tools import ToolContext, execute
    execute("focus_mode", ToolContext(server.store, server.bus, settings, server.engine, "JARVIS"), {"minutes": 0})
    assert client.post("/api/orb/action", json={"action": "brief"}).json()["say"].startswith("Good ")
    assert client.post("/api/orb/action", json={"action": "nope"}).status_code == 400


def test_phone_device_token_unlocks_api(monkeypatch):
    monkeypatch.setattr(settings, "access_pin", "4321")
    remote = TestClient(server.app, base_url="https://kamal.example.ts.net")
    assert remote.get("/api/orb").status_code == 401
    tok = TestClient(server.app, base_url="http://127.0.0.1:7334", client=("127.0.0.1", 1)).get("/api/phone/token").json()["token"]
    assert remote.get("/api/orb", headers={"X-Jarvis-Device": tok}).status_code == 200
    assert remote.get("/api/orb", headers={"X-Jarvis-Device": "wrong"}).status_code == 401
