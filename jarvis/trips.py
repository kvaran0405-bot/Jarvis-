"""Trips: JARVIS notices when the owner sets off somewhere and asks where they're heading, so the route, the time
to leave and the travel options are ready inside JARVIS. Asks once per trip (after being somewhere at least 15
minutes and then moving 300 m+), never at quiet hours or in focus, and at most once an hour."""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta

from .config import settings

STILL_MIN = 15      # minutes somewhere before a departure counts
LEFT_M = 300        # metres from that spot = setting off
GAP_MIN = 60        # at most one question an hour


def _m(a, b) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(h))


def departure(store, lat: float, lon: float, now: datetime | None = None) -> str | None:
    """Returns the name of the place just left ("" if unnamed) when the owner has set off, else None."""
    from .phonelink import where
    now = now or datetime.now(settings.tz)
    st = json.loads(store.get("trip:still") or "null")
    if not st:
        store.set("trip:still", json.dumps({"lat": lat, "lon": lon, "since": now.isoformat()}))
        return None
    d = _m((st["lat"], st["lon"]), (lat, lon))
    if d < 150:
        return None   # still here
    stayed = now - datetime.fromisoformat(st["since"])
    store.set("trip:still", json.dumps({"lat": lat, "lon": lon, "since": now.isoformat()}))
    if d < LEFT_M or stayed < timedelta(minutes=STILL_MIN):
        return None
    return where(store, st["lat"], st["lon"], 0.35) or ""


def ask(store, bus, left: str, now: datetime | None = None) -> str | None:
    from .life import in_focus
    from .speech import in_quiet_hours
    now = now or datetime.now(settings.tz)
    last = store.get("trip:asked_at")
    if last and now - datetime.fromisoformat(last) < timedelta(minutes=GAP_MIN):
        return None
    if in_quiet_hours() or in_focus(store) or (store.get("trips:on") or "on") == "off":
        return None
    store.set("trip:asked_at", now.isoformat())
    msg = (f"Heading out{(' from ' + left) if left else ''}, Sir? Tell me where you're going and I'll have the route, "
           "the best way there and when you'll arrive ready.")
    from . import phonelink
    from . import telegram as tg
    phonelink.queue(store, "notify", title="JARVIS · where to?", text=msg, url="/map.html")
    if tg.ready():
        try:
            tg.send(msg)
            store.set("telegram:last_agent", f"JARVIS|{now.isoformat()}")   # the answer comes back to JARVIS
        except Exception:  # noqa: BLE001
            pass
    if bus is not None:
        bus.log("JARVIS", "🧭 " + msg, "reply")
    return msg


def on_location(store, bus, lat: float, lon: float) -> str | None:
    left = departure(store, lat, lon)
    return ask(store, bus, left) if left is not None else None


def context(store, now: datetime | None = None) -> str:
    """For the agents: if JARVIS just asked where the owner is going, their next message is probably the answer."""
    now = now or datetime.now(settings.tz)
    last = store.get("trip:asked_at")
    if last and now - datetime.fromisoformat(last) < timedelta(minutes=45):
        return ("- You asked the owner where they're heading at " + last[11:16] + ". If their message names a place, "
                "call navigate_to with it right away and tell them the best way, the time and when to leave.")
    return ""
