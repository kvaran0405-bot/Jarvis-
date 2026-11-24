"""Places you've been and routes for your day.

The trail: every phone check-in with a location lights up a ~300 m square on the Singapore map (stored on the
laptop only), so the map shows where you've really been, not just famous landmarks.
Route planning: today's stops (calendar events with a place, in time order, plus any extra stops) drawn on the map,
with a Google Maps link that starts multi-stop directions on the phone."""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from urllib.parse import quote

from .config import settings
from .tools import S, ToolContext, tool

CELL = 0.003   # degrees, about 330 m


def _ensure(store) -> None:
    store.execute("CREATE TABLE IF NOT EXISTS trail (cell TEXT PRIMARY KEY, lat REAL, lon REAL, first TEXT, "
                  "last TEXT, visits INTEGER DEFAULT 1)")


def record(store, lat: float, lon: float, now: datetime | None = None) -> bool:
    """Light up the square the phone is in. A new visit counts if you were last there 2+ hours ago.
    Returns True when it's a square you've never been to."""
    if not (1.1 < lat < 1.5 and 103.5 < lon < 104.1):
        return False   # outside Singapore: not drawn on this map
    _ensure(store)
    now = now or datetime.now(settings.tz)
    clat, clon = round(round(lat / CELL) * CELL, 4), round(round(lon / CELL) * CELL, 4)
    cell = f"{clat:.4f},{clon:.4f}"
    row = store.query("SELECT last, visits FROM trail WHERE cell = ?", (cell,))
    if not row:
        store.execute("INSERT INTO trail (cell, lat, lon, first, last) VALUES (?, ?, ?, ?, ?)",
                      (cell, clat, clon, now.isoformat(), now.isoformat()))
        return True
    if datetime.fromisoformat(row[0]["last"]) < now - timedelta(hours=2):
        store.execute("UPDATE trail SET visits = visits + 1, last = ? WHERE cell = ?", (now.isoformat(), cell))
    else:
        store.execute("UPDATE trail SET last = ? WHERE cell = ?", (now.isoformat(), cell))
    return False


def trail(store, limit: int = 4000) -> list[list[float]]:
    _ensure(store)
    return [[r["lat"], r["lon"], r["visits"]] for r in
            store.query("SELECT lat, lon, visits FROM trail ORDER BY last DESC LIMIT ?", (limit,))]


def stats(store) -> dict:
    _ensure(store)
    r = store.query("SELECT COUNT(*) AS n, MIN(first) AS since FROM trail")[0]
    return {"squares": r["n"], "km2": round(r["n"] * 0.109, 1), "since": (r["since"] or "")[:10]}


# ------------------------------------------------------------------ route planning
def geocode(store, query: str):
    """Any Singapore place, building, address or postal code -> (lat, lon), via OneMap (the free official
    Singapore map, no key needed). Answers are remembered, so each place is looked up once."""
    import json as _json
    import urllib.parse
    import urllib.request
    q = re.sub(r"\s+", " ", (query or "")).strip()
    if len(q) < 3:
        return None
    key = "geo:" + q.lower()
    if (hit := store.get(key)) is not None:
        try:
            v = _json.loads(hit)
            return tuple(v) if v else None
        except ValueError:
            pass
    url = ("https://www.onemap.gov.sg/api/common/elastic/search?returnGeom=Y&getAddrDetails=Y&pageNum=1&searchVal="
           + urllib.parse.quote(q))
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "JARVIS personal assistant"}),
                                    timeout=10) as r:
            res = _json.loads(r.read()).get("results") or []
    except Exception:  # noqa: BLE001 - offline: try again next time
        return None
    out = (float(res[0]["LATITUDE"]), float(res[0]["LONGITUDE"])) if res else None
    store.set(key, _json.dumps(list(out) if out else None))
    return out


def _coords(store, name: str):
    from .phonelink import places
    from .holo import place_of
    from .quests import QUESTS
    m = re.match(r"^\s*(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)\s*$", name or "")
    if m:
        return float(m.group(1)), float(m.group(2))
    known = places(store)
    known.update({q[0]: (q[2], q[3]) for q in QUESTS})
    key = next((k for k in known if k.lower() == (name or "").lower().strip()), None) or place_of(name or "")
    return known.get(key) if key else geocode(store, name)


