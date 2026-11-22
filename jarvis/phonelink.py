"""Phone link (Phase 5). The JARVIS phone app checks in with the laptop every few seconds while it's awake (less when
the screen is off). Each check-in carries the phone's state (battery, screen, location) and collects commands the
laptop queued for it: ring (find my phone), silent mode, clipboard, notifications, open a page, and approved
autopilot steps. Location check-ins drive 'location magic'. Phone notifications feed the notification brain."""
from __future__ import annotations

import json
import math
import re
from datetime import datetime, timedelta

from .config import settings
from .guard import REFUSAL, blocked, is_secret
from .tools import S, ToolContext, tool

B = {"type": "boolean"}
MESSAGING = {"com.whatsapp": "WhatsApp", "com.whatsapp.w4b": "WhatsApp Business", "org.telegram.messenger": "Telegram",
             "com.instagram.android": "Instagram", "com.google.android.apps.messaging": "Messages",
             "com.android.mms": "Messages", "com.coloros.mms": "Messages", "com.facebook.orca": "Messenger"}
URGENT_RE = re.compile(r"\b(urgent|asap|emergency|help|call me|now please|accident|hospital|important)\b", re.I)


def _ensure(store) -> None:
    store.execute("CREATE TABLE IF NOT EXISTS phone_cmds (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, "
                  "payload TEXT DEFAULT '{}', status TEXT NOT NULL DEFAULT 'queued', result TEXT DEFAULT '', created TEXT NOT NULL)")
    store.execute("CREATE TABLE IF NOT EXISTS phone_notes (id INTEGER PRIMARY KEY AUTOINCREMENT, app TEXT, sender TEXT, "
                  "text TEXT, urgent INTEGER DEFAULT 0, created TEXT NOT NULL)")


def queue(store, kind: str, **payload) -> int:
    _ensure(store)
    return store.execute("INSERT INTO phone_cmds (kind, payload, created) VALUES (?,?,?)",
                         (kind, json.dumps(payload), datetime.now(settings.tz).isoformat()))


def state(store) -> dict:
    try:
        return json.loads(store.get("phone:state") or "{}")
    except ValueError:
        return {}


def online(store, minutes: int = 3) -> bool:
    st = state(store)
    return bool(st.get("at")) and datetime.fromisoformat(st["at"]) > datetime.now(settings.tz) - timedelta(minutes=minutes)


# ------------------------------------------------------------------ check-in
def checkin(store, bus, report: dict) -> list[dict]:
    """The phone reports in; returns the commands waiting for it."""
    _ensure(store)
    now = datetime.now(settings.tz)
    prev = state(store)
    st = {k: report.get(k) for k in ("battery", "charging", "screen_on", "lat", "lon", "speed", "accuracy") if k in report}
    st["at"] = now.isoformat()
    if "lat" not in st and prev.get("lat") is not None:
        st.update(lat=prev["lat"], lon=prev["lon"], loc_at=prev.get("loc_at"))
    elif "lat" in st:
        st["loc_at"] = now.isoformat()
    store.set("phone:state", json.dumps(st))
    if "lat" in report and report.get("lat") is not None:
        location_magic(store, bus, float(report["lat"]), float(report["lon"]), float(report.get("speed") or 0), prev)
    continuity(store, st)
    cmds = store.query("SELECT id, kind, payload FROM phone_cmds WHERE status = 'queued' ORDER BY id LIMIT 10")
    for c in cmds:
        store.execute("UPDATE phone_cmds SET status = 'sent' WHERE id = ?", (c["id"],))
    store.execute("DELETE FROM phone_cmds WHERE created < ?", ((now - timedelta(days=2)).isoformat(),))
    return [{"id": c["id"], "kind": c["kind"], **json.loads(c["payload"] or "{}")} for c in cmds]


def done(store, cmd_id: int, result: str) -> None:
    _ensure(store)
    store.execute("UPDATE phone_cmds SET status = 'done', result = ? WHERE id = ?", (result[:500], cmd_id))


# ------------------------------------------------------------------ location magic
def _km(a, b) -> float:
    return 111.2 * math.hypot(a[0] - b[0], (a[1] - b[1]) * math.cos(math.radians(a[0])))


