"""Mark IV P3: group calls, team dinner, surprise notes, diaries, gifts, team photo."""
from datetime import datetime

import pytest

from jarvis import bonds, team
from jarvis.bus import Bus
from jarvis.config import settings
from jarvis.store import Store


class FakeEngine:
    def __init__(self, reply):
        self.store = Store(":memory:")
        self.bus = Bus(self.store)
        self.events = []
        self.bus.publish = self.events.append
        self.reply, self.prompts = reply, []

    def run(self, agent, prompt, **kw):
        self.prompts.append((agent, prompt))
        return self.reply(agent, prompt) if callable(self.reply) else self.reply


@pytest.fixture(autouse=True)
def quiet(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "proactive_voice", False)
    monkeypatch.setattr(settings, "telegram_voice", False)
    monkeypatch.setattr(team, "GIFTS", tmp_path / "gifts")
    from jarvis import telegram
    monkeypatch.setattr(telegram, "ready", lambda: False)


def test_phrases():
    assert team.TEAM_RE.match("team, what should I do this weekend?").group(1).startswith("what")
    assert team.TEAM_RE.match("Jarvis, group call about the Tan wedding").group(2) == "the Tan wedding"
    assert team.TEAM_RE.match("call the team")
    assert not team.TEAM_RE.match("the team is great")
    assert team.DINNER_RE.match("team dinner") and team.DINNER_RE.match("Jarvis, dinner with the team!")


def test_group_call_parses_script_and_bonds():
    script = ('Sure! ```json\n[{"agent": "JARVIS", "line": "Gentlemen, ladies."}, {"agent": "friday", "line": '
              '"[laughs] Boss is here!"}, {"agent": "ZEUS", "line": "Let\'s go!"}, {"agent": "NOBODY", "line": "x"}]```')
    e = FakeEngine(script)
    lines = team.call(e, "weekend plans with zeus")
    assert [x["agent"] for x in lines] == ["JARVIS", "FRIDAY", "ZEUS"]
    ev = next(x for x in e.events if x.get("type") == "team")
    assert "ZEUS" in ev["agents"] and ev["agents"][0] == "JARVIS" and len(ev["lines"]) == 3
    assert "bond level" in e.prompts[0][1]
    assert bonds.get(e.store, "FRIDAY")["xp"] == 3
    assert team.transcript(lines).startswith("Jarvis: Gentlemen")


def test_group_call_falls_back_to_plain_reply():
    e = FakeEngine("The team is busy, Sir.")
    assert team.call(e, "hi") == [{"agent": "JARVIS", "line": "The team is busy, Sir."}]


def test_dinner_marks_event():
    e = FakeEngine('[{"agent":"JARVIS","line":"A toast."}]')
    team.dinner(e)
    ev = next(x for x in e.events if x.get("type") == "team")
    assert ev["dinner"] and "TEAM DINNER" in e.prompts[0][1]


def test_surprise_rules():
    e = FakeEngine("")
    assert team.surprise_agent(e.store, roll=0.1) is None          # nobody is close enough yet
    bonds.add_xp(e.store, e.bus, "BANNER", 200)
    assert team.surprise_agent(e.store, roll=0.9) is None          # not today
    assert team.surprise_agent(e.store, roll=0.1) == "BANNER"
    bonds.moment(e.store, "BANNER", "Surprise voice note: hi")
    bonds.moment(e.store, "BANNER", "Surprise voice note: hello")
    assert team.surprise_agent(e.store, roll=0.1) is None          # two this week already


def test_diaries():
    e = FakeEngine('{"JARVIS": "Dear diary, he slept at 3am again.", "FRIDAY": "Best week ever!", "ZEUS": ""}')
    bonds.add_xp(e.store, e.bus, "FRIDAY", 50)
    assert team.write_diaries(e) == 2
    room = bonds.room(e.store, "JARVIS")
    assert room["diary"][0]["text"].startswith("Dear diary")


def test_gift_and_photo():
    e = FakeEngine('{"title": "Gym Bangers", "message": "For leg day.", "items": ["Queen - Don\'t Stop Me Now", "Survivor - Eye of the Tiger"]}')
    assert team.give_gift(e) is None                               # no level-5 friend yet
    bonds.add_xp(e.store, e.bus, "STEVE", 500)
    g = team.give_gift(e, kind="playlist")
    assert g["agent"] == "STEVE" and g["title"] == "Gym Bangers"
    row = e.store.query("SELECT * FROM agent_gifts WHERE id = ?", (g["id"],))[0]
    assert "youtube.com/results?search_query=Queen" in row["body"]
    from PIL import Image
    assert Image.open(row["file"]).size == (1200, 1500)
    assert any(x.get("type") == "gift" for x in e.events)
    w = team.give_gift(e, "STEVE", "wallpaper")
    assert Image.open(w["file"]).size == (1080, 2340)
    photo = team.team_photo(e.store)
    assert Image.open(photo).size == (1600, 1000)


def test_routes(monkeypatch):
    from fastapi.testclient import TestClient
    from jarvis import server
    c = TestClient(server.app, base_url="http://127.0.0.1:7334", client=("127.0.0.1", 5))
    assert c.get("/api/team/photo").headers["content-type"] == "image/png"
    assert c.get("/api/gifts/999999").status_code == 404
    assert isinstance(c.get("/api/gifts").json(), list)
    called = {}
    monkeypatch.setattr(team, "call", lambda eng, topic, **kw: called.setdefault("t", (topic, kw)) and [{"agent": "JARVIS", "line": "Hi"}])
    assert c.post("/api/team", json={"topic": "plans", "agents": ["friday", "guest"]}).json()["lines"][0]["line"] == "Hi"
    assert called["t"] == ("plans", {"who": ["FRIDAY"]})
