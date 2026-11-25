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
    if isinstance(report.get("steps"), (int, float)) and 0 <= report["steps"] < 200000:   # the phone's step counter
        store.set(f"steps:{now.date().isoformat()}", str(int(report["steps"])))
    if report.get("points"):   # the phone's location history since the last check-in (catches up after being offline)
        from . import explore as _ex
        try:
            _ex.add_points(store, report["points"])
        except Exception:  # noqa: BLE001
            pass
    if "lat" in report and report.get("lat") is not None:
        from . import explore
        try:
            explore.record(store, float(report["lat"]), float(report["lon"]))
        except Exception:  # noqa: BLE001 - the map is a nicety
            pass
        try:
            from . import trips
            trips.on_location(store, bus, float(report["lat"]), float(report["lon"]))
        except Exception:  # noqa: BLE001
            pass
        try:
            from . import chatter
            chatter.on_location(store, bus, float(report["lat"]), float(report["lon"]), float(report.get("speed") or 0))
        except Exception:  # noqa: BLE001 - chatter is a nicety
            pass
        location_magic(store, bus, float(report["lat"]), float(report["lon"]), float(report.get("speed") or 0), prev)
    continuity(store, st)
    cmds = store.query("SELECT id, kind, payload FROM phone_cmds WHERE status = 'queued' ORDER BY id LIMIT 10")
    for c in cmds:
        store.execute("UPDATE phone_cmds SET status = 'sent' WHERE id = ?", (c["id"],))
    store.execute("DELETE FROM phone_cmds WHERE created < ?", ((now - timedelta(days=2)).isoformat(),))
    return [{"id": c["id"], "kind": c["kind"], **json.loads(c["payload"] or "{}")} for c in cmds]


def done(store, cmd_id: int, result: str) -> None:
    _ensure(store)
    store.execute("UPDATE phone_cmds SET status = 'done', result = ? WHERE id = ?", (result[:6000], cmd_id))


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
    """The named place you're at. Your own saved places (home, gym...) win over built-in landmarks."""
    try:
        saved = {k: tuple(v) for k, v in json.loads(store.get("places:saved") or "{}").items()}
    except ValueError:
        saved = {}
    for pool in (saved, places(store)):
        best = min(((n, _km((lat, lon), p)) for n, p in pool.items()), key=lambda x: x[1], default=None)
        if best and best[1] <= radius_km:
            return best[0]
    return None


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
    # living notifications (#48): every one that isn't private flies onto the laptop as a hologram card
    bus.publish({"type": "notice", "app": MESSAGING.get(app, app), "sender": sender[:60], "text": text[:180], "urgent": bool(c["urgent"])})
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


# ------------------------------------------------------------------ phone powers (calls, apps, music, shopping...)
SHOPS = {"shopee": "https://shopee.sg/search?keyword={q}", "shein": "https://sg.shein.com/pdsearch/{q}/",
         "lazada": "https://www.lazada.sg/catalog/?q={q}", "amazon": "https://www.amazon.sg/s?k={q}",
         "carousell": "https://www.carousell.sg/search/{q}", "taobao": "https://s.taobao.com/search?q={q}",
         "zalora": "https://www.zalora.sg/search?q={q}", "uniqlo": "https://www.uniqlo.com/sg/en/search?q={q}"}


def wait_result(store, cmd_id: int, seconds: float = 25) -> str | None:
    """Wait for the phone to carry out a command (it checks in every few seconds while the screen is on)."""
    import time
    end = time.time() + seconds
    while time.time() < end:
        row = store.query("SELECT status, result FROM phone_cmds WHERE id = ?", (cmd_id,))
        if row and row[0]["status"] == "done":
            return row[0]["result"]
        time.sleep(0.7)
    return None


def _send(ctx: ToolContext, kind: str, wait: float = 12, **payload) -> dict:
    if not state(ctx.store):
        return {"error": "The phone app hasn't linked yet (open the JARVIS app on the phone once)."}
    cid = queue(ctx.store, kind, **payload)
    res = wait_result(ctx.store, cid, wait) if wait else None
    if res is None:
        return {"queued": True, "note": "The phone will do it as soon as it checks in (it may be asleep)."}
    try:
        return {"result": json.loads(res)}
    except ValueError:
        return {"result": res}


