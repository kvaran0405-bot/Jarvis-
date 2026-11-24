"""Instant answers: everyday questions answered straight from JARVIS's own data, with no AI round trip.

"What time is it", "what's next", "my tasks", "how many steps", "where am I", "phone battery", "weather",
"hi Jarvis", "thanks": these come back in well under a second, in JARVIS's voice. Anything more than that goes to
the brain as usual. Only whole, simple questions match, so nothing richer is cut short.
"""
from __future__ import annotations

import json
import random
import re
import urllib.request
from datetime import datetime, timedelta

from .config import settings

_J = r"^\s*(?:(?:hey|ok|okay|yo)\s+)?(?:jarvis[,\s]+)?(?:can you\s+)?(?:tell me\s+)?"
_E = r"\s*(?:please|pls|lah|leh|sir)?\s*[.!?]*\s*$"
P = {
    "time": re.compile(_J + r"(?:what(?:'s| is) the time|what time is it(?: now)?|time(?: now)?|current time)" + _E, re.I),
    "date": re.compile(_J + r"(?:what(?:'s| is) (?:the date|today'?s date)|what day is (?:it|today))(?: today)?" + _E, re.I),
    "next": re.compile(_J + r"(?:what(?:'s| is) next|what(?:'s| is) (?:my|the) next (?:thing|event|plan|class)|what(?:'s| is) on (?:today|my plate)(?: today)?|"
                            r"what(?:'s| have i got| do i have) today|my day|today'?s plan)" + _E, re.I),
    "tasks": re.compile(_J + r"(?:what are my tasks|my tasks|(?:what(?:'s| is) on )?my to-?do(?: list)?|what do i (?:need|have) to do)" + _E, re.I),
    "steps": re.compile(_J + r"(?:how many steps(?: (?:have i|did i)(?: walked| done| taken)?)?(?: today)?|my steps(?: today)?|step count)" + _E, re.I),
    "where": re.compile(_J + r"(?:where am i(?: now)?|where(?:'s| is) my phone)" + _E, re.I),
    "battery": re.compile(_J + r"(?:(?:my |the )?phone battery|how(?:'s| is) my (?:phone )?battery|battery(?: level)?)" + _E, re.I),
    "weather": re.compile(_J + r"(?:(?:what(?:'s| is) the )?weather(?: like)?(?: now| today| outside)?|is it (?:going to )?rain(?:ing)?(?: today| later)?|will it rain(?: today| later)?)" + _E, re.I),
    "hello": re.compile(r"^\s*(?:hi|hello|hey|yo|sup|wassup)(?:\s+jarvis)?\s*[.!?]*\s*$|^\s*jarvis\s*[.!?]*\s*$", re.I),
    "thanks": re.compile(r"^\s*(?:thanks?|thank you|thx|ty|cheers|nice one|good job|well done)(?:\s+jarvis)?(?:\s+(?:lah|bro|buddy))?\s*[.!]*\s*$", re.I),
}
HOME = (1.3521, 103.8198)   # Singapore, when the phone hasn't said where it is


def _now() -> datetime:
    return datetime.now(settings.tz)


def _events(store, start: datetime, end: datetime) -> list[dict]:
    a, b = start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")
    rows = list(store.list_events(a, b))
    try:
        rows += list(store.google_events_between(a, b))
    except Exception:  # noqa: BLE001
        pass
    seen, out = set(), []
    for e in sorted(rows, key=lambda e: e.get("start") or ""):
        k = ((e.get("title") or "").lower(), (e.get("start") or "")[:16])
        if k not in seen:
            seen.add(k)
            out.append(e)
    return out


def _phone(store) -> dict:
    try:
        return json.loads(store.get("phone:state") or "{}")
    except ValueError:
        return {}


def weather(lat: float, lon: float) -> dict | None:
    url = (f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current=temperature_2m,apparent_temperature,"
           "precipitation,weather_code&hourly=precipitation_probability&forecast_hours=6&timezone=auto")
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "JARVIS personal assistant"}), timeout=4) as r:
            return json.loads(r.read())
    except Exception:  # noqa: BLE001
        return None


