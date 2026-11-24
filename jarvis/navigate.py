"""JARVIS's own navigation: everything stays inside JARVIS (no Google Maps).

- Where: any Singapore place, building, address or postal code (OneMap, the free official map; explore.geocode).
- How: real road and footpath routes with turn-by-turn steps from the free OpenStreetMap routing servers
  (routing.openstreetmap.de: car, foot, bike), drawn on JARVIS's map and spoken during live navigation.
- Options: walk, bus/MRT, Grab and driving, each with a time; Grab with a price range; driving adjusted for the
  usual traffic at that hour; everything adjusted for rain. "Leave by" from your arrival time.
Times for bus/MRT and Grab prices are careful estimates from distance and time of day (labelled as such); with a
free LTA DataMall key they can use live bus arrivals later. Nothing here costs money."""
from __future__ import annotations

import json
import math
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta

from .config import settings
from .tools import S, ToolContext, tool

OSRM = "https://routing.openstreetmap.de/routed-{profile}/route/v1/{mode}/{a};{b}?overview=full&geometries=geojson&steps=true"
PROFILES = {"walk": ("foot", "foot"), "drive": ("car", "driving"), "cycle": ("bike", "bike")}


def _km(a, b) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def traffic_factor(when: datetime) -> float:
    """Singapore's usual traffic at that hour (weekday peaks are slow, late nights are clear)."""
    h, wd = when.hour + when.minute / 60, when.weekday()
    if wd < 5 and (7.25 <= h <= 9.75 or 17.25 <= h <= 20):
        return 1.4
    if 22 <= h or h < 6:
        return .85
    return 1.1


def raining() -> bool:
    try:
        from .hud import weather_now
        w = weather_now()
        return bool(w) and bool(re.search(r"rain|shower|thunder|drizzle", json.dumps(w), re.I))
    except Exception:  # noqa: BLE001
        return False


def grab_fare(km: float, minutes: float, when: datetime, rain: bool) -> tuple[float, float]:
    """A realistic GrabCar range for Singapore: flag-down + per km + per minute + platform fee, with the usual
    surge at peak hours and in rain. An estimate, never a quote."""
    base = 3.0 + .75 * km + .22 * minutes + .9
    surge = 1.0
    if traffic_factor(when) > 1.3:
        surge += .3
    if rain:
        surge += .35
    if when.hour >= 0 and when.hour < 6:
        surge += .25   # midnight surcharge
    low = max(6.0, base * surge * .9)
    return round(low), round(max(low + 2, base * surge * 1.2))


def osrm(a: tuple[float, float], b: tuple[float, float], mode: str = "walk") -> dict | None:
    profile, m = PROFILES[mode]
    url = OSRM.format(profile=profile, mode=m, a=f"{a[1]},{a[0]}", b=f"{b[1]},{b[0]}")
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "JARVIS personal assistant"}),
                                    timeout=12) as r:
            data = json.loads(r.read())
    except Exception:  # noqa: BLE001 - offline: estimates only
        return None
    if data.get("code") != "Ok" or not data.get("routes"):
        return None
    rt = data["routes"][0]
    steps = []
    for leg in rt.get("legs", []):
        for st in leg.get("steps", []):
            steps.append({"text": instruction(st), "m": round(st.get("distance", 0)),
                          "at": list(reversed(st["maneuver"]["location"]))})
    return {"km": round(rt["distance"] / 1000, 2), "min": rt["duration"] / 60,
            "line": [[c[1], c[0]] for c in rt["geometry"]["coordinates"]], "steps": steps}


def instruction(step: dict) -> str:
    """OSRM's maneuver -> a short spoken instruction ("Turn left onto North Bridge Road")."""
    man, road = step.get("maneuver", {}), step.get("name") or ""
    kind, mod = man.get("type", ""), (man.get("modifier") or "").replace("sharp ", "sharp ").strip()
    onto = f" onto {road}" if road else ""
    if kind == "depart":
        return f"Head off{(' along ' + road) if road else ''}"
    if kind == "arrive":
        return "You've arrived"
    if kind in ("roundabout", "rotary"):
        return f"At the roundabout, take exit {man.get('exit', 1)}{onto}"
    if mod in ("straight", ""):
        return f"Continue straight{onto}"
    if "uturn" in mod:
        return "Make a U-turn"
    return f"{'Keep' if kind in ('fork', 'merge') else 'Turn'} {mod}{onto}"