@tool("phone_call", "Call someone from the owner's phone, by contact name or number. Only when the owner asks to call "
      "someone.", {"name": S, "number": S})
def phone_call(ctx: ToolContext, name: str = "", number: str = "") -> dict:
    return _send(ctx, "call", name=name.strip(), number=re.sub(r"[^\d+]", "", number))


@tool("phone_contacts", "Look up a contact's phone number on the owner's phone by (part of) their name.", {"name": S}, ["name"])
def phone_contacts(ctx: ToolContext, name: str) -> dict:
    return _send(ctx, "contacts", wait=20, name=name.strip()[:40])


@tool("phone_alarm", "Set an alarm on the owner's phone. time is HH:MM (24h).", {"time": S, "label": S}, ["time"])
def phone_alarm(ctx: ToolContext, time: str, label: str = "") -> dict:
    m = re.match(r"^\s*(\d{1,2})[:.](\d{2})\s*$", time)
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        return {"error": "time must be HH:MM, e.g. 06:30"}
    return _send(ctx, "alarm", hour=int(m.group(1)), minute=int(m.group(2)), label=label[:60])


@tool("phone_timer", "Start a countdown timer on the owner's phone.", {"minutes": {"type": "number"}, "label": S}, ["minutes"])
def phone_timer(ctx: ToolContext, minutes: float, label: str = "") -> dict:
    return _send(ctx, "timer", seconds=int(max(0.1, float(minutes)) * 60), label=label[:60])


@tool("phone_torch", "Turn the phone's torch (flashlight) on or off.", {"on": B}, ["on"])
def phone_torch(ctx: ToolContext, on: bool) -> dict:
    return _send(ctx, "torch", on=bool(on))


@tool("phone_volume", "Set the phone's media volume (0-100).", {"level": {"type": "integer"}}, ["level"])
def phone_volume(ctx: ToolContext, level: int) -> dict:
    return _send(ctx, "volume", level=max(0, min(100, int(level))))


@tool("phone_music", "Control music on the phone: action play | pause | toggle | next | previous. Or give `query` to "
      "play a song/artist/playlist (optionally in app: spotify, youtube music, youtube).",
      {"action": S, "query": S, "app": S})
def phone_music(ctx: ToolContext, action: str = "toggle", query: str = "", app: str = "") -> dict:
    if query.strip():
        return _send(ctx, "play", query=query.strip()[:120], app=app.strip().lower())
    return _send(ctx, "media", action=(action or "toggle").lower())


@tool("phone_open", "Open an app on the owner's phone by name (e.g. 'Gmail', 'Camera', 'Shopee', 'YouTube') or open a "
      "link (url). Bank and finance apps are blocked.", {"app": S, "url": S})
def phone_open(ctx: ToolContext, app: str = "", url: str = "") -> dict:
    if blocked(app, url):
        return {"error": REFUSAL}
    if url.strip():
        if not url.startswith(("https://", "http://")):
            return {"error": "url must start with https://"}
        return _send(ctx, "link", url=url.strip())
    if app.strip().lower() in ("camera", "video camera"):
        return _send(ctx, "camera", video=app.strip().lower().startswith("video"))
    return _send(ctx, "app", name=app.strip()[:60])


@tool("phone_youtube", "Search YouTube on the owner's phone (opens the YouTube app with the results).", {"query": S}, ["query"])
def phone_youtube(ctx: ToolContext, query: str) -> dict:
    from urllib.parse import quote_plus
    return _send(ctx, "link", url="https://www.youtube.com/results?search_query=" + quote_plus(query.strip()))


@tool("phone_shop", "Search a shopping app on the owner's phone: shopee, shein, lazada, amazon, carousell, taobao, "
      "zalora or uniqlo. Opens the search results in the app; the owner chooses and pays themselves (never buy or pay).",
      {"store": S, "query": S}, ["store", "query"])
