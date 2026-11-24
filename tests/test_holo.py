"""Mark III phase 2: Holo Lab data, narration, trophies, voice commands."""
from datetime import date, timedelta

from jarvis import holo, server
from jarvis.bus import Bus
from jarvis.store import Store


def test_holo_data_and_narration():
    s = Store(":memory:")
    today = date.today()
    s.add_event("FIN302 lecture", today.isoformat() + "T09:00", today.isoformat() + "T11:00", "Kaplan City Campus", "academic")
    s.add_event("Site visit", (today - timedelta(days=30)).isoformat() + "T10:00", None, "Marina Bay Sands", "career")
    s.execute("INSERT INTO workouts (day, exercise, sets) VALUES (?,?,?)", (today.isoformat(), "Bench press", 12))
    s.execute("INSERT INTO transactions (day, amount, category) VALUES (?,?,?)", (today.isoformat(), -50, "food"))
    gid = s.add_gig("Priya", event_type="Wedding", event_date=(today + timedelta(days=10)).isoformat())
    s.update_gig(gid, quote_total=12000, status="confirmed")
    d = holo.data(s)
    assert d["week"][0]["title"] == "FIN302 lecture" and d["week"][0]["dur"] == 2
    assert d["muscles"]["chest"] == 1.0 and d["muscles"]["quads"] == 0 and d["muscles"]["lats"] == 0
    assert d["spending"] == [{"category": "food", "amount": 50}]
    assert "Marina Bay Sands" in d["explored"] and d["today_places"][0]["place"] == "Kaplan City Campus"
    assert "chest" in holo.narrate("body", d) and "$12,000" in holo.narrate("business", d)
    assert "Kaplan" in holo.narrate("singapore", d)
    assert holo.narrate("diagnostics", d).startswith("Diagnostics complete")


def test_trophies_unlock_once_and_celebrate():
    s = Store(":memory:")
    b = Bus(s)
    events = []
    b.publish = events.append
    gid = s.add_gig("Tan", event_type="Engagement")
    s.update_gig(gid, quote_total=7000, status="confirmed")
    new = {t["key"] for t in holo.check_trophies(s, b)}
    assert {"first_quote", "first_booking"} <= new
    assert any(e.get("type") == "celebrate" for e in events)
    assert holo.check_trophies(s, b) == []          # never twice
    t = {x["key"]: x for x in holo.trophies(s)}
    assert t["first_booking"]["unlocked"] and not t["ten_events"]["unlocked"] and t["ten_events"]["progress"] == 1


def test_show_me_phrases_open_holograms(monkeypatch):
    seen = []
    monkeypatch.setattr(server.bus, "publish", seen.append)
    line, agent, _ = server.special("Jarvis, show me my week")
    assert line.startswith("Your week") and agent is None and seen[-1] == {"type": "holo", "view": "week"}
    server.special("show me Shaabaz")
    assert seen[-1]["view"] == "business"
    server.special("run diagnostics")
    assert seen[-1]["view"] == "diagnostics"
    assert server.special("show me the trophies")[0].endswith(".") and seen[-1]["view"] == "trophies"
    assert server.special("show me how to cook rice") == (None, None, None)


def test_holo_has_todays_path_and_steps():
    from jarvis import server, holo
    d = holo.data(server.store)
    assert "today_path" in d and isinstance(d["today_path"], list)
    assert "today" in d["steps"] and len(d["steps"]["week"]) == 7