def plan(store, day: date | None = None, extra: list[str] | None = None, include_calendar: bool = True) -> dict:
    """Today's stops in order, with coordinates where JARVIS knows them, and a multi-stop Google Maps link."""
    from .holo import place_of
    day = day or datetime.now(settings.tz).date()
    stops = []
    for e in (store.list_events(day.isoformat(), (day + timedelta(days=1)).isoformat()) if include_calendar else []):
        loc = (e.get("location") or "").strip()
        if len(e["start"]) <= 10 or not loc or re.search(r"zoom|teams|online|meet\.google", loc, re.I):
            continue
        name = place_of(f"{e['title']} {loc}") or loc
        stops.append({"name": name, "address": loc, "title": e["title"], "time": e["start"][11:16]})
    for x in extra or []:
        if x.strip():
            stops.append({"name": x.strip(), "address": x.strip(), "title": "", "time": ""})
    for s in stops:
        c = _coords(store, s["name"]) or _coords(store, s["address"])
        s["lat"], s["lon"] = (c[0], c[1]) if c else (None, None)
    link = ""
    if stops:   # JARVIS's own map shows today's route (never Google Maps)
        link = (settings.app_url or "").rstrip("/") + "/map.html?route=today"
    out = {"date": day.isoformat(), "stops": stops, "link": link}
    store.set("route:plan", json.dumps(out))
    return out


def current_route(store) -> dict | None:
    try:
        r = json.loads(store.get("route:plan") or "null")
    except ValueError:
        return None
    return r if r and r.get("date") == datetime.now(settings.tz).date().isoformat() else None


def send_route(store, route: dict) -> list[str]:
    """Get the directions to the owner's phone for real: Telegram (always reaches the phone) + the phone app.
    Returns where it actually went, so JARVIS never claims "sent" when it wasn't."""
    from . import phonelink
    from . import telegram as tg
    went = []
    if not route.get("link"):
        return went
    if tg.ready():
        try:
            tg.send("🧭 " + " → ".join(s["name"] for s in route["stops"])
                    + ("\nOpen it on JARVIS's map:\n" + route["link"] if route["link"].startswith("http") else ""))
            went.append("Telegram")
        except Exception:  # noqa: BLE001
            pass
    if phonelink.online(store):
        phonelink.queue(store, "open", url="/map.html?route=today", title="JARVIS · today's route",
                        text=" → ".join(s["name"] for s in route["stops"]))
        went.append("phone")
    return went


def describe(route: dict, went: list[str] | None = None) -> str:
    if not route["stops"]:
        return ("Nothing with a place on your calendar today, Sir. Tell me the stops: “plan a route to Orchard, "
                "then Tampines Mall”.")
    parts = [f"{i + 1}. {s['name']}" + (f" ({s['time']})" if s["time"] else "") for i, s in enumerate(route["stops"])]
    lost = [s["name"] for s in route["stops"] if s.get("lat") is None]
    where_to = (" It's on JARVIS's map, and I've sent it to your " + " and ".join(went) + "." if went else
                " It's on JARVIS's map.")
    return ("Your route, Sir: " + " → ".join(parts) + "." + where_to
            + (f" (I couldn't find {', '.join(lost)} on the map; try the building name or postal code.)" if lost else ""))


@tool("plan_route", "Plan the owner's route for a day: their calendar stops in time order (plus any extra stops, "
      "e.g. ['Orchard', 'Tampines Mall']), drawn on the Singapore holo map, with a Google Maps multi-stop link sent "
      "to the phone.", {"extra_stops": {"type": "array", "items": S}, "day": S})
def plan_route(ctx: ToolContext, extra_stops: list | None = None, day: str = "") -> dict:
    from . import phonelink
    d = date.fromisoformat(day) if re.match(r"^\d{4}-\d{2}-\d{2}$", day or "") else None
    route = plan(ctx.store, d, [str(x) for x in (extra_stops or [])])
    route["sent_to"] = send_route(ctx.store, route)
    if ctx.bus and route["link"]:
        ctx.bus.publish({"type": "open_page", "url": "/map.html"})
    return route