def phone_shop(ctx: ToolContext, store: str, query: str) -> dict:
    from urllib.parse import quote, quote_plus
    key = next((k for k in SHOPS if k in store.lower()), None)
    if key is None:
        return {"error": f"Shops I know: {', '.join(SHOPS)}"}
    q = quote(query.strip()) if "{q}/" in SHOPS[key] else quote_plus(query.strip())
    return _send(ctx, "link", url=SHOPS[key].format(q=q))


@tool("phone_navigate", "Show directions to a place on JARVIS's own map in the phone app (never Google Maps).",
      {"to": S}, ["to"])
def phone_navigate(ctx: ToolContext, to: str) -> dict:
    from urllib.parse import quote
    return _send(ctx, "open", url="/map.html?nav=" + quote(to.strip()[:120]), title="JARVIS · route ready",
                 text=f"Tap for directions to {to.strip()[:60]}")


@tool("phone_email", "Open a ready-written email on the phone for the owner to check and send (never sent by you).",
      {"to": S, "subject": S, "body": S}, ["subject", "body"])
def phone_email(ctx: ToolContext, subject: str, body: str, to: str = "") -> dict:
    if is_secret(body) or blocked(to, subject, body):
        return {"error": REFUSAL}
    return _send(ctx, "email", to=to.strip(), subject=subject[:200], body=body[:5000])


@tool("phone_screen_time", "How long the owner used each app on their phone today (screen time).")
def phone_screen_time(ctx: ToolContext) -> dict:
    return _send(ctx, "screentime", wait=25)


@tool("phone_latest_photo", "Look at the newest photo or screenshot on the owner's phone and answer a question about it.",
      {"question": S})
def phone_latest_photo(ctx: ToolContext, question: str = "") -> dict:
    out = _send(ctx, "photo", wait=40)
    path = out.get("result")
    if not isinstance(path, str) or not path.endswith(".jpg"):
        return out
    from pathlib import Path
    from . import vision
    try:
        seen = vision.ask(Path(path).read_bytes(), "image/jpeg", vision.PROMPT + (f"\nThe owner asks: {question}" if question else ""))
    except Exception as exc:  # noqa: BLE001
        return {"error": f"I got the photo but couldn't look at it: {exc}", "file": path}
    return {"photo": Path(path).name, "what_it_shows": seen}


@tool("phone_screen", "Read what's on the owner's phone screen right now (the open app's text), e.g. 'what's this on my "
      "phone?'. Never reads bank, finance or password screens.")
def phone_screen(ctx: ToolContext) -> dict:
    out = _send(ctx, "screen", wait=15)
    res = out.get("result")
    if isinstance(res, dict):
        from .guard import mask_numbers
        lines = [ln for ln in str(res.get("text", "")).splitlines() if not is_secret(ln) and not blocked(ln)]
        res["text"] = mask_numbers("\n".join(lines))   # codes, passwords and bank lines dropped; long numbers masked
    return out


# ------------------------------------------------------------------ "your phone can't reach me" nudge
LINK_LOST_HOURS = 2


def link_watch(store, now: datetime | None = None, send=None) -> str | None:
    """If the phone app was linked but hasn't checked in for a while (usually Tailscale switched off on the phone),
    tell the owner once on Telegram. Checks in every minute even with the screen off, so a long gap means no link."""
    st = state(store)
    if not st.get("at"):
        return None
    now = now or datetime.now(settings.tz)
    last = datetime.fromisoformat(st["at"])
    gap_h = (now - last).total_seconds() / 3600
    warned = store.get("phone:link_warned") or ""
    if gap_h < LINK_LOST_HOURS:
        if warned:
            store.set("phone:link_warned", "")   # back online: ready to warn again next time
        return None
    if warned == st["at"]:
        return None   # already told them about this gap
    store.set("phone:link_warned", st["at"])
    msg = (f"📱 Your phone hasn't reached me for {int(gap_h)} hours, Sir. Is Tailscale switched on on the phone? "
           "Open the Tailscale app → Connected, then open JARVIS.")
    if send is None:
        from . import telegram as tg
        send = tg.send if tg.ready() else None
    if send:
        send(msg)
    return msg
