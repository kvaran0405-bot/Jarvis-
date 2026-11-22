"""Live HUD data that needs no AI: the floating orb's state, the boot greeting, each agent's one-tap status line,
suit themes, guest mode and birthday mode. Everything here is instant and free."""
from __future__ import annotations

import random
import re
import time
from datetime import date, datetime, timedelta

from .config import settings

THEMES = {   # name -> accent used for the HUD chrome; "classic" keeps today's look exactly
    "classic": "", "mark 42": "#ffcc3d", "stealth": "#c9d3df", "arc blue": "#5fd8ff",
    "ironheart": "#ff4d5e", "wakanda": "#b06bff", "hulkbuster": "#3dff9a",
}


def theme(store) -> str:
    t = store.get("hud:theme") or "classic"
    return t if t in THEMES else "classic"


def set_theme(store, name: str) -> str | None:
    name = name.strip().lower().replace("mark42", "mark 42").replace("arc-blue", "arc blue")
    match = next((t for t in THEMES if t == name or t.replace(" ", "") == name.replace(" ", "")), None)
    if match:
        store.set("hud:theme", match)
    return match


def guest_on(store) -> bool:
    return store.get("hud:guest") == "on"


def birthday() -> tuple[int, int] | None:
    """(month, day) from JARVIS_BIRTHDAY (MM-DD) or a 'birthday' line in profile.md."""
    import os
    raw = os.environ.get("JARVIS_BIRTHDAY", "").strip()
    if re.match(r"^\d{2}-\d{2}$", raw):
        return int(raw[:2]), int(raw[3:])
    m = re.search(r"birthday[^\n]{0,20}?(\d{1,2})\s*(?:st|nd|rd|th)?\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)",
                  settings.profile(), re.I)
    if m:
        months = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
        return months.index(m.group(2).lower()[:3]) + 1, int(m.group(1))
    return None


def is_birthday(today: date | None = None) -> bool:
    b = birthday()
    today = today or datetime.now(settings.tz).date()
    return bool(b) and (today.month, today.day) == b


def orb_state(store, bus) -> dict:
    from . import brain
    from .agents import AGENTS
    agent, at, length = bus.last_voice
    talk_for = min(20, 2.5 + length / 14)   # roughly how long that line takes to say
    speaking = time.time() - at < talk_for
    color = AGENTS[agent].color if agent in AGENTS else "#ffd23f"
    return {"agent": agent, "color": color, "speaking": speaking, "mode": brain.get_mode(store)["mode"],
            "focus": store.get("focus:until") or "", "theme": theme(store), "accent": THEMES[theme(store)],
            "guest": guest_on(store), "birthday": is_birthday(), "screens": bus.screens,
            "text": bus.last_text[-160:] if speaking else ""}


_weather_cache: dict = {"at": 0.0, "data": None}


def weather_now() -> dict | None:
    if time.time() - _weather_cache["at"] < 1800:
        return _weather_cache["data"]
    try:
        from .extras import weather
        from .tools import ToolContext
        data = weather(ToolContext(None, None, settings, None, "JARVIS"))
        data = None if "error" in data else data
    except Exception:  # noqa: BLE001 - offline is fine
        data = None
    _weather_cache.update(at=time.time(), data=data)
    return data


def greeting(store) -> dict:
    """The boot greeting: time of day, weather, first thing today. No AI."""
    now = datetime.now(settings.tz)
    owner = settings.owner_name
    part = "morning" if now.hour < 12 else "afternoon" if now.hour < 18 else "evening"
    lines = [f"Good {part} {owner}."]
    if is_birthday(now.date()):
        lines = [f"Happy birthday {owner}. The whole team has been waiting all year for this one."]
    w = weather_now()
    if w and w.get("today"):
        t = w["today"]
        rain = t["rainy_hours"]
        wet = f", rain likely around {rain[0].split()[0]}" if isinstance(rain, list) and rain else ""
        lines.append(f"It's {round(t['max_c'])} degrees and {t['sky']}{wet}.")
    today = now.date().isoformat()
    events = [e for e in store.list_events(today, (now.date() + timedelta(days=1)).isoformat())
              if len(e["start"]) > 10 and e["start"][11:16] >= now.strftime("%H:%M")]
    if events:
        lines.append(f"Next up, {events[0]['title']} at {events[0]['start'][11:16]}.")
    due = [t for t in store.list_tasks("open", limit=300) if t["due"] and t["due"][:10] <= today]
    if due:
        lines.append(f"{len(due)} thing{'s' if len(due) != 1 else ''} due today.")
    waiting = len(store.list_proposals("open", 50)) + len(store.list_outbox("pending", 50))
    if waiting:
        lines.append(f"{waiting} waiting for your yes.")
    lines.append(random.choice(["All systems are yours.", "The lab is ready.", "Twelve agents standing by.",
                                "Shall we begin?"]))
    return {"text": " ".join(lines), "weather": w, "birthday": is_birthday(now.date())}