def places(store) -> dict:
    """Saved places (home, gym...) plus the built-in Singapore landmarks: {name: (lat, lon)}."""
    from .holo import LANDMARKS
    out = {k: (v[0], v[1]) for k, v in LANDMARKS.items()}
    try:
        out.update({k: tuple(v) for k, v in json.loads(store.get("places:saved") or "{}").items()})
    except ValueError:
        pass
    return out


def where(store, lat: float, lon: float, radius_km: float = 0.35) -> str | None:
    best = min(((n, _km((lat, lon), p)) for n, p in places(store).items()), key=lambda x: x[1], default=None)
    return best[0] if best and best[1] <= radius_km else None


def location_magic(store, bus, lat: float, lon: float, speed: float, prev: dict) -> list[str]:
    """Arrive somewhere: do the sensible thing. Returns what it did (for tests and the log)."""
    from .speech import announce
    did = []
    here = where(store, lat, lon)
    was = store.get("phone:place") or ""
    if speed * 3.6 > 25 and not store.get("phone:driving"):
        store.set("phone:driving", "1")
        queue(store, "notify", title="Car mode?", text="Looks like you're on the road. Tap for car mode.", url="/car.html")
        did.append("car mode offered")
    elif speed * 3.6 < 8 and store.get("phone:driving"):
        store.set("phone:driving", "")
    if (here or "") == was:
        return did
    store.set("phone:place", here or "")
    if was:
        bus.log("EDITH", f"📍 Left {was}", "system")
        if "gym" in was.lower():
            queue(store, "notify", title="STEVE", text="Done at the gym? Tell me what you trained and I'll log it.", url="/home.html")
            did.append("gym log prompt")
    if not here:
        return did
    bus.log("EDITH", f"📍 Arrived at {here}", "system")
    visited = set(filter(None, (store.get("places:visited") or "").split("|")))
    visited.add(here)
    store.set("places:visited", "|".join(sorted(visited)))
    low = here.lower()
    if low == "home":
        store.set("owner:arrived_home", datetime.now(settings.tz).isoformat())
        if bus.screens:
            bus.publish({"type": "home_arrival"})
        did.append("welcome home")
    elif "kaplan" in low or "campus" in low or "nus" in low or "school" in low:
        queue(store, "dnd", on=True)
        queue(store, "notify", title="ATHENA", text=f"At {here}. Phone on silent for class. Want me to record the lecture?",
              url="/home.html")
        did.append("class mode")
    elif "gym" in low:
        queue(store, "notify", title="STEVE", text="Gym time. Let's go! Tell me what you're training and I'll track it.",
              url="/home.html")
        did.append("gym hype")
    today = datetime.now(settings.tz).date().isoformat()
    for e in store.list_events(today, (datetime.now(settings.tz).date() + timedelta(days=1)).isoformat()):
        from .holo import place_of
        if place_of(f"{e['title']} {e.get('location') or ''}") == here:
            queue(store, "notify", title="PEPPER" if e["area"] == "career" else "JARVIS",
                  text=f"You're at {here} for {e['title']}. Rundown and checklist are ready.", url="/command-centre.html#agenda")
            announce(bus, "JARVIS", f"You've arrived at {here} for {e['title']}, Sir.", phone=False)
            did.append(f"event: {e['title']}")
            break
    return did


def continuity(store, st: dict) -> None:
    """Walked away from the laptop mid-conversation and picked up the phone: offer to continue there."""
    if not st.get("screen_on"):
        return
    now = datetime.now(settings.tz)
    last_seen = store.get("owner:last_seen")
    if not last_seen:
        return
    seen = datetime.fromisoformat(last_seen)
    if not (now - timedelta(minutes=30) < seen < now - timedelta(minutes=5)):
        return
    if store.get("phone:continuity_for") == last_seen:
        return
    last = store.query("SELECT message FROM activity WHERE agent = 'YOU' AND kind = 'command' ORDER BY id DESC LIMIT 1")
    if not last:
        return
    store.set("phone:continuity_for", last_seen)
    queue(store, "notify", title="Continue on phone?", text=f"You were saying: “{last[0]['message'][:80]}”", url="/home.html")


