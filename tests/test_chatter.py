"""Location chatter: a friendly message about where the owner is, with sensible limits."""
import json
from datetime import datetime, timedelta

import pytest

from jarvis import chatter
from jarvis.config import settings
from jarvis.store import Store

CITY_HALL = (1.2935, 103.8515)


@pytest.fixture(autouse=True)
def awake(monkeypatch):
    monkeypatch.setattr("jarvis.speech.in_quiet_hours", lambda now=None: False)
    monkeypatch.setattr("jarvis.life.in_focus", lambda store: False)


def test_needs_a_few_minutes_and_limits():
    s = Store(":memory:")
    t = datetime(2026, 11, 26, 12, 0, tzinfo=settings.tz)
    assert chatter.should_chat(s, *CITY_HALL, 0, t) is None                        # just arrived
    assert chatter.should_chat(s, *CITY_HALL, 0, t + timedelta(minutes=2)) is None  # still settling in
    assert chatter.should_chat(s, *CITY_HALL, 0, t + timedelta(minutes=6)) == "City Hall"
    assert chatter.should_chat(s, *CITY_HALL, 0, t + timedelta(minutes=9)) is None  # once per area per day
    assert chatter.should_chat(s, *CITY_HALL, 15, t + timedelta(minutes=10)) is None    # driving through
    # another area soon after: too soon (90-minute gap)
    chatter.should_chat(s, 1.3005, 103.8558, 0, t + timedelta(minutes=20))
    assert chatter.should_chat(s, 1.3005, 103.8558, 0, t + timedelta(minutes=30)) is None


def test_never_at_home_or_when_off():
    s = Store(":memory:")
    s.set("places:saved", json.dumps({"home": list(CITY_HALL)}))
    t = datetime(2026, 11, 26, 12, 0, tzinfo=settings.tz)
    chatter.should_chat(s, *CITY_HALL, 0, t)
    assert chatter.should_chat(s, *CITY_HALL, 0, t + timedelta(minutes=10)) is None
    s2 = Store(":memory:")
    s2.set("chatter:on", "off")
    chatter.should_chat(s2, *CITY_HALL, 0, t)
    assert chatter.should_chat(s2, *CITY_HALL, 0, t + timedelta(minutes=10)) is None


def test_compose_template_and_agent():
    s = Store(":memory:")
    agent, msg = chatter.compose(s, "City Hall", *CITY_HALL, engine=None)
    assert agent in ("FRIDAY", "ATHENA", "HERALD", "STEVE", "JARVIS") and "minutes' walk" in msg

    class E:
        def run(self, agent, prompt, **kw):
            assert "City Hall" in prompt and "walk" in prompt
            return "Hi Sir, I see you're at City Hall! The National Gallery rooftop is calling 🌇"
    from jarvis import brain
    import pytest as _p
    mp = _p.MonkeyPatch(); mp.setattr(brain, "pick", lambda *a, **k: "gemini")
    try:
        assert chatter.compose(s, "City Hall", *CITY_HALL, engine=E())[1].startswith("Hi Sir")
    finally:
        mp.undo()


def test_area_lookup():
    assert chatter.area_of(*CITY_HALL) == "City Hall"
    assert chatter.area_of(1.45, 104.05) is None