def answer(store, text: str) -> str | None:
    """An instant reply, or None to let the brain handle it."""
    t = (text or "").strip()
    if len(t) > 80:
        return None
    kind = next((k for k, rx in P.items() if rx.match(t)), None)
    if kind is None:
        return None
    now, sir = _now(), settings.owner_name or "Sir"
    if kind == "time":
        return random.choice([f"It's {now:%H:%M}, {sir}.", f"{now:%H:%M}, {sir}. {'Late one tonight.' if now.hour >= 23 or now.hour < 5 else 'Time flies.'}"])
    if kind == "date":
        return f"It's {now:%A, %d %B}, {sir}."
    if kind == "next":
        evs = [e for e in _events(store, now - timedelta(minutes=30), now.replace(hour=23, minute=59)) if (e.get("end") or e["start"]) >= now.isoformat()]
        if not evs:
            tomorrow = _events(store, now.replace(hour=23, minute=59), now + timedelta(days=1, hours=12))
            return f"Nothing else today, {sir}." + (f" Tomorrow starts with {tomorrow[0]['title']} at {tomorrow[0]['start'][11:16]}." if tomorrow else " The rest of the day is yours.")
        e = evs[0]
        more = f" Then {', '.join(x['title'] for x in evs[1:3])}." if len(evs) > 1 else ""
        where = f" at {e['location']}" if e.get("location") else ""
        return f"Next up: {e['title']} at {e['start'][11:16]}{where}.{more}"
    if kind == "tasks":
        ts = store.list_tasks("open", limit=20)
        if not ts:
            return f"Your list is clear, {sir}. Suspiciously clear."
        top = ", ".join(x["title"] for x in ts[:3])
        return f"{len(ts)} open, {sir}. Top of the pile: {top}."
    if kind == "steps":
        s = store.get(f"steps:{now.date().isoformat()}")
        if not s:
            return f"I haven't had a step count from your phone today, {sir}. Is the step counter allowed in the app?"
        n = int(s)
        return f"{n:,} steps so far today, {sir}." + (" Respectable." if n >= 8000 else " The stairs are calling." if n < 3000 else "")
    if kind == "where":
        place, st = store.get("phone:place") or "", _phone(store)
        if place:
            return f"You're at {place}, {sir}."
        if st.get("lat"):
            return f"Your phone's at {st['lat']:.4f}, {st['lon']:.4f}, {sir}. Open the map for the street view."
        return f"Your phone hasn't told me where it is lately, {sir}."
    if kind == "battery":
        st = _phone(store)
        if "battery" not in st:
            return f"Your phone hasn't checked in lately, {sir}."
        b = st["battery"]
        return f"Phone's at {b}%{', charging' if st.get('charging') else ''}, {sir}." + (" Might want a charger soon." if b < 25 and not st.get("charging") else "")
    if kind == "weather":
        st = _phone(store)
        lat, lon = (st.get("lat"), st.get("lon")) if st.get("lat") else HOME
        w = weather(lat, lon)
        if not w:
            return None   # let the brain try another way
        c, code = w["current"], w["current"]["weather_code"]
        words = ("thunderstorms" if code >= 95 else "showers" if code >= 80 else "rain" if code >= 61 else "drizzle" if code >= 51
                 else "fog" if code >= 45 else "cloudy" if code >= 3 else "partly cloudy" if code >= 1 else "clear")
        probs = (w.get("hourly") or {}).get("precipitation_probability") or []
        soon = next((i for i, p in enumerate(probs) if p >= 60), None)
        rain = (" Rain likely within the hour: umbrella." if soon is not None and soon <= 1 else f" Rain likely in about {soon} hours." if soon is not None else " No rain expected for a while.")
        return f"{round(c['temperature_2m'])}° and {words}, feels like {round(c['apparent_temperature'])}°.{rain}"
    if kind == "hello":
        h = now.hour
        part = "morning" if 5 <= h < 12 else "afternoon" if h < 18 else "evening"
        return random.choice([f"Good {part}, {sir}. What can I do for you?", f"At your service, {sir}.", f"{sir}. Always a pleasure. What's the mission?"])
    if kind == "thanks":
        return random.choice([f"Any time, {sir}.", "My pleasure.", f"That's what I'm here for, {sir}.", "Happy to help. As always."])
    return None
