"""Navigation inside JARVIS, trips, leave-time, day review and geocoding (network calls stubbed)."""
import json
from datetime import datetime, timedelta

import pytest

from jarvis import explore, navigate, trips
from jarvis.config import settings
from jarvis.store import Store

HOME, ODEON = (1.3496, 103.9568), (1.2963, 103.8528)


@pytest.fixture
def s(monkeypatch):
    st = Store(":memory:")
    st.set("phone:state", json.dumps({"lat": HOME[0], "lon": HOME[1], "at": datetime.now(settings.tz).isoformat()}))
    monkeypatch.setattr(explore, "geocode", lambda store, q: ODEON if "odeon" in q.lower() else None)
    monkeypatch.setattr(navigate, "raining", lambda: False)

    def fake_osrm(a, b, mode="walk"):
        km = navigate._km(a, b) * 1.3
        return {"km": round(km, 2), "min": km / (4.8 if mode == "walk" else 40) * 60, "line": [list(a), list(b)],
                "steps": [{"text": "Head off along Tampines Ave", "m": 400, "at": list(a)},
                          {"text": "Turn left onto North Bridge Road", "m": 900, "at": list(b)},
                          {"text": "You've arrived", "m": 0, "at": list(b)}]}
    monkeypatch.setattr(navigate, "osrm", fake_osrm)
    return st


def test_options_inside_jarvis(s):
    o = navigate.options(s, "Odeon Towers", arrive="23:59")
    modes = {x["mode"]: x for x in o["options"]}
    assert set(modes) == {"transit", "grab", "drive"}            # 13 km: too far to suggest walking
    lo, hi = modes["grab"]["price"]
    assert 10 <= lo < hi <= 60 and o["leave_by"] and o["routes"]["drive"]["steps"][1]["text"].startswith("Turn left")
    text = navigate.say_options(o)
    assert "Grab" in text and "$" in text and "google" not in text.lower()
    assert "couldn't find" in navigate.options(s, "Nowhereville")["error"]


def test_grab_surge_and_traffic():
    peak = datetime(2026, 11, 25, 8, 30, tzinfo=settings.tz)
    calm = datetime(2026, 11, 25, 14, 0, tzinfo=settings.tz)
    assert navigate.traffic_factor(peak) > navigate.traffic_factor(calm)
    assert navigate.grab_fare(12, 25, peak, True)[1] > navigate.grab_fare(12, 25, calm, False)[1]


def test_instructions_read_naturally():
    assert navigate.instruction({"maneuver": {"type": "turn", "modifier": "left"}, "name": "North Bridge Road"}) == "Turn left onto North Bridge Road"
    assert navigate.instruction({"maneuver": {"type": "arrive"}}) == "You've arrived"
    assert "exit 2" in navigate.instruction({"maneuver": {"type": "roundabout", "exit": 2}, "name": "X"})


def test_phrases(s, monkeypatch):
    from jarvis import server
    monkeypatch.setattr(server, "store", s)
    out = server.special("take me to Odeon Towers")[0]
    assert "Odeon Towers" in out and "Grab" in out
    assert server.NAV_RE.match("how do I get to Jewel by 18:30").group(2) == "18:30"


def test_trip_question_once(monkeypatch):
    monkeypatch.setattr("jarvis.speech.in_quiet_hours", lambda now=None: False)
    monkeypatch.setattr("jarvis.life.in_focus", lambda store: False)
    from jarvis import telegram
    monkeypatch.setattr(telegram, "ready", lambda: False)
    st = Store(":memory:")
    st.set("places:saved", json.dumps({"home": list(HOME)}))
    t = datetime(2026, 11, 25, 9, 0, tzinfo=settings.tz)
    assert trips.departure(st, *HOME, now=t) is None                                  # first fix: just remember it
    assert trips.departure(st, HOME[0] + .0005, HOME[1], now=t + timedelta(minutes=30)) is None   # still home
    left = trips.departure(st, HOME[0] + .006, HOME[1], now=t + timedelta(minutes=40))   # 650 m away: set off
    assert left == "home"
    assert "Heading out from home" in trips.ask(st, None, left, now=t + timedelta(minutes=40))
    assert trips.ask(st, None, left, now=t + timedelta(minutes=50)) is None              # once an hour at most
    assert "navigate_to" in trips.context(st, now=t + timedelta(minutes=45))


def test_day_review_and_steps():
    st = Store(":memory:")
    day = datetime.now(settings.tz).date()
    t0 = datetime(day.year, day.month, day.day, 9, 0, tzinfo=settings.tz).timestamp()
    pts = [[t0 + i * 60, HOME[0] + i * .0009, HOME[1], 10, 1.2] for i in range(10)]   # walking ~100 m a minute
    explore.add_points(st, pts)
    d = explore.day_summary(st, day)
    assert 0.6 < d["walk_km"] < 1.2 and d["steps"] > 800 and d["steps_source"] == "estimated from GPS"
    st.set(f"steps:{day.isoformat()}", "8421")
    assert explore.day_summary(st, day)["steps"] == 8421


def test_geocode_uses_onemap_and_remembers(monkeypatch):
    import importlib
    importlib.reload(explore)
    calls = []

    class R:
        def __init__(self, body): self.body = body
        def read(self): return self.body
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def fake(req, timeout=10):
        calls.append(req.full_url)
        return R(json.dumps({"results": [{"LATITUDE": "1.2963", "LONGITUDE": "103.8528", "SEARCHVAL": "ODEON TOWERS"}]}).encode())
    monkeypatch.setattr("urllib.request.urlopen", fake)
    st = Store(":memory:")
    assert explore.geocode(st, "odeon towers") == (1.2963, 103.8528)
    assert explore.geocode(st, "Odeon Towers") == (1.2963, 103.8528) and len(calls) == 1
    assert "onemap.gov.sg" in calls[0]


