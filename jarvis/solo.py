"""Solo JARVIS: the phone keeps working when the laptop is off, asleep or far away.

While the laptop is reachable, the phone app regularly collects a "solo pack": what JARVIS knows (memories, open
tasks, the next two weeks of events, saved places, upcoming reminders, the team) plus the free keys its own brain
needs (Gemini, and the bus/MRT ones). The keys stay inside the app's private storage on the owner's own phone and
are only ever sent to their own services (Google, OneMap, LTA).

When the laptop can't be reached, the app switches to its own JARVIS page that thinks with Gemini directly over
Wi-Fi or mobile data. Anything it does on its own (things to remember, tasks, reminders, events, notes, the
conversation) is queued on the phone and merged back here the next time the laptop is reachable, so both stay the
same JARVIS.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta

from .config import settings

PACK_VERSION = 1


def _events(store, start: datetime, end: datetime) -> list[dict]:
    a, b = start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")
    rows = list(store.list_events(a, b))
    try:
        rows += list(store.google_events_between(a, b))
    except Exception:  # noqa: BLE001 - no Google calendar linked
        pass
    seen, out = set(), []
    for e in sorted(rows, key=lambda e: e.get("start") or ""):
        key = ((e.get("title") or "").strip().lower(), (e.get("start") or "")[:16])
        if key in seen:
            continue
        seen.add(key)
        out.append({"title": e.get("title", ""), "start": e.get("start", ""), "end": e.get("end") or "",
                    "location": e.get("location") or ""})
    return out[:80]


def _reminders(store, now: datetime) -> list[dict]:
    rows = store.query("SELECT id, body, send_at FROM outbox WHERE reason = 'reminder' AND status IN ('pending', 'approved') "
                       "AND send_at > ? ORDER BY send_at LIMIT 60", (now.isoformat(timespec="seconds"),))
    return [{"id": r["id"], "text": r["body"].replace("⏰ Reminder: ", ""), "at": r["send_at"]} for r in rows]


def keys() -> dict:
    """The free keys the phone's own brain uses. Only sent to the owner's own phone app (device token)."""
    from . import navigate
    out = {"gemini": settings.gemini_key or "", "gemini_model": settings.gemini_model,
           "lta": os.environ.get("JARVIS_LTA_KEY", "") if navigate.lta_ready() else "",
           "onemap_email": os.environ.get("JARVIS_ONEMAP_EMAIL", "") if navigate.onemap_ready() else "",
           "onemap_password": os.environ.get("JARVIS_ONEMAP_PASSWORD", "") if navigate.onemap_ready() else "",
           # so the phone can answer your Telegram messages while the laptop is off (it hands the bot back after)
           "telegram_token": settings.telegram_token or "", "telegram_chat": _chat(),
           "morning_at": settings.morning_brief_at}
    return out


def _chat() -> str:
    from . import telegram
    try:
        return telegram.chat_id() or ""
    except Exception:  # noqa: BLE001
        return ""


def pack(store) -> dict:
    """Everything the phone needs to be JARVIS on its own for a few days."""
    from .agents import AGENTS
    now = datetime.now(settings.tz)
    places = {}
    try:
        places = json.loads(store.get("places:saved") or "{}")
    except ValueError:
        pass
    return {
        "version": PACK_VERSION,
        "made": now.isoformat(timespec="seconds"),
        "owner": settings.owner_name,
        "tz": str(settings.tz),
        "memories": [m["fact"] for m in store.memories(120)],
        "tasks": [{"id": t["id"], "title": t["title"], "due": t.get("due") or "", "area": t.get("area", "")}
                  for t in store.list_tasks("open", limit=60)],
        "events": _events(store, now - timedelta(hours=2), now + timedelta(days=14)),
        "reminders": _reminders(store, now),
        "places": places,
        "team": [{"name": a.name, "title": a.title, "color": a.color, "style": (a.personality or "")[:220]}
                 for a in AGENTS.values() if not a.hidden],
        "speaker": store.get("voice:speaker") or "laptop",
        "theme": _theme(store),
        "voices": _voices(),
        "money": _money(store),
        "holo": _holo(store),
        "guest": store.get("hud:guest") == "on",
        "routines": json.loads(store.get("predict:routines") or "[]") if (store.get("predict:on") or "on") == "on" else [],
    }


def _money(store) -> dict:
    """VERONICA's books (this month and last), so "what's my P&L?" works with the laptop off."""
    try:
        from datetime import timedelta as _td
        from . import money
        this = money.report(store)
        prev = money.report(store, (datetime.now(settings.tz).date().replace(day=1) - _td(days=1)).strftime("%Y-%m"))
        return {"this_month": money.text(this), "last_month": money.text(prev) if prev["transactions"] else "",
                "net": this["net"], "spent": this["spent"], "income": this["income"]}
    except Exception:  # noqa: BLE001
        return {}