# ------------------------------------------------------------------ notification brain
def classify(store, app: str, sender: str, text: str) -> dict:
    """Is this phone notification urgent? Rules only, no AI."""
    name = (sender or "").split(":")[0].strip()
    vip = store.query("SELECT relationship, trusted FROM contacts WHERE lower(name) = lower(?)", (name,))
    rel = (vip[0]["relationship"] or "").lower() if vip else ""
    today = datetime.now(settings.tz).date().isoformat()
    client_today = any(name and name.lower() in (g["client"] or "").lower() and (g["event_date"] or "")[:10] == today
                       for g in store.list_gigs("active", 50))
    urgent = bool(URGENT_RE.search(text or "")) and (bool(vip) or client_today) or client_today and app in MESSAGING
    family = any(k in rel for k in ("mum", "mom", "dad", "family", "brother", "sister", "wife", "girlfriend", "partner"))
    return {"urgent": urgent or (family and bool(URGENT_RE.search(text or ""))), "vip": bool(vip), "client_today": client_today}


def note(store, bus, app: str, sender: str, text: str) -> dict:
    _ensure(store)
    if blocked(app, sender, text) or is_secret(text):
        return {"ignored": "private"}
    c = classify(store, app, sender, text)
    store.execute("INSERT INTO phone_notes (app, sender, text, urgent, created) VALUES (?,?,?,?,?)",
                  (MESSAGING.get(app, app), sender[:80], text[:500], int(c["urgent"]), datetime.now(settings.tz).isoformat()))
    store.execute("DELETE FROM phone_notes WHERE created < ?", ((datetime.now(settings.tz) - timedelta(days=3)).isoformat(),))
    if c["urgent"]:
        from .speech import announce
        bus.publish({"type": "alert", "agent": "SENTINEL", "text": f"{sender}: {text[:120]}"})
        announce(bus, "SENTINEL", f"Urgent message from {sender.split(':')[0]}, Sir: {text[:140]}", critical=False, phone=False)
    return c


@tool("phone_notifications", "What happened on the owner's phone: recent notifications (messages, apps) from the last N "
      "hours, with urgent ones first. For 'what did I miss?'. Bank and OTP notifications are never stored.",
      {"hours": {"type": "integer"}})
def phone_notifications(ctx: ToolContext, hours: int = 6) -> dict:
    _ensure(ctx.store)
    since = (datetime.now(settings.tz) - timedelta(hours=hours)).isoformat()
    rows = ctx.store.query("SELECT app, sender, text, urgent, created FROM phone_notes WHERE created >= ? "
                           "ORDER BY urgent DESC, id DESC LIMIT 60", (since,))
    return {"count": len(rows), "notifications": rows}


# ------------------------------------------------------------------ tools that act on the phone
@tool("find_my_phone", "Make the owner's phone ring loudly (even on silent) so they can find it, and say where it "
      "last was.")
def find_my_phone(ctx: ToolContext) -> dict:
    st = state(ctx.store)
    if not st:
        return {"error": "The phone app hasn't linked yet (open the JARVIS app once)."}
    queue(ctx.store, "ring")
    out = {"ringing": "queued", "phone_last_seen": st.get("at"), "battery": st.get("battery")}
    if st.get("lat") is not None:
        out["last_place"] = where(ctx.store, st["lat"], st["lon"], 1.0) or f"{st['lat']:.4f},{st['lon']:.4f}"
        out["map"] = f"https://maps.google.com/?q={st['lat']},{st['lon']}"
    if not online(ctx.store):
        out["note"] = "The phone hasn't checked in for a few minutes; it rings as soon as it's back online."
    return out


@tool("phone_silent", "Turn the phone's Do Not Disturb (silent) on or off.", {"on": B}, ["on"])
def phone_silent(ctx: ToolContext, on: bool) -> dict:
    queue(ctx.store, "dnd", on=bool(on))
    return {"queued": "silent on" if on else "silent off"}


@tool("phone_clipboard", "Put text on the phone's clipboard (shared clipboard from the laptop), ready to paste.",
      {"text": S}, ["text"])