def _encode(points):
    """Google polyline encoder (to build OneMap-style test data)."""
    out, plat, plon = [], 0, 0
    for lat, lon in points:
        for v, prev in ((round(lat * 1e5), plat), (round(lon * 1e5), plon)):
            d = v - prev
            d = ~(d << 1) if d < 0 else d << 1
            while d >= 0x20:
                out.append(chr((0x20 | (d & 0x1f)) + 63))
                d >>= 5
            out.append(chr(d + 63))
        plat, plon = round(lat * 1e5), round(lon * 1e5)
    return "".join(out)


def test_polyline_round_trip():
    pts = [[1.3496, 103.9568], [1.3201, 103.9002], [1.2963, 103.8528]]
    assert navigate.decode_polyline(_encode(pts)) == pts


def test_real_journey_with_live_buses(monkeypatch):
    monkeypatch.setenv("JARVIS_ONEMAP_EMAIL", "me@example.com")
    monkeypatch.setenv("JARVIS_ONEMAP_PASSWORD", "pw")
    monkeypatch.setenv("JARVIS_LTA_KEY", "A" * 24)
    navigate._token.update(value="", until=0.0)
    now = datetime.now(settings.tz)
    ms = lambda m: int((now + timedelta(minutes=m)).timestamp() * 1000)   # noqa: E731
    plan = {"plan": {"itineraries": [{"duration": 1860, "startTime": ms(0), "endTime": ms(31), "fare": "1.79", "transfers": 1, "legs": [
        {"mode": "WALK", "duration": 240, "startTime": ms(0), "from": {"name": "Origin"}, "to": {"name": "Blk 201"},
         "legGeometry": {"points": _encode([[1.3496, 103.9568], [1.3490, 103.9550]])}},
        {"mode": "BUS", "route": "15", "duration": 600, "startTime": ms(5), "from": {"name": "Blk 201", "stopCode": "76191"}, "to": {"name": "Tampines Int"}},
        {"mode": "SUBWAY", "route": "EW", "duration": 900, "startTime": ms(16), "from": {"name": "TAMPINES MRT STATION"}, "to": {"name": "CITY HALL MRT STATION"}},
        {"mode": "WALK", "duration": 120, "startTime": ms(29), "from": {"name": "City Hall"}, "to": {"name": "Destination"}}]}]}}
    eta = lambda m: (now + timedelta(minutes=m, seconds=30)).isoformat()   # noqa: E731
    arrivals = {"Services": [{"ServiceNo": "15", "NextBus": {"EstimatedArrival": eta(6)}, "NextBus2": {"EstimatedArrival": eta(14)},
                             "NextBus3": {"EstimatedArrival": eta(25)}}, {"ServiceNo": "3", "NextBus": {"EstimatedArrival": eta(2)}}]}

    class R:
        def __init__(self, body): self.body = json.dumps(body).encode()
        def read(self): return self.body
        def __enter__(self): return self
        def __exit__(self, *a): return False
    seen = []

    def fake(req, timeout=10):
        url = req.full_url
        seen.append(url)
        if "getToken" in url:
            return R({"access_token": "tok"})
        if "routingsvc" in url:
            assert req.headers.get("Authorization") == "tok"
            return R(plan)
        if "BusArrival" in url:
            assert req.headers.get("Accountkey") == "A" * 24
            return R(arrivals)
        raise AssertionError(url)
    monkeypatch.setattr("urllib.request.urlopen", fake)
    t = navigate.transit(HOME, ODEON)
    bus = next(l for l in t["legs"] if l["mode"] == "BUS")
    assert bus["live"] == [6, 14, 25] and bus["route"] == "15"          # only bus 15, live
    mrt = next(l for l in t["legs"] if l["mode"] == "SUBWAY")
    assert mrt["line"] == "East-West Line" and "every" in mrt["every"]
    assert t["fare"] == "1.79" and t["min"] == 31 and len(t["line"]) == 2
    assert t["leave"] == (now + timedelta(minutes=6 - 4 - 1)).strftime("%H:%M")   # reach the stop as bus 15 comes
    said = navigate.say_transit(t)
    assert said.startswith("Leave at") and "bus 15 from Blk 201 (live: 6, 14, 25 min)" in said and "East-West Line" in said


def test_transit_setup_over_telegram(monkeypatch):
    from jarvis import telegram
    out, calls, got = [], [], []
    bot = telegram.Bot(on_text=lambda t, voice=False: "AI", on_decision=lambda *a: "", log=lambda m: None)
    bot.on_transit = lambda which, v: got.append((which, v)) or "ok"
    monkeypatch.setattr(telegram, "chat_id", lambda: "42")
    monkeypatch.setattr(telegram, "send", lambda text, *a, **k: out.append(text))
    monkeypatch.setattr(telegram, "api", lambda method, **p: calls.append((method, p)))
    msg = lambda t, i=1: {"update_id": i, "message": {"message_id": i, "text": t, "chat": {"id": 42}}}   # noqa: E731
    bot.handle(msg("/onemap"))
    assert "onemap.gov.sg" in out[-1]
    bot.handle(msg("me@gmail.com hunter22", 5))
    assert got[-1] == ("onemap", {"email": "me@gmail.com", "password": "hunter22"}) and ("deleteMessage", {"chat_id": "42", "message_id": 5}) in calls
    bot.handle(msg("/lta"))
    bot.handle(msg("AbCdEf0123456789XyZ==", 6))
    assert got[-1] == ("lta", {"key": "AbCdEf0123456789XyZ=="})