def _theme(store) -> dict:
    from . import hud
    name = hud.theme(store)
    return {"name": name, "accent": hud.THEMES.get(name, "")}


def _voices() -> dict:
    """The team's premium Gemini voices, so the phone sounds the same with the laptop off."""
    from . import gemtts
    from .voice import ATTITUDE
    return {"models": gemtts.MODELS,
            "cast": {k: [v[0], v[1], ATTITUDE.get(k, "")] for k, v in gemtts.VOICES.items()},
            "acting": gemtts.acting("{who}", "{mood}")}


def _holo(store) -> dict | None:
    """The Holo Lab's data, so the holograms open on the phone with the laptop off."""
    try:
        from . import holo
        return holo.data(store)
    except Exception:  # noqa: BLE001
        return None


def merge(store, bus, items: list[dict]) -> dict:
    """What the phone did on its own, applied here. Each item: {kind, at, ...}. Unknown kinds are skipped.
    Items carry an id so a retried upload is never applied twice."""
    done = set(json.loads(store.get("solo:merged") or "[]"))
    counts: dict[str, int] = {}
    for it in items[:500]:
        uid = str(it.get("uid") or "")
        if not uid or uid in done:
            continue
        kind = it.get("kind", "")
        try:
            if kind == "remember" and it.get("fact"):
                store.remember(str(it["fact"])[:500])
            elif kind == "task" and it.get("title"):
                store.add_task(str(it["title"])[:200], due=it.get("due") or None)
            elif kind == "task_done" and it.get("id"):
                store.update_task(int(it["id"]), status="done")
            elif kind == "event" and it.get("title") and it.get("start"):
                store.add_event(str(it["title"])[:200], it["start"], it.get("end") or None, it.get("location") or "")
            elif kind == "reminder" and it.get("text"):
                # The phone rings for its own reminders (even offline), so the laptop only notes it: never twice.
                when = datetime.fromtimestamp(float(it.get("at_ms") or 0) / 1000, settings.tz) if it.get("at_ms") else None
                store.log_activity("JARVIS", f"⏰ Reminder set on the phone{when and f' for {when:%a %d %b %H:%M}' or ''}: "
                                             f"{it['text']}"[:500], "system")
            elif kind == "note" and it.get("body"):
                store.add_note(str(it.get("title") or "Phone note")[:120], str(it["body"])[:4000], "solo", "JARVIS")
            elif kind == "chat" and it.get("text"):
                who = "YOU" if it.get("who") == "you" else str(it.get("agent") or "JARVIS")
                store.log_activity(who, f"(phone, solo) {it['text']}"[:1500], "command" if who == "YOU" else "reply")
            else:
                continue
        except Exception:  # noqa: BLE001 - one bad item never blocks the rest
            continue
        done.add(uid)
        counts[kind] = counts.get(kind, 0) + 1
    store.set("solo:merged", json.dumps(sorted(done)[-3000:]))
    if counts:
        bits = ", ".join(f"{n} {k.replace('_', ' ')}{'s' if n > 1 else ''}" for k, n in counts.items())
        bus.log("JARVIS", f"📱 Synced from the phone (solo mode): {bits}.", "system")
        bus.publish({"type": "data", "what": "solo"})
    return {"merged": counts}