def phone_clipboard(ctx: ToolContext, text: str) -> dict:
    if is_secret(text) or blocked(text):
        return {"error": REFUSAL}
    queue(ctx.store, "clip", text=text[:5000])
    return {"queued": True}


@tool("phone_notify", "Show a notification on the owner's phone from an agent (with a page to open when tapped).",
      {"title": S, "text": S, "url": S}, ["title", "text"])
def phone_notify(ctx: ToolContext, title: str, text: str, url: str = "/home.html") -> dict:
    queue(ctx.store, "notify", title=title[:60], text=text[:300], url=url if url.startswith("/") else "/home.html")
    return {"queued": True}


@tool("save_place", "Remember a place by name for location magic (e.g. 'home', 'gym', 'office'). Uses the phone's "
      "current location if lat/lon aren't given.", {"name": S, "lat": {"type": "number"}, "lon": {"type": "number"}},
      ["name"])
def save_place(ctx: ToolContext, name: str, lat: float | None = None, lon: float | None = None) -> dict:
    if lat is None or lon is None:
        st = state(ctx.store)
        if st.get("lat") is None:
            return {"error": "No phone location yet: open the JARVIS app with location allowed, or give lat/lon."}
        lat, lon = st["lat"], st["lon"]
    saved = json.loads(ctx.store.get("places:saved") or "{}")
    saved[name.strip().lower()] = [round(float(lat), 6), round(float(lon), 6)]
    ctx.store.set("places:saved", json.dumps(saved))
    return {"saved": name, "places": list(saved)}


AUTOPILOT_ACTIONS = {"open_app", "tap_text", "type_text", "scroll_down", "scroll_up", "back", "home", "wait"}


@tool("phone_autopilot", "Do something on the owner's phone by tapping through apps: steps like "
      "[{action: open_app, app: 'Instagram'}, {action: tap_text, text: 'Your story'}, {action: type_text, text: '...'}, "
      "{action: back}]. Actions: open_app, tap_text, type_text, scroll_down, scroll_up, back, home, wait. Always waits "
      "for the owner's OK first. Bank and finance apps are blocked.",
      {"steps": {"type": "array", "items": {"type": "object"}}, "reason": S}, ["steps", "reason"])
def phone_autopilot(ctx: ToolContext, steps: list, reason: str) -> dict:
    clean = []
    for st in steps[:20]:
        a = str(st.get("action", "")).lower()
        if a not in AUTOPILOT_ACTIONS:
            return {"error": f"Unknown step '{a}'. Use: {', '.join(sorted(AUTOPILOT_ACTIONS))}"}
        if blocked(json.dumps(st)):
            return {"error": REFUSAL}
        clean.append({k: str(v)[:500] for k, v in st.items()})
    if not ctx.approved:
        from .tools import REGISTRY
        plan = ("Call phone_autopilot with these exact steps: " + json.dumps(clean) + "\nIn plain words: " +
                "; ".join(f"{s['action'].replace('_', ' ')} {s.get('app') or s.get('text') or ''}".strip() for s in clean))
        out = REGISTRY["propose"].fn(ctx, title=f"On your phone: {reason}"[:120], plan=plan, why=reason)
        return {"status": "waiting for the owner's yes", **out}
    cid = queue(ctx.store, "autopilot", steps=clean)
    return {"queued": cid, "steps": len(clean)}


# ------------------------------------------------------------------ widget
def widget(store) -> dict:
    from . import brain
    now = datetime.now(settings.tz)
    today = now.date().isoformat()
    nxt = next((e for e in store.list_events(today, (now.date() + timedelta(days=2)).isoformat())
                if len(e["start"]) > 10 and e["start"] >= now.replace(tzinfo=None).isoformat(timespec="minutes")), None)
    month = now.date().replace(day=1).isoformat()
    handled = store.query("SELECT COUNT(*) AS n FROM activity WHERE kind IN ('job','reply','report') AND created >= ?",
                          (month,))[0]["n"]
    return {"next": f"{nxt['title']} · {nxt['start'][11:16]}" if nxt else "Nothing else today",
            "handled": handled, "mode": brain.get_mode(store)["mode"],
            "waiting": len(store.list_proposals("open", 50)) + len(store.list_outbox("pending", 50))}
