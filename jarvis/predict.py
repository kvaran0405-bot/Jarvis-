"""Predictive JARVIS (#69): he learns your routines and speaks up before you ask.

From the phone's location history (the last 6 weeks), JARVIS works out trips you make regularly: "home → gym around
18:10 on Tuesdays and Thursdays", "home → SMU around 08:40 on weekdays". About 15 minutes before one, if you're at
the starting place, he nudges you with the live way to get there:

    "You usually head to the gym around 18:10 on Tuesdays, Sir. Bus 15 is 4 minutes out: leave by 18:06."

One nudge per routine per day, never in quiet hours or focus mode. Say "my routines" to see what he's learned, or
"routine nudges off".
"""
from __future__ import annotations

import json
import statistics
from collections import defaultdict
from datetime import datetime, timedelta

from .config import settings
from .tools import ToolContext, tool

DAYS = ["Mondays", "Tuesdays", "Wednesdays", "Thursdays", "Fridays", "Saturdays", "Sundays"]
LOOKBACK_DAYS = 42
MIN_STAY_MIN = 10        # at a place at least this long to count as "being there"
SPREAD_MIN = 35          # departures within this many minutes of each other are the same habit


def trips(store, now: datetime | None = None, days: int = LOOKBACK_DAYS) -> list[dict]:
    """[{from, to, leave}] trips between named places from the location history. The phone only records a point when
    you move, so a stay is measured from arriving to the first point after you left, and the departure time is that
    first point away (accurate: moving produces points straight away)."""
    from . import explore
    from .phonelink import where
    explore._ensure_locs(store)
    now = now or datetime.now(settings.tz)
    rows = store.query("SELECT ts, lat, lon FROM locs WHERE ts >= ? ORDER BY ts", ((now - timedelta(days=days)).timestamp(),))
    out: list[dict] = []
    cur = cur_start = left_from = left_at = None
    for r in rows:
        ts, place = r["ts"], where(store, r["lat"], r["lon"], 0.3)
        if place and place == cur:
            continue
        if cur is not None:                       # this point is away from where we were: we left
            if ts - cur_start >= MIN_STAY_MIN * 60:
                left_from, left_at = cur, ts
            cur = None
        if place:
            if left_from and left_from != place and ts - left_at < 3 * 3600:
                out.append({"from": left_from, "to": place, "leave": datetime.fromtimestamp(left_at, settings.tz)})
            left_from = None
            cur, cur_start = place, ts
    return out


def routines(store, now: datetime | None = None) -> list[dict]:
    """[{from, to, days: [0-6], at: "HH:MM", times: n}] habits: the same trip at about the same time on the same
    weekday at least twice, or on 3+ different weekdays at about the same time (then it's a "weekdays" habit)."""
    by_pair: dict[tuple, list[tuple[int, int, str]]] = defaultdict(list)
    for t in trips(store, now=now):
        lv = t["leave"]
        by_pair[(t["from"], t["to"])].append((lv.weekday(), lv.hour * 60 + lv.minute, lv.date().isoformat()))
    out = []
    for (a, b), occ in by_pair.items():
        # cluster departure times, then see which weekdays each cluster covers
        occ.sort(key=lambda x: x[1])
        clusters: list[list[tuple]] = []
        for o in occ:
            if clusters and o[1] - statistics.median(c[1] for c in clusters[-1]) <= SPREAD_MIN:
                clusters[-1].append(o)
            else:
                clusters.append([o])
        for c in clusters:
            per_day = defaultdict(set)
            for wd, _m, d in c:
                per_day[wd].add(d)
            days = sorted(wd for wd, ds in per_day.items() if len(ds) >= 2)
            if not days and len(per_day) >= 3:
                days = sorted(per_day)
            if not days:
                continue
            m = int(statistics.median(x[1] for x in c))
            out.append({"from": a, "to": b, "days": days, "at": f"{m // 60:02d}:{m % 60:02d}", "times": len(c)})
    return sorted(out, key=lambda r: (r["at"], r["from"]))


def describe_days(days: list[int]) -> str:
    if days == [0, 1, 2, 3, 4]:
        return "weekdays"
    if days == [5, 6]:
        return "weekends"
    if len(days) == 7:
        return "every day"
    names = [DAYS[d] for d in days]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def learn(store) -> list[dict]:
    """Re-learn the routines (nightly) and keep them for the phone's offline brain too."""
    rs = routines(store)
    store.set("predict:routines", json.dumps(rs))
    return rs


def due(store, now: datetime | None = None) -> list[dict]:
    """Routines starting in the next 5 to 25 minutes, from where you are right now, not yet nudged today."""
    now = now or datetime.now(settings.tz)
    try:
        rs = json.loads(store.get("predict:routines") or "[]")
    except ValueError:
        rs = []
    here = (store.get("phone:place") or "").lower()
    out = []
    for r in rs:
        if now.weekday() not in r["days"] or (here and r["from"].lower() != here):
            continue
        h, m = map(int, r["at"].split(":"))
        mins = (now.replace(hour=h, minute=m, second=0, microsecond=0) - now).total_seconds() / 60
        if 5 <= mins <= 25 and not store.get(f"predict:sent:{now.date()}:{r['from']}>{r['to']}"):
            out.append(r)
    return out


def nudge_text(store, r: dict) -> str:
    who = settings.owner_name or "Sir"
    lead = f"You usually head to {r['to']} around {r['at']} on {describe_days(r['days'])}, {who}."
    try:
        from . import navigate
        o = navigate.options(store, r["to"])
        if "error" not in o:
            t = o.get("transit") or {}
            bus = next((lg for lg in t.get("legs", []) if lg.get("mode") == "BUS" and lg.get("live")), None)
            if bus:
                lead += f" Bus {bus['route']} is {bus['live'][0]} minutes out" + (f": leave by {t['leave']}." if t.get("leave") else ".")
            else:
                best = next((x for x in o["options"] if x["mode"] == o["best"]), None)
                if best:
                    lead += f" {best['label']} takes about {best['min']} minutes right now."
            if o.get("rain"):
                lead += " It's raining: umbrella."
    except Exception:  # noqa: BLE001 - the nudge still goes, just without live travel
        pass
    return lead


def check(store, bus, now: datetime | None = None) -> list[str]:
    """Called every few minutes: send the nudges that are due."""
    from .life import in_focus
    from .speech import in_quiet_hours
    now = now or datetime.now(settings.tz)
    if (store.get("predict:on") or "on") == "off" or in_quiet_hours(now) or in_focus(store):
        return []
    sent = []
    for r in due(store, now):
        store.set(f"predict:sent:{now.date()}:{r['from']}>{r['to']}", now.isoformat())
        msg = nudge_text(store, r)
        from . import phonelink
        phonelink.queue(store, "notify", title="JARVIS · before you ask", text=msg, url="/map.html?nav=" + r["to"])
        bus.publish({"type": "say", "agent": "JARVIS", "text": msg})
        bus.log("JARVIS", "🔮 " + msg, "reply")
        sent.append(msg)
    return sent


@tool("my_routines", "The owner's learned routines (regular trips at regular times), e.g. home to gym around 18:10 on "
      "Tuesdays. Use for 'what are my routines', 'when do I usually…'.", {"type": "object", "properties": {}})
def my_routines(ctx: ToolContext) -> dict:
    rs = json.loads(ctx.store.get("predict:routines") or "null")
    if rs is None:
        rs = learn(ctx.store)
    return {"routines": [f"{r['from']} → {r['to']} around {r['at']} on {describe_days(r['days'])} (seen {r['times']}×)" for r in rs],
            "nudges": (ctx.store.get("predict:on") or "on")}