@tool("places_explored", "How much of Singapore the owner has explored (from their phone's location trail).")
def places_explored(ctx: ToolContext) -> dict:
    return stats(ctx.store)


# ------------------------------------------------------------------ location history (timeline)
KEEP_DAYS = 120


def _ensure_locs(store) -> None:
    store.execute("CREATE TABLE IF NOT EXISTS locs (ts REAL PRIMARY KEY, lat REAL, lon REAL, acc REAL, speed REAL)")


def add_points(store, points: list) -> int:
    """Points from the phone: [unix_seconds, lat, lon, accuracy_m, speed_mps]. Also lights up the trail."""
    _ensure_locs(store)
    n = 0
    now = datetime.now(settings.tz).timestamp()
    for p in (points or [])[:2000]:
        try:
            ts, lat, lon = float(p[0]), float(p[1]), float(p[2])
            acc = float(p[3]) if len(p) > 3 else -1
            speed = float(p[4]) if len(p) > 4 else -1
        except (TypeError, ValueError, IndexError):
            continue
        if not (-90 <= lat <= 90 and -180 <= lon <= 180) or ts > now + 300 or ts < now - KEEP_DAYS * 86400:
            continue
        store.execute("INSERT OR IGNORE INTO locs (ts, lat, lon, acc, speed) VALUES (?, ?, ?, ?, ?)", (ts, lat, lon, acc, speed))
        record(store, lat, lon, datetime.fromtimestamp(ts, settings.tz))
        n += 1
    if n:
        store.execute("DELETE FROM locs WHERE ts < ?", (now - KEEP_DAYS * 86400,))
    return n


def path(store, day: date | None = None) -> list[list[float]]:
    """The day's movements, in order: [[unix_seconds, lat, lon], ...]."""
    _ensure_locs(store)
    day = day or datetime.now(settings.tz).date()
    start = datetime(day.year, day.month, day.day, tzinfo=settings.tz).timestamp()
    return [[r["ts"], r["lat"], r["lon"]] for r in
            store.query("SELECT ts, lat, lon FROM locs WHERE ts >= ? AND ts < ? ORDER BY ts", (start, start + 86400))]


def parse_when(text: str, now: datetime | None = None) -> datetime | None:
    """'yesterday 3pm', 'today 09:30', '2026-11-20 14:00', '3pm', 'monday 8pm' -> a time."""
    now = now or datetime.now(settings.tz)
    t = (text or "").strip().lower()
    try:
        d = datetime.fromisoformat(t)
        return d if d.tzinfo else d.replace(tzinfo=settings.tz)
    except ValueError:
        pass
    day = now.date()
    if "yesterday" in t:
        day -= timedelta(days=1)
    else:
        for i, name in enumerate(["mon", "tue", "wed", "thu", "fri", "sat", "sun"]):
            if re.search(rf"\b{name}", t):
                back = (now.weekday() - i) % 7 or 7
                day -= timedelta(days=back)
    m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", t)
    if not m:
        return datetime(day.year, day.month, day.day, 12, tzinfo=settings.tz) if day != now.date() else None
    h, mi = int(m.group(1)), int(m.group(2) or 0)
    if m.group(3) == "pm" and h < 12:
        h += 12
    if m.group(3) == "am" and h == 12:
        h = 0
    if h > 23 or mi > 59:
        return None
    return datetime(day.year, day.month, day.day, h, mi, tzinfo=settings.tz)


def where_at(store, when: datetime) -> dict | None:
    _ensure_locs(store)
    ts = when.timestamp()
    rows = store.query("SELECT ts, lat, lon FROM locs WHERE ts BETWEEN ? AND ? ORDER BY ABS(ts - ?) LIMIT 1",
                       (ts - 3 * 3600, ts + 3 * 3600, ts))
    if not rows:
        return None
    r = rows[0]
    from .phonelink import where
    return {"time": datetime.fromtimestamp(r["ts"], settings.tz).isoformat(timespec="minutes"),
            "lat": r["lat"], "lon": r["lon"], "place": where(store, r["lat"], r["lon"], 0.5),
            "map": f"https://maps.google.com/?q={r['lat']},{r['lon']}",
            "minutes_off": round(abs(r["ts"] - ts) / 60)}


