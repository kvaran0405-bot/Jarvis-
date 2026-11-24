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
    transit_min = 8 + road_km / 22 * 60 + (5 if rain else 0)          # walk to/from + waits + ride (estimate)
    arrive_dt = None
    m_arr = re.match(r"^\s*(\d{1,2})[:.](\d{2})\s*$", arrive or "")
    if m_arr:
        arrive_dt = now.replace(hour=int(m_arr.group(1)), minute=int(m_arr.group(2)), second=0, microsecond=0)
        if arrive_dt < now:
            arrive_dt += timedelta(days=1)
    real = transit(origin, to, arrive_dt)
    if real:
        transit_min = real["min"]
    low, high = grab_fare(road_km, drive_min, now, rain)
    opts = []
    if walk_min <= 45:
        opts.append({"mode": "walk", "icon": "🚶", "label": "Walk", "min": round(walk_min), "km": walk["km"] if walk else round(km * 1.25, 1),
                     "note": "rain: umbrella" if rain else "", "exact": bool(walk)})
    opts.append({"mode": "transit", "icon": "🚇", "label": "Bus / MRT", "min": round(transit_min),
                 "note": (f"leave {real['leave']}" + (f" · ${real['fare']}" if real.get("fare") else "")) if real else "estimate",
                 "exact": bool(real)})
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
    if real and best["mode"] == "transit":
        leave = real["leave"]
    return {"transit": real, "transit_live": bool(real) and lta_ready(), "transit_setup": not onemap_ready(),
            "to": dest, "to_at": list(to), "from_at": list(origin), "km": round(km, 1), "rain": rain,
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
    if o.get("transit"):
        lead += " By bus/MRT: " + say_transit(o["transit"])
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


# ------------------------------------------------------------------ real public transport (OneMap + LTA, both free)
ONEMAP_TOKEN_URL = "https://www.onemap.gov.sg/api/auth/post/getToken"
ONEMAP_ROUTE_URL = "https://www.onemap.gov.sg/api/public/routingsvc/route"
LTA_ARRIVAL_URL = "https://datamall2.mytransport.sg/ltaodataservice/v3/BusArrival?BusStopCode="
LINES = {"EW": "East-West Line", "NS": "North-South Line", "NE": "North East Line", "CC": "Circle Line",
         "DT": "Downtown Line", "TE": "Thomson-East Coast Line", "BP": "Bukit Panjang LRT", "SE": "Sengkang LRT",
         "PE": "Punggol LRT", "CG": "Changi Airport branch"}
_token = {"value": "", "until": 0.0}


def onemap_ready() -> bool:
    import os
    return bool(os.environ.get("JARVIS_ONEMAP_EMAIL") and os.environ.get("JARVIS_ONEMAP_PASSWORD"))


def lta_ready() -> bool:
    import os
    return bool(os.environ.get("JARVIS_LTA_KEY"))


def _onemap_token() -> str:
    import os
    import time
    if _token["value"] and time.time() < _token["until"]:
        return _token["value"]
    body = json.dumps({"email": os.environ.get("JARVIS_ONEMAP_EMAIL", ""),
                       "password": os.environ.get("JARVIS_ONEMAP_PASSWORD", "")}).encode()
    req = urllib.request.Request(ONEMAP_TOKEN_URL, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=12) as r:
        data = json.loads(r.read())
    _token.update(value=data["access_token"], until=time.time() + 2.5 * 86400)   # tokens last 3 days
    return _token["value"]


def decode_polyline(s: str) -> list[list[float]]:
    """Google-style encoded polyline (what OneMap returns) -> [[lat, lon], ...]."""
    pts, i, lat, lon = [], 0, 0, 0
    while i < len(s):
        for which in (0, 1):
            shift = result = 0
            while True:
                b = ord(s[i]) - 63
                i += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            d = ~(result >> 1) if result & 1 else result >> 1
            if which == 0:
                lat += d
            else:
                lon += d
        pts.append([lat / 1e5, lon / 1e5])
    return pts


def bus_arrivals(stop_code: str, service: str = "") -> list[int]:
    """Live minutes until the next buses (LTA DataMall). [] when not available."""
    import os
    if not (lta_ready() and stop_code):
        return []
    req = urllib.request.Request(LTA_ARRIVAL_URL + urllib.parse.quote(str(stop_code)),
                                 headers={"AccountKey": os.environ["JARVIS_LTA_KEY"], "accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
    except Exception:  # noqa: BLE001
        return []
    now = datetime.now(settings.tz)
    out = []
    for svc in data.get("Services", []):
        if service and svc.get("ServiceNo") != service:
            continue
        for k in ("NextBus", "NextBus2", "NextBus3"):
            eta = (svc.get(k) or {}).get("EstimatedArrival")
            if eta:
                mins = int((datetime.fromisoformat(eta) - now).total_seconds() // 60)
                if mins >= 0:
                    out.append(mins)
        if service:
            break
    return sorted(out)[:3]


def train_every(when: datetime) -> str:
    h, wd = when.hour + when.minute / 60, when.weekday()
    if wd < 5 and (7 <= h <= 9.5 or 17 <= h <= 20):
        return "every 2–3 min"
    return "every 4–7 min" if 6 <= h < 23 else "every 7–10 min (last trains around 23:30–00:30)"


def transit(origin, dest, arrive: datetime | None = None) -> dict | None:
    """The real bus/MRT journey (OneMap), with live bus arrivals for the first bus (LTA). None if not set up."""
    if not onemap_ready():
        return None
    now = datetime.now(settings.tz)
    when = arrive or now
    q = urllib.parse.urlencode({"start": f"{origin[0]},{origin[1]}", "end": f"{dest[0]},{dest[1]}", "routeType": "pt",
                                "date": when.strftime("%m-%d-%Y"), "time": when.strftime("%H:%M:%S"), "mode": "TRANSIT",
                                "maxWalkDistance": 1000, "numItineraries": 3, "arriveBy": "true" if arrive else "false"})
    try:
        req = urllib.request.Request(f"{ONEMAP_ROUTE_URL}?{q}", headers={"Authorization": _onemap_token()})
        with urllib.request.urlopen(req, timeout=15) as r:
            plan = json.loads(r.read()).get("plan") or {}
    except Exception:  # noqa: BLE001
        return None
    its = plan.get("itineraries") or []
    if not its:
        return None
    it = min(its, key=lambda x: x.get("duration", 1e9))
    legs, line, first_bus = [], [], None
    for lg in it.get("legs", []):
        mode = lg.get("mode", "")
        start = datetime.fromtimestamp(lg.get("startTime", 0) / 1000, settings.tz)
        frm, to = lg.get("from", {}), lg.get("to", {})
        leg = {"mode": mode, "min": round(lg.get("duration", 0) / 60), "from": frm.get("name", ""), "to": to.get("name", ""),
               "at": start.strftime("%H:%M"), "route": lg.get("route") or lg.get("routeShortName") or ""}
        if mode == "BUS":
            leg["stop"] = frm.get("stopCode", "")
            leg["live"] = bus_arrivals(leg["stop"], leg["route"])
            first_bus = first_bus or leg
        elif mode in ("SUBWAY", "RAIL", "TRAM"):
            code = re.match(r"[A-Z]{2}", leg["route"] or "")
            leg["line"] = LINES.get(code.group(0) if code else "", leg["route"] or "MRT")
            leg["every"] = train_every(start)
        pts = (lg.get("legGeometry") or {}).get("points")
        if pts:
            line += decode_polyline(pts)
        legs.append(leg)
    start = datetime.fromtimestamp(it.get("startTime", 0) / 1000, settings.tz)
    end = datetime.fromtimestamp(it.get("endTime", 0) / 1000, settings.tz)
    leave = start
    if first_bus and first_bus.get("live") and not arrive:   # leave so you reach the stop as the bus comes
        walk_before = sum(x["min"] for x in legs[:legs.index(first_bus)] if x["mode"] == "WALK")
        nxt = next((m for m in first_bus["live"] if m >= walk_before + 1), None)
        if nxt is not None:
            leave = now + timedelta(minutes=nxt - walk_before - 1)
    return {"min": round(it.get("duration", 0) / 60), "leave": leave.strftime("%H:%M"), "arrive": end.strftime("%H:%M"),
            "fare": it.get("fare", ""), "transfers": it.get("transfers", 0), "legs": legs, "line": line}


def say_transit(t: dict) -> str:
    """'Leave at 18:34. Walk 4 min to Blk 201, bus 15 (live: 3, 14 min), East-West Line from Tampines, arrive 19:05.'"""
    bits = []
    for lg in t["legs"]:
        if lg["mode"] == "WALK":
            if lg["min"] >= 2:
                bits.append(f"walk {lg['min']} min" + (f" to {lg['to']}" if lg["to"] else ""))
        elif lg["mode"] == "BUS":
            live = f" (live: {', '.join(str(m) for m in lg['live'])} min)" if lg.get("live") else ""
            bits.append(f"bus {lg['route']} from {lg['from']}{live}")
        else:
            bits.append(f"{lg.get('line', 'MRT')} from {lg['from']} to {lg['to']}, trains {lg.get('every', '')}")
    fare = f" Fare about ${t['fare']}." if t.get("fare") else ""
    return f"Leave at {t['leave']}: " + ", ".join(bits) + f". Arrive {t['arrive']}.{fare}"
