"""Mark IV P2: bonds, nicknames, moods, opinions, greetings, rituals, rooms."""
from datetime import datetime, timedelta

import pytest

from jarvis import bonds
from jarvis.bus import Bus
from jarvis.config import settings
from jarvis.store import Store


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setattr(settings, "timezone", "Asia/Singapore")
    monkeypatch.setattr(settings, "proactive_voice", True)
    monkeypatch.setattr(settings, "quiet_hours", "00:00-00:01")
    monkeypatch.setattr(settings, "telegram_voice", False)
    s = Store(":memory:")
    b = Bus(s)
    events = []
    b.publish = events.append
    return s, b, events


def test_levels_and_level_up(env):
    s, b, events = env
    assert bonds.get(s, "FRIDAY")["level"] == 1
    bonds.add_xp(s, b, "FRIDAY", 35, "test")
    got = bonds.get(s, "FRIDAY")
    assert got["level"] == 2 and got["title"] == "Acquaintance" and 0 < got["progress"] < 1
    up = [e for e in events if e.get("type") == "bond_up"]
    assert up and up[0]["agent"] == "FRIDAY" and up[0]["unlocked"] == "uses your nickname"
    assert any(e.get("type") == "say" and e["agent"] == "FRIDAY" for e in events)
    assert bonds.add_xp(s, b, "GUEST", 50) == {}


def test_thanks_and_nicknames(env, monkeypatch):
    s, b, _ = env
    monkeypatch.setenv("JARVIS_OWNER_FIRSTNAME", "Kam")
    bonds.interact(s, b, "BANNER", "thank you, that really helped")
    got = bonds.get(s, "BANNER")
    assert got["thanks"] == 1 and got["xp"] == 11
    assert bonds.nickname(s, "BANNER") == settings.owner_name       # level 1: still formal
    bonds.add_xp(s, b, "BANNER", 40)
    assert bonds.nickname(s, "BANNER") == "Kam" and bonds.nickname(s, "JARVIS") == "Sir"
    bonds.set_nickname(s, "FRIDAY", "Dragon")
    assert bonds.nickname(s, "FRIDAY") == "Dragon"


def test_moods_follow_life(env):
    s, b, _ = env
    for i in range(3):
        s.add_task(f"late {i}", due=(datetime.now(settings.tz).date() - timedelta(days=2)).isoformat())
    assert bonds.mood(s, "SENTINEL")[0] == "grumpy"
    s.execute("INSERT INTO workouts (day, exercise) VALUES (?, 'Squat')", (datetime.now(settings.tz).date().isoformat(),))
    assert bonds.mood(s, "STEVE") == ("pumped", "you trained today")
    m1, _ = bonds.mood(s, "ORACLE")
    assert m1 == bonds.mood(s, "ORACLE")[0] and m1 in bonds.FLAVOURS["ORACLE"]   # stable all day


def test_context_room_and_rituals(env):
    s, b, _ = env
    bonds.add_xp(s, b, "PEPPER", 300)
    bonds.moment(s, "PEPPER", "Closed the Tan wedding together")
    s.add_agent_note("PEPPER", "Running gag: he always underquotes")
    ctx = bonds.context(s, "PEPPER")
    assert "level 5" in ctx and "Closed the Tan wedding" in ctx and "underquotes" in ctx and "VERONICA" in ctx
    assert bonds.context(s, "GUEST") == ""
    room = bonds.room(s, "PEPPER")
    assert room["bond"]["level"] == 5 and room["favourites"] and any(u["on"] for u in room["unlocked"])
    kind, line = bonds.ritual(s, "STEVE")
    assert kind == "chant" and line
    assert bonds.greet(s, "FRIDAY", night=True) in [l.format(n=bonds.nickname(s, "FRIDAY")) for l in bonds.NIGHTS["FRIDAY"]]


def test_phrases_and_routes(monkeypatch):
    from fastapi.testclient import TestClient
    from jarvis import server
    assert server.special("good morning")[0]
    assert "Friday will call you" in server.special("Friday, call me Dragon")[0]
    c = TestClient(server.app, base_url="http://127.0.0.1:7334", client=("127.0.0.1", 5))
    all_b = c.get("/api/bonds").json()
    assert {x["agent"] for x in all_b} >= {"JARVIS", "PEPPER"} and "GUEST" not in {x["agent"] for x in all_b}
    assert c.get("/api/bonds/pepper").json()["agent"] == "PEPPER"
    assert c.get("/api/bonds/guest").status_code == 404
    assert c.post("/api/bonds/zeus/thanks").json()["bond"]["thanks"] >= 1


def test_named_greeting_comes_from_that_agent():
    from fastapi.testclient import TestClient
    from jarvis import server
    direct = server.special("good night Friday")[0]
    assert server.split_agent(direct)[0] == "FRIDAY" and "…" not in direct
    c = TestClient(server.app, base_url="http://127.0.0.1:7334", client=("127.0.0.1", 5))
    r = c.post("/api/command", json={"text": "good morning steve", "agent": "JARVIS"}).json()
    assert r["agent"] == "STEVE" and not r["reply"].startswith("@")
    assert server.handle_owner_message("good morning pepper", via="Telegram").startswith("Pepper: ")
    assert server.split_agent(server.special("good morning")[0])[0] == "JARVIS"