def quips(store) -> dict:
    """One live status line per agent for when you tap their card. Built from real data; no AI."""
    now = datetime.now(settings.tz)
    today = now.date().isoformat()
    owner = settings.owner_name
    tasks = store.list_tasks("open", limit=500)
    overdue = [t for t in tasks if t["due"] and t["due"][:10] < today]
    events = store.list_events(today, (now.date() + timedelta(days=7)).isoformat())
    upcoming = [e for e in events if e["start"] >= now.replace(tzinfo=None).isoformat(timespec="minutes")[:16]]
    gigs = store.list_gigs("active", 50)
    apps = store.list_applications()
    exams = store.query("SELECT course, exam_at FROM exams WHERE status='upcoming' AND exam_at >= ? ORDER BY exam_at",
                        (today,))
    lectures = store.list_lectures(3)
    from .life import workout_streak
    streak = workout_streak(store, now.date())
    money = store.spending_summary(now.date().replace(day=1).isoformat())
    mood = store.query("SELECT AVG(mood) AS m FROM mood WHERE day >= ?", ((now.date() - timedelta(days=7)).isoformat(),))
    mood_avg = mood[0]["m"] if mood and mood[0]["m"] else None
    sugg = store.list_suggestions("open", 20)
    notes = store.query("SELECT COUNT(*) AS n FROM notes")[0]["n"]
    pipeline = sum(float(g.get("quote_total") or 0) for g in gigs)

    def nxt(e):
        return f"{e['title']} {('at ' + e['start'][11:16]) if e['start'][:10] == today else 'on ' + e['start'][5:10]}"
    q = {
        "JARVIS": f"{len(tasks)} open task{'s' if len(tasks) != 1 else ''}, {len(overdue)} overdue. All under control, {owner}."
                  if tasks else f"Nothing on your plate. Suspicious, {owner}.",
        "FRIDAY": f"Next up: {nxt(upcoming[0])}." if upcoming else "Calendar's clear, boss. Enjoy it.",
        "ORACLE": f"{notes} notes in the archive. Ask me anything.",
        "ATHENA": (f"{exams[0]['course']} exam in {(date.fromisoformat(exams[0]['exam_at'][:10]) - now.date()).days} days. "
                   "Shall we revise?") if exams else (f"Latest lecture: {lectures[0]['title']}." if lectures
                                                      else "No exams on the radar. Study anyway."),
        "ZEUS": f"{len(apps)} application{'s' if len(apps) != 1 else ''} in play. "
                f"{sum(a['status'] == 'interview' for a in apps)} interview(s)." if apps else "No applications yet. We hunt tonight.",
        "HERALD": f"{len(sugg)} e-mail{'s' if len(sugg) != 1 else ''} waiting for your reply." if sugg else "Inbox is quiet. Too quiet.",
        "PEPPER": f"{len(gigs)} client{'s' if len(gigs) != 1 else ''} in the pipeline, ${pipeline:,.0f} in play."
                  if gigs else "No clients in the pipeline. Shall we change that?",
        "STEVE": f"{streak}-day gym streak. Don't break it." if streak else "No workout logged today. Just saying.",
        "VERONICA": (f"Spent ${-spent:,.0f} this month." if (spent := sum(r["total"] for r in money["by_category"]
                                                                          if r["total"] < 0)) < 0
                     else "No spending logged this month. Either very good or very sneaky."),
        "BANNER": (f"Mood's averaging {mood_avg:.1f} out of 5 this week." if mood_avg else "How are you actually feeling today?"),
        "EDITH": "Laptop and phone link online. Systems nominal.",
        "SENTINEL": f"{len(overdue)} overdue. I'm watching them." if overdue else "Perimeter secure. Nothing overdue.",
    }
    return q


# Poke the sphere: JARVIS reacts. No AI.
POKES = ["Yes Sir?", "I'm listening.", "That tickles, Sir. Metaphorically.", "Still here. Always am.",
         "Shall I do something useful, or are we just admiring the glow?", "At your service.",
         "Sir, the reactor is not a stress ball.", "Ready when you are.", "Online and fabulous, Sir."]


def poke() -> str:
    return random.choice(POKES)
