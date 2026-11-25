"""The boardroom: the owner is the boss, the agents are the team, and they report in when the boss shows up.

The first time JARVIS opens each day (phone or laptop, whenever that is: noon is fine), JARVIS greets the owner with
the weather and the day, then each agent with something to say reports in their own voice, one line each:
VERONICA yesterday's spending and the month so far, ZEUS the jobs lined up and anything waiting on a yes,
HERALD what came in overnight, ATHENA deadlines, plus anything waiting for approval. If it hasn't been opened by
1pm, the same briefing goes to Telegram. Built from the data directly (no AI wait), so it plays at once.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from .config import settings

DAY_STARTS = 5   # a "day" for the briefing starts at 5am: a 2am session still counts as last night


def _today(now: datetime) -> str:
    return (now - timedelta(hours=DAY_STARTS)).date().isoformat()


def _money(f: float) -> str:
    return f"${f:,.0f}" if abs(f) >= 100 else f"${f:,.2f}".replace(".00", "")


def greeting(now: datetime, name: str) -> str:
    h = now.hour
    part = "Good morning" if 5 <= h < 12 else "Good afternoon" if h < 18 else "Good evening"
    return f"{part}, {name}." + (" Rise and shine, the company's been busy." if 11 <= h < 14 else "")


def weather_line() -> str:
    try:
        from .hud import weather_now
        w = weather_now()
        t = (w or {}).get("today")
        if not t:
            return ""
        rain = t.get("rain_chance_max") or 0
        return (f"Today's {t['sky']}, {round(t['min_c'])} to {round(t['max_c'])} degrees"
                + (f", with a {rain}% chance of rain: take an umbrella." if rain >= 50 else "."))
    except Exception:  # noqa: BLE001
        return ""


def briefing(store, now: datetime | None = None) -> dict:
    """Everything the team has to report, as lines in order: [{agent, text}]."""
    now = now or datetime.now(settings.tz)
    name = settings.owner_name or "Sir"
    lines = [{"agent": "JARVIS", "text": " ".join(x for x in (greeting(now, name), weather_line()) if x)}]

    # JARVIS: the day
    try:
        from .quick import _events
        evs = [e for e in _events(store, now, now.replace(hour=23, minute=59)) if (e.get("end") or e["start"]) >= now.isoformat()]
        tasks = store.list_tasks("open", limit=50)
        due = [t for t in tasks if (t.get("due") or "")[:10] and (t["due"][:10] <= now.date().isoformat())]
        bits = []
        if evs:
            bits.append(f"{len(evs)} thing{'s' if len(evs) > 1 else ''} on today, first {evs[0]['title']} at {evs[0]['start'][11:16]}")
        if due:
            bits.append(f"{len(due)} task{'s' if len(due) > 1 else ''} due, starting with {due[0]['title']}")
        if bits:
            lines.append({"agent": "JARVIS", "text": "On the agenda: " + "; ".join(bits) + "."})
    except Exception:  # noqa: BLE001
        pass

    # VERONICA: the daily P&L (yesterday, and the month so far)
    try:
        from . import money
        try:
            money.sync(store)
        except Exception:  # noqa: BLE001
            pass
        y = (now.date() - timedelta(days=1)).isoformat()
        rows = store.query("SELECT amount, category, note FROM transactions WHERE day = ?", (y,))
        spent = -sum(r["amount"] for r in rows if r["amount"] < 0)
        got = sum(r["amount"] for r in rows if r["amount"] > 0)
        cats = {}
        for r in rows:
            if r["amount"] < 0:
                cats[r["category"]] = cats.get(r["category"], 0) - r["amount"]
        m = money.report(store)
        if rows or m["transactions"]:
            top = ", ".join(f"{c} {_money(v)}" for c, v in sorted(cats.items(), key=lambda x: -x[1])[:3])
            t = (f"Yesterday you spent {_money(spent)}" + (f": {top}" if top else "") + "." if spent else "No spending yesterday. Saint behaviour.")
            if got:
                t += f" {_money(got)} came in."
            t += f" Month so far: {_money(m['income'])} in, {_money(m['spent'])} out, net {'+' if m['net'] >= 0 else '-'}{_money(abs(m['net']))}."
            lines.append({"agent": "VERONICA", "text": t})
    except Exception:  # noqa: BLE001
        pass

    # ZEUS: the job hunt
    try:
        from . import jobs
        q, ready = jobs.queue(store, 200), jobs.email_ready(store)
        y0 = (now - timedelta(days=1)).date().isoformat()
        did = store.query("SELECT COUNT(*) AS n FROM jobs WHERE status IN ('applied','emailed') AND acted >= ? AND acted < ?",
                          (y0, now.date().isoformat()))[0]["n"]
        if q or did:
            t = f"{len(q)} jobs lined up for you, best fit {q[0]['fit']}% at {q[0]['company'] or q[0]['title']}." if q else ""
            if ready:
                t += f" {len(ready)} can be emailed with your CV the moment you say SEND ALL."
            if did:
                t += f" Yesterday: {did} application{'s' if did > 1 else ''}."
            t += " Target today: " + str(jobs.prefs(store)["daily_target"]) + "."
            lines.append({"agent": "ZEUS", "text": t.strip()})
        interviews = store.list_applications("interview")
        if interviews:
            lines.append({"agent": "ZEUS", "text": f"Interview{'s' if len(interviews) > 1 else ''} in play: "
                          + ", ".join(f"{a['role']} at {a['company']}" for a in interviews[:3]) + "."})
    except Exception:  # noqa: BLE001
        pass

    # HERALD: what came in while you slept
    try:
        since = (now - timedelta(hours=14)).isoformat()
        notes = store.query("SELECT app, sender, urgent FROM phone_notes WHERE created >= ?", (since,))
        if notes:
            by = {}
            for n in notes:
                by[n["app"]] = by.get(n["app"], 0) + 1
            urgent = [n["sender"] for n in notes if n["urgent"]]
            t = "Overnight: " + ", ".join(f"{v} from {k}" for k, v in sorted(by.items(), key=lambda x: -x[1])[:4]) + "."
            if urgent:
                t += f" Flagged: {', '.join(dict.fromkeys(urgent))[:80]}."
            lines.append({"agent": "HERALD", "text": t})
    except Exception:  # noqa: BLE001
        pass

    # ATHENA: deadlines this week
    try:
        soon = [t for t in store.list_tasks("open", limit=80) if (t.get("due") or "")[:10]
                and now.date().isoformat() < t["due"][:10] <= (now.date() + timedelta(days=3)).isoformat()
                and any(k in (t["title"] or "").lower() for k in ("exam", "assignment", "submit", "deadline", "quiz", "project", "essay", "test"))]
        if soon:
            lines.append({"agent": "ATHENA", "text": "Coming up: " + "; ".join(f"{t['title']} on {t['due'][:10]}" for t in soon[:3]) + "."})
    except Exception:  # noqa: BLE001
        pass

    # waiting on the boss
    try:
        pend = store.list_outbox("pending", 50)
        props = store.list_proposals("open", 20)
        if pend or props:
            t = []
            if pend:
                t.append(f"{len(pend)} message{'s' if len(pend) > 1 else ''} waiting for your yes")
            if props:
                t.append(f"{len(props)} idea{'s' if len(props) > 1 else ''} from the team to approve")
            lines.append({"agent": "PEPPER", "text": "Needs your sign-off: " + " and ".join(t) + ". It's all on the dashboard."})
    except Exception:  # noqa: BLE001
        pass

    if len(lines) == 1:
        lines.append({"agent": "JARVIS", "text": "All quiet on every front. The team awaits your orders."})
    else:
        lines.append({"agent": "JARVIS", "text": "That's the briefing. Where shall we start?"})
    return {"day": _today(now), "lines": lines, "text": "\n".join(f"{l['agent']}: {l['text']}" for l in lines)}


def first_open(store, now: datetime | None = None) -> dict:
    """The briefing if the boss hasn't had today's yet (then it's marked as given), else {'new': False}."""
    now = now or datetime.now(settings.tz)
    if store.get("brief:given") == _today(now):
        return {"new": False}
    store.set("brief:given", _today(now))
    return {"new": True, **briefing(store, now)}


def fallback(store, bus) -> None:
    """1pm and JARVIS hasn't been opened today: the briefing goes to Telegram instead."""
    now = datetime.now(settings.tz)
    if store.get("brief:given") == _today(now):
        return
    b = first_open(store, now)
    if b.get("new"):
        from .notify import notify_owner
        notify_owner("🏢 Your team's briefing", "\n\n".join(f"{l['agent']}: {l['text']}" for l in b["lines"]))
