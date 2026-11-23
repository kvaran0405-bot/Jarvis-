"""Places explored (the phone's trail) and route planning."""
from datetime import datetime, timedelta

from jarvis import explore, phonelink
from jarvis.bus import Bus
from jarvis.config import settings
from jarvis.store import Store


def test_trail_squares_and_visits():
    s = Store(":memory:")
    t = datetime(2026, 11, 20, 9, 0, tzinfo=settings.tz)
    assert explore.record(s, 1.3006, 103.8497, t) is True          # a new square
    assert explore.record(s, 1.3007, 103.8498, t + timedelta(minutes=10)) is False   # same square, same visit
    explore.record(s, 1.3006, 103.8497, t + timedelta(hours=5))    # came back later: a second visit
    assert explore.record(s, 35.68, 139.76, t) is False             # Tokyo isn't drawn on the Singapore map
    tr = explore.trail(s)
    assert len(tr) == 1 and tr[0][2] == 2 and explore.stats(s)["squares"] == 1


def test_checkin_records_the_trail():
    s = Store(":memory:")
    phonelink.checkin(s, Bus(s), {"battery": 50, "lat": 1.3521, "lon": 103.9447, "speed": 0})
    assert explore.stats(s)["squares"] == 1


def test_route_plan_and_phrase():
    s = Store(":memory:")
    today = datetime.now(settings.tz).date().isoformat()
    s.add_event("Dinner", today + "T19:30", None, "Marina Bay Sands", "life")
    s.add_event("Class", today + "T10:00", None, "Kaplan City Campus", "study")
    s.add_event("Call", today + "T12:00", None, "Zoom", "career")       # online: not a stop
    r = explore.plan(s, extra=["Ah Hock Kopitiam"])
    assert [x["name"] for x in r["stops"]] == ["Kaplan City Campus", "Marina Bay Sands", "Ah Hock Kopitiam"]
    assert r["stops"][0]["lat"] and r["stops"][2]["lat"] is None
    assert r["link"].startswith("https://www.google.com/maps/dir/?api=1") and "Ah%20Hock" in r["link"]
    assert explore.current_route(s)["stops"][1]["time"] == "19:30"
    assert "1. Kaplan City Campus (10:00)" in explore.describe(r)
    from jarvis import server
    assert "Orchard" in server.special("plan a route to Orchard, then Tampines Mall")[0]


def test_quests_and_map_api():
    from jarvis import quests
    trail = [[1.2816, 103.8636, 3]]                                     # walked past Gardens by the Bay
    st = {q["name"]: q for q in quests.status(trail, here=(1.2816, 103.8636))}
    assert st["Gardens by the Bay"]["done"] and not st["Pulau Ubin"]["done"]
    assert st["Pulau Ubin"]["km"] > 10 and len(quests.QUESTS) >= 40
    from fastapi.testclient import TestClient
    from jarvis import server
    c = TestClient(server.app, base_url="http://127.0.0.1:7334", client=("127.0.0.1", 5))
    d = c.get("/api/map").json()
    assert d["total"] == len(quests.QUESTS) and set(d["kinds"]) == {"food", "nature", "heritage", "views", "night"}
    r = c.post("/api/route", json={"stops": ["1.2816,103.8636", "Pulau Ubin"], "today": False}).json()
    assert [s["lat"] for s in r["stops"]] == [1.2816, 1.4045] and "google.com/maps/dir" in r["link"]
    assert c.get("/map.html").status_code == 200 and c.get("/vendor/leaflet/leaflet.js").status_code == 200