@tool("where_was_i", "Where the owner was at a time, from their phone's location history (kept on the laptop only). "
      "when: e.g. 'yesterday 3pm', 'monday 8pm', 'today 10:30', or an ISO time.", {"when": S}, ["when"])
def where_was_i(ctx: ToolContext, when: str) -> dict:
    t = parse_when(when)
    if t is None:
        return {"error": "Give a time, e.g. 'yesterday 3pm'."}
    found = where_at(ctx.store, t)
    return found or {"error": f"No location recorded around {t:%a %d %b %H:%M} (the phone app needs location on)."}


@tool("my_day_path", "The owner's movements on a day (from the phone's location history): places in order with times.",
      {"day": S})
def my_day_path(ctx: ToolContext, day: str = "") -> dict:
    from .phonelink import where
    d = date.fromisoformat(day) if re.match(r"^\d{4}-\d{2}-\d{2}$", day or "") else (parse_when(day) or datetime.now(settings.tz)).date()
    stops, last = [], None
    for ts, lat, lon in path(ctx.store, d):
        name = where(ctx.store, lat, lon, 0.4)
        if name and name != last:
            stops.append({"time": datetime.fromtimestamp(ts, settings.tz).strftime("%H:%M"), "place": name})
            last = name
    return {"day": d.isoformat(), "points": len(path(ctx.store, d)), "places": stops}


# ------------------------------------------------------------------ the day in review (map replay + nightly stats)
def _m(a, b) -> float:
    import math
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(h))


def steps_on(store, day: date) -> int | None:
    """Real steps from the phone's step counter, if it reported them that day."""
    v = store.get(f"steps:{day.isoformat()}")
    return int(v) if v and v.isdigit() else None


def day_summary(store, day: date | None = None) -> dict:
    """Everything about one day's movement: the path (with times), km travelled, km walked, steps, minutes on the
    move, and the places in order. Walking = moving at under 8 km/h; faster is a vehicle."""
    from .phonelink import where
    day = day or datetime.now(settings.tz).date()
    pts = path(store, day)
    total = walk = moving_s = 0.0
    for (t1, la1, lo1), (t2, la2, lo2) in zip(pts, pts[1:]):
        dt = t2 - t1
        if dt <= 0 or dt > 30 * 60:   # a long gap is not one journey
            continue
        d = _m((la1, lo1), (la2, lo2))
        if d < 25:   # GPS wobble while standing still
            continue
        total += d
        speed = d / dt
        if speed < 2.2:
            walk += d
        moving_s += dt
    places, last = [], None
    for ts, lat, lon in pts:
        name = where(store, lat, lon, 0.35)
        if name and name != last:
            places.append({"time": datetime.fromtimestamp(ts, settings.tz).strftime("%H:%M"), "place": name})
            last = name
    real = steps_on(store, day)
    return {"date": day.isoformat(), "path": [[p[0], p[1], p[2]] for p in pts],
            "km": round(total / 1000, 1), "walk_km": round(walk / 1000, 1),
            "steps": real if real is not None else int(walk / 0.75),
            "steps_source": "phone step counter" if real is not None else "estimated from GPS",
            "moving_min": round(moving_s / 60), "places": places}


@tool("my_day_review", "The owner's day of movement: where they went (in order, with times), km travelled, km walked, "
      "steps and minutes on the move. day: 'today', 'yesterday' or YYYY-MM-DD.", {"day": S})
def my_day_review(ctx: ToolContext, day: str = "today") -> dict:
    d = date.fromisoformat(day) if re.match(r"^\d{4}-\d{2}-\d{2}$", day or "") else \
        (parse_when(day + " 12:00") or datetime.now(settings.tz)).date() if day and day != "today" else None
    out = day_summary(ctx.store, d)
    out.pop("path")
    return out