def options(store, dest: str, origin: tuple[float, float] | None = None, arrive: str = "") -> dict:
    """Ways to get there right now, with times, a Grab price range and a leave-by time. Never sends you elsewhere."""
    from . import explore, phonelink
    to = explore._coords(store, dest)
    if not to:
        return {"error": f"I couldn't find “{dest}” in Singapore. Try a building name, street or postal code."}
    if origin is None:
        st = phonelink.state(store)
        if st.get("lat") is not None:
            origin = (st["lat"], st["lon"])
        else:
            home = phonelink.places(store).get("home")
            origin = tuple(home) if home else None
    if origin is None:
        return {"error": "I don't know where you are yet: open the JARVIS app on the phone (location on)."}
    now = datetime.now(settings.tz)
    rain, tf = raining(), traffic_factor(now)
    km = _km(origin, to)
    walk = osrm(origin, to, "walk") if km <= 6 else None
    drive = osrm(origin, to, "drive")
    road_km = drive["km"] if drive else km * 1.3
    drive_min = (drive["min"] if drive else road_km / 35 * 60) * tf * (1.15 if rain else 1)
    walk_min = walk["min"] if walk else km * 1.25 / 4.8 * 60
    transit_min = 8 + road_km / 22 * 60 + (5 if rain else 0)          # walk to/from + waits + ride
    low, high = grab_fare(road_km, drive_min, now, rain)
    opts = []
    if walk_min <= 45:
        opts.append({"mode": "walk", "icon": "🚶", "label": "Walk", "min": round(walk_min), "km": walk["km"] if walk else round(km * 1.25, 1),
                     "note": "rain: umbrella" if rain else "", "exact": bool(walk)})
    opts.append({"mode": "transit", "icon": "🚇", "label": "Bus / MRT", "min": round(transit_min), "note": "estimate", "exact": False})
    opts.append({"mode": "grab", "icon": "🚕", "label": "Grab", "min": round(drive_min + 4), "price": [low, high],
                 "note": ("surge likely" if low > 3.0 + .75 * road_km + 3 else ""), "exact": bool(drive)})
    opts.append({"mode": "drive", "icon": "🚗", "label": "Drive", "min": round(drive_min), "km": round(road_km, 1),
                 "note": "peak traffic" if tf > 1.3 else "", "exact": bool(drive)})
    best = min(opts, key=lambda o: o["min"] + (o.get("price", [0])[0] / 4))
    leave = None
    m = re.match(r"^\s*(\d{1,2})[:.](\d{2})\s*$", arrive or "")
    if m:
        at = now.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
        if at < now:
            at += timedelta(days=1)
        leave = (at - timedelta(minutes=best["min"] + 8)).strftime("%H:%M")   # 8 minutes' buffer
    return {"to": dest, "to_at": list(to), "from_at": list(origin), "km": round(km, 1), "rain": rain,
            "traffic": "heavy" if tf > 1.3 else "light" if tf < 1 else "normal", "options": opts, "best": best["mode"],
            "leave_by": leave, "routes": {"walk": walk, "drive": drive}}


def say_options(o: dict) -> str:
    if "error" in o:
        return o["error"]
    parts = []
    for x in o["options"]:
        s = f"{x['label']} {x['min']} min"
        if x.get("price"):
            s += f" (about ${x['price'][0]}–{x['price'][1]})"
        parts.append(s)
    best = next(x for x in o["options"] if x["mode"] == o["best"])
    lead = f"To {o['to']}: " + ", ".join(parts) + f". Best right now: {best['label'].lower()}."
    if o.get("leave_by"):
        lead += f" Leave by {o['leave_by']}."
    if o["rain"]:
        lead += " It's raining, so I've allowed extra time."
    return lead


def map_link(dest: str) -> str:
    """JARVIS's own map with the route open (never Google)."""
    base = (settings.app_url or "").rstrip("/")
    return f"{base}/map.html?nav=" + urllib.parse.quote(dest)


@tool("navigate_to", "Plan how the owner gets somewhere, inside JARVIS (never Google Maps): walk, bus/MRT, Grab "
      "(with a price range) and driving, with times for the current traffic and weather, and a leave-by time if "
      "they give an arrival time (HH:MM). Opens the route on JARVIS's map on their phone.",
      {"destination": S, "arrive_by": S}, ["destination"])
def navigate_to(ctx: ToolContext, destination: str, arrive_by: str = "") -> dict:
    from . import phonelink
    o = options(ctx.store, destination, arrive=arrive_by)
    if "error" in o:
        return o
    if phonelink.online(ctx.store):
        phonelink.queue(ctx.store, "open", url="/map.html?nav=" + urllib.parse.quote(destination),
                        title="JARVIS · route ready", text=f"Tap for directions to {destination}")
    o.pop("routes", None)
    return {"summary": say_options(o), "options": o["options"], "leave_by": o["leave_by"], "open_on_phone": phonelink.online(ctx.store)}
