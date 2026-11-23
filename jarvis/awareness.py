"""Live awareness: what JARVIS knows about the owner's situation right now, gathered automatically from the phone,
the calendar and the laptop, and given to every agent before every reply. The owner never has to tell JARVIS where
they are, where they've been, or how their day is going."""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta

from .config import settings
from .tools import ToolContext, tool

_cache: dict = {"at": 0.0, "text": ""}


def _ago(iso: str | None) -> str:
    if not iso:
        return "unknown"
    mins = int((datetime.now(settings.tz) - datetime.fromisoformat(iso)).total_seconds() // 60)
    return "just now" if mins < 2 else f"{mins} min ago" if mins < 90 else f"{mins // 60} h ago"


def time_at_places(store, days: int = 7) -> dict[str, float]:
    """Hours spent at each named place (home, gym, campus, venues...), worked out from the location history."""
    from . import explore
    from .phonelink import where
    explore._ensure_locs(store)
    since = (datetime.now(settings.tz) - timedelta(days=days)).timestamp()
    rows = store.query("SELECT ts, lat, lon FROM locs WHERE ts >= ? ORDER BY ts", (since,))
    hours: dict[str, float] = {}
    for a, b in zip(rows, rows[1:]):
        gap = b["ts"] - a["ts"]
        if gap > 45 * 60:   # phone off or no fix for a long time: don't count it
            continue
        place = where(store, a["lat"], a["lon"], 0.35)
        if place:
            hours[place] = hours.get(place, 0) + gap / 3600
    return {k: round(v, 1) for k, v in sorted(hours.items(), key=lambda x: -x[1]) if v >= 0.1}


def last_screen_time(store) -> dict | None:
    from .phonelink import _ensure
    _ensure(store)
    rows = store.query("SELECT result, created FROM phone_cmds WHERE kind = 'screentime' AND status = 'done' "
                       "ORDER BY id DESC LIMIT 1")
    if not rows:
        return None
    try:
        data = json.loads(rows[0]["result"])
        return data if isinstance(data, dict) and "apps" in data else None
    except ValueError:
        return None


def situation(store) -> str:
    """A few lines for the agents' context. Cached for a minute (it's built before every reply)."""
    if time.time() - _cache["at"] < 60:
        return _cache["text"]
    lines = []
    try:
        from . import explore, phonelink
        st = phonelink.state(store)
        now = datetime.now(settings.tz)
        if st.get("lat") is not None:
            place = phonelink.where(store, st["lat"], st["lon"], 0.4)
            moving = (st.get("speed") or 0) * 3.6
            lines.append(f"- Phone location: {place or 'not at a named place'} ({st['lat']:.4f},{st['lon']:.4f}), "
                         f"updated {_ago(st.get('loc_at') or st.get('at'))}"
                         + (f", moving ~{moving:.0f} km/h" if moving > 6 else ""))
        if st.get("battery") is not None:
            lines.append(f"- Phone battery {st['battery']}%{' (charging)' if st.get('charging') else ''}, "
                         f"last check-in {_ago(st.get('at'))}")
        seen, last = [], None
        for ts, lat, lon in explore.path(store):
            name = phonelink.where(store, lat, lon, 0.4)
            if name and name != last:
                seen.append(f"{datetime.fromtimestamp(ts, settings.tz):%H:%M} {name}")
                last = name
        if seen:
            lines.append("- Places today: " + " → ".join(seen[-8:]))
        week = time_at_places(store, 7)
        if week:
            lines.append("- Time at places, last 7 days: " + ", ".join(f"{k} {v}h" for k, v in list(week.items())[:6]))
        nxt = next((e for e in store.list_events(now.date().isoformat(), (now.date() + timedelta(days=2)).isoformat())
                    if len(e["start"]) > 10 and e["start"] >= now.replace(tzinfo=None).isoformat(timespec="minutes")), None)
        if nxt:
            lines.append(f"- Next: {nxt['title']} at {nxt['start'][:16].replace('T', ' ')}"
                         + (f" ({nxt['location']})" if nxt.get("location") else ""))
        scr = last_screen_time(store)
        if scr:
            lines.append(f"- Phone screen time (last report): {scr.get('total_minutes', 0) // 60}h"
                         f"{scr.get('total_minutes', 0) % 60:02d}m; top: "
                         + ", ".join(f"{a['app']} {a['minutes']}m" for a in scr["apps"][:3]))
        urgent = store.query("SELECT COUNT(*) AS n FROM phone_notes WHERE urgent = 1 AND created >= ?",
                             ((now - timedelta(hours=3)).isoformat(),))
        if urgent and urgent[0]["n"]:
            lines.append(f"- {urgent[0]['n']} urgent phone message(s) in the last 3 hours")
    except Exception:  # noqa: BLE001 - awareness must never break a reply
        pass
    text = ("Live situation (gathered automatically; use it, don't ask the owner for it):\n" + "\n".join(lines) + "\n"
            if lines else "")
    _cache.update(at=time.time(), text=text)
    return text


@tool("time_at_places", "How many hours the owner spent at each place (home, gym, campus, venues...) over the last N "
      "days, worked out automatically from their phone's location.", {"days": {"type": "integer"}})
def time_at_places_tool(ctx: ToolContext, days: int = 7) -> dict:
    return {"days": days, "hours": time_at_places(ctx.store, max(1, min(int(days), 120)))}
