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
def _coords(store, name: str):
    from .phonelink import places
    from .holo import place_of
    known = places(store)
    key = next((k for k in known if k.lower() == (name or "").lower().strip()), None) or place_of(name or "")
    return known.get(key) if key else None


def plan(store, day: date | None = None, extra: list[str] | None = None) -> dict:
    """Today's stops in order, with coordinates where JARVIS knows them, and a multi-stop Google Maps link."""
    from .holo import place_of
    day = day or datetime.now(settings.tz).date()
    stops = []
    for e in store.list_events(day.isoformat(), (day + timedelta(days=1)).isoformat()):
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
    if stops:
        dest = stops[-1]
        dq = f"{dest['lat']},{dest['lon']}" if dest["lat"] is not None else dest["address"]
        way = "|".join(f"{s['lat']},{s['lon']}" if s["lat"] is not None else s["address"] for s in stops[:-1])
        link = ("https://www.google.com/maps/dir/?api=1&travelmode=transit&destination=" + quote(dq)
                + (f"&waypoints={quote(way)}" if way else ""))
    out = {"date": day.isoformat(), "stops": stops, "link": link}
    store.set("route:plan", json.dumps(out))
    return out


def current_route(store) -> dict | None:
    try:
        r = json.loads(store.get("route:plan") or "null")
    except ValueError:
        return None
    return r if r and r.get("date") == datetime.now(settings.tz).date().isoformat() else None


def describe(route: dict) -> str:
    if not route["stops"]:
        return ("Nothing with a place on your calendar today, Sir. Tell me the stops: “plan a route to Orchard, "
                "then Tampines Mall”.")
    parts = [f"{i + 1}. {s['name']}" + (f" ({s['time']})" if s["time"] else "") for i, s in enumerate(route["stops"])]
    return "Your route, Sir: " + " → ".join(parts) + ". It's on the Singapore map, and I've sent the directions to your phone."


@tool("plan_route", "Plan the owner's route for a day: their calendar stops in time order (plus any extra stops, "
      "e.g. ['Orchard', 'Tampines Mall']), drawn on the Singapore holo map, with a Google Maps multi-stop link sent "
      "to the phone.", {"extra_stops": {"type": "array", "items": S}, "day": S})
def plan_route(ctx: ToolContext, extra_stops: list | None = None, day: str = "") -> dict:
    from . import phonelink
    d = date.fromisoformat(day) if re.match(r"^\d{4}-\d{2}-\d{2}$", day or "") else None
    route = plan(ctx.store, d, [str(x) for x in (extra_stops or [])])
    if route["link"]:
        phonelink.queue(ctx.store, "link", url=route["link"])
        if ctx.bus:
            ctx.bus.publish({"type": "holo", "view": "singapore"})
    return route


@tool("places_explored", "How much of Singapore the owner has explored (from their phone's location trail).")
def places_explored(ctx: ToolContext) -> dict:
    return stats(ctx.store)
