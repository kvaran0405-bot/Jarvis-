"""Phase 3 tools: deep memory (find anything, people met, agent coaching), home manager (groceries, expiry dates),
the Stark Daily newspaper, and the no-AI butler checks (leave-now alerts, water & posture nudges)."""
from __future__ import annotations

import json
import math
import re
from datetime import date, datetime, timedelta

from .config import settings
from .tools import I, S, ToolContext, tool

B = {"type": "boolean"}


# ================================================================== deep memory
@tool("find_anything", "Lost and found: search EVERYTHING JARVIS knows for something - notes, the owner's files, "
      "lecture transcripts, tasks, calendar, contacts, clients, past conversations and (if set up) e-mail. "
      "Use it for 'where is…', 'when did I…', 'what did X say about…'.", {"query": S}, ["query"])
def find_anything(ctx: ToolContext, query: str) -> dict:
    s, like = ctx.store, f"%{query}%"
    words = [w for w in re.findall(r"[A-Za-z0-9]{3,}", query)]
    wl = [f"%{w}%" for w in words] or [like]

    def q(sql_tpl: str, cols: tuple, limit: int = 6):
        rows, seen = [], set()
        for w in wl:
            for r in s.query(sql_tpl + f" LIMIT {limit}", tuple(w for _ in cols)):
                key = json.dumps(r, sort_keys=True, default=str)
                if key not in seen:
                    seen.add(key)
                    rows.append(r)
        return rows[:limit]
    out = {
        "notes": [{"id": r["id"], "title": r["title"], "excerpt": r["body"][:240]} for r in
                  q("SELECT id, title, body FROM notes WHERE title LIKE ? OR body LIKE ? ORDER BY id DESC", ("t", "b"))],
        "tasks": q("SELECT id, title, status, due FROM tasks WHERE title LIKE ? OR notes LIKE ? ORDER BY id DESC", ("t", "n")),
        "events": q("SELECT id, title, start, location FROM events WHERE title LIKE ? OR location LIKE ? OR notes LIKE ? "
                    "ORDER BY start DESC", ("t", "l", "n")),
        "contacts": q("SELECT id, name, phone, email, relationship, notes FROM contacts WHERE name LIKE ? OR notes LIKE ? "
                      "OR relationship LIKE ?", ("n", "o", "r")),
        "clients": q("SELECT id, client, event_type, event_date, status, notes FROM gigs WHERE client LIKE ? OR notes LIKE ? "
                     "OR venue LIKE ?", ("c", "n", "v")),
        "conversations": q("SELECT agent, message, created FROM activity WHERE kind IN ('command','reply') AND message LIKE ? "
                           "ORDER BY id DESC", ("m",), 8),
        "lectures": [{"id": r["id"], "title": r["title"]} for r in
                     q("SELECT id, title FROM lectures WHERE title LIKE ? OR transcript LIKE ?", ("t", "x"))],
    }
    from . import files_index
    out["files"] = files_index.search(s, query, 6)
    from . import channels as ch
    if ch.email_read_ready():
        from .life import search_email
        try:
            out["email"] = search_email(ctx, query, 120).get("results", [])[:6]
        except Exception:  # noqa: BLE001
            pass
    return {k: v for k, v in out.items() if v}


@tool("log_meeting", "Remember someone the owner met (at an event, a class, an interview): who, where, what about, "
      "and anything personal worth remembering. Builds the network radar.",
      {"person": S, "where": S, "notes": S, "phone": S, "email": S}, ["person"])
def log_meeting(ctx: ToolContext, person: str, where: str = "", notes: str = "", phone: str = "", email: str = "") -> dict:
    found = ctx.store.query("SELECT * FROM contacts WHERE lower(name) = lower(?)", (person,))
    line = f"{ctx.today()}: met at {where or '?'} - {notes}".strip(" -")
    if found:
        c = found[0]
        ctx.store.execute("UPDATE contacts SET notes = ? WHERE id = ?", (((c["notes"] or "") + "\n" + line).strip(), c["id"]))
        return {"updated_contact": c["id"]}
    from .tools import REGISTRY
    out = REGISTRY["add_contact"].fn(ctx, name=person, phone=phone, email=email, relationship="network", notes=line)
    return {"new_contact": out}


@tool("network_radar", "People in the owner's network not contacted for a while, with what they were about - for "
      "reconnect nudges and to prepare before events.", {"days": I})
def network_radar(ctx: ToolContext, days: int = 60) -> list:
    rows = ctx.store.query("SELECT id, name, relationship, notes FROM contacts WHERE notes != '' ORDER BY id DESC LIMIT 80")
    out = []
    for r in rows:
        dates = re.findall(r"(\d{4}-\d{2}-\d{2}):", r["notes"] or "")
        last = max(dates) if dates else None
        if not last or (ctx.now().date() - date.fromisoformat(last)).days >= days:
            out.append({**r, "last_noted": last, "notes": (r["notes"] or "")[-300:]})
    return out[:20]


@tool("coach_agent", "Give another agent a note about how to work with the owner (tone, preferences, what worked). "
      "The note goes into that agent's private notebook, so their personality grows with the owner.",
      {"agent": S, "note": S}, ["agent", "note"])
def coach_agent(ctx: ToolContext, agent: str, note: str) -> dict:
    from .agents import AGENTS
    a = agent.upper()
    if a not in AGENTS or AGENTS[a].hidden:
        return {"error": f"No agent {agent}"}
    ctx.store.add_agent_note(a, note[:400])
    return {"saved_for": a}


# ================================================================== home manager
def _grocery(store) -> list:
    try:
        return json.loads(store.get("home:grocery") or "[]")
    except ValueError:
        return []


@tool("grocery_list", "The household grocery list. action: add | remove | clear | show. items: list of things.",
      {"action": {"type": "string", "enum": ["add", "remove", "clear", "show"]}, "items": {"type": "array", "items": S}},
      ["action"])
def grocery_list(ctx: ToolContext, action: str, items: list | None = None) -> dict:
    cur = _grocery(ctx.store)
    items = [i.strip() for i in (items or []) if i and i.strip()]
    if action == "add":
        for i in items:
            if i.lower() not in {c.lower() for c in cur}:
                cur.append(i)
    elif action == "remove":
        low = {i.lower() for i in items}
        cur = [c for c in cur if c.lower() not in low]
    elif action == "clear":
        cur = []
    ctx.store.set("home:grocery", json.dumps(cur))
    return {"grocery_list": cur}


@tool("track_expiry", "Track something that expires or renews (passport, IC, licence, insurance, warranty, lease, "
      "membership). Adds it to the calendar and reminders 60, 30 and 7 days before.",
      {"name": S, "expires": {"type": "string", "description": "YYYY-MM-DD"}, "notes": S}, ["name", "expires"])
def track_expiry(ctx: ToolContext, name: str, expires: str, notes: str = "") -> dict:
    from .actions import _queue
    from .tools import REGISTRY
    REGISTRY["add_event"].fn(ctx, title=f"Expires: {name}", start=expires[:10], area="personal", notes=notes)
    when = date.fromisoformat(expires[:10])
    made = 0
    for d in (60, 30, 7):
        at = when - timedelta(days=d)
        if at > ctx.now().date():
            _queue(ctx, "telegram", "", f"⏳ {name} expires in {d} days ({when:%d %b %Y}). {notes}".strip(),
                   reason="expiry reminder", send_at=f"{at.isoformat()}T09:00")
            made += 1
    return {"tracked": name, "reminders": made}


# ================================================================== The Stark Daily
@tool("publish_newspaper", "Publish today's 'Stark Daily': a one-page newspaper PDF for the owner (sent to Telegram and "
      "saved as a report). headline + lead about their day, 3-6 stories [{section, title, body}] mixing their schedule "
      "and real news they care about (finance, events industry, Singapore), and a quote of the day.",
      {"headline": S, "lead": S, "stories": {"type": "array", "items": {"type": "object", "properties": {
          "section": S, "title": S, "body": S}, "required": ["title", "body"]}}, "quote": S},
      ["headline", "lead", "stories"])
def publish_newspaper(ctx: ToolContext, headline: str, lead: str, stories: list, quote: str = "") -> dict:
    from . import devices
    from .pdf import MARGIN, PAGE_W, Doc
    now = ctx.now()
    d = Doc()
    ink, grey = (0.1, 0.09, 0.08), (0.35, 0.33, 0.3)
    d.rect(0, 0, PAGE_W, 842, (0.95, 0.93, 0.88))
    d.y -= 8
    d.text(PAGE_W / 2, d.y - 24, "The Stark Daily", 38, True, ink, "center", serif=True)
    d.y -= 40
    d.line(MARGIN, d.y, PAGE_W - MARGIN, d.y, 2, ink)
    d.y -= 13
    w = ""
    try:
        from .hud import weather_now
        wd = weather_now()
        if wd and wd.get("today"):
            w = f"Singapore · {round(wd['today']['max_c'])}° {wd['today']['sky']}"
    except Exception:  # noqa: BLE001
        pass
    d.text(MARGIN, d.y, now.strftime("%A, %d %B %Y"), 9, False, grey, serif=True)
    d.text(PAGE_W / 2, d.y, w, 9, False, grey, "center", serif=True)
    d.text(PAGE_W - MARGIN, d.y, f"For {settings.owner_name}'s eyes only", 9, False, grey, "right", serif=True)
    d.y -= 6
    d.line(MARGIN, d.y, PAGE_W - MARGIN, d.y, .7, ink)
    d.y -= 8
    d.paragraph(headline, 22, True, color=ink, gap=1.15, serif=True)
    d.y -= 4
    d.paragraph(lead, 11.5, color=grey, gap=1.4, serif=True)
    d.y -= 10
    d.line(MARGIN, d.y, PAGE_W - MARGIN, d.y, .5, grey)
    # two columns
    col_w = (PAGE_W - 2 * MARGIN - 20) / 2
    top = d.y - 6
    ys = [top, top]
    for st in stories[:6]:
        c = 0 if ys[0] >= ys[1] else 1
        x = MARGIN + c * (col_w + 20)
        d.y = ys[c]
        if d.y < 140:
            continue
        if st.get("section"):
            d.y -= 12
            d.text(x, d.y, st["section"].upper(), 7.5, True, (0.6, 0.15, 0.1))
        d.paragraph(st["title"], 13, True, x=x, width=col_w, color=ink, gap=1.2, serif=True)
        d.paragraph(st["body"], 9.5, x=x, width=col_w, color=(0.2, 0.19, 0.17), gap=1.45, serif=True)
        d.y -= 12
        ys[c] = d.y
    if quote:
        d.y = min(ys) - 6
        d.line(MARGIN, d.y, PAGE_W - MARGIN, d.y, .5, grey)
        d.y -= 4
        d.paragraph(f"“{quote}”", 11, x=MARGIN + 30, width=PAGE_W - 2 * MARGIN - 60, color=grey, serif=True)
    # today at a glance, straight from the calendar and tasks
    today = now.date().isoformat()
    evs = [e for e in ctx.store.list_events(today, (now.date() + timedelta(days=1)).isoformat())]
    due = [t for t in ctx.store.list_tasks("open", limit=200) if t["due"] and t["due"][:10] <= today]
    if (evs or due) and d.y > 180:
        d.y -= 26
        d.rect(MARGIN, d.y - 8 - 14 * min(12, len(evs) + len(due)), PAGE_W - 2 * MARGIN, 22 + 14 * min(12, len(evs) + len(due)),
               (0.9, 0.87, 0.8))
        d.text(MARGIN + 10, d.y, "TODAY AT A GLANCE", 8, True, (0.6, 0.15, 0.1))
        for e in evs[:8]:
            d.y -= 14
            d.text(MARGIN + 10, d.y, e["start"][11:16] if len(e["start"]) > 10 else "all day", 9.5, True, ink, serif=True)
            d.text(MARGIN + 70, d.y, f"{e['title']}{' · ' + e['location'] if e.get('location') else ''}"[:80], 9.5, False, ink, serif=True)
        for t in due[:4]:
            d.y -= 14
            d.text(MARGIN + 10, d.y, "due", 9.5, True, (0.6, 0.15, 0.1), serif=True)
            d.text(MARGIN + 70, d.y, t["title"][:80], 9.5, False, ink, serif=True)
    path = d.save(devices.WORKSPACE / "Stark Daily" / f"Stark-Daily-{now:%Y-%m-%d}.pdf")
    body = f"# {headline}\n\n{lead}\n\n" + "\n\n".join(
        f"**{(s.get('section') or '').upper()}** · **{s['title']}**\n{s['body']}" for s in stories) + (f"\n\n> {quote}" if quote else "")
    rid = ctx.store.save_report("newspaper", ctx.agent, f"The Stark Daily · {now:%d %b}", body)
    ctx.bus.publish({"type": "data", "what": "reports"})
    from . import telegram as tg
    sent = False
    if tg.ready():
        try:
            tg.send_file(str(path), caption=f"📰 The Stark Daily · {headline}")
            sent = True
        except Exception:  # noqa: BLE001
            pass
    return {"pdf": str(path), "report_id": rid, "telegram": sent}


# ================================================================== no-AI butler checks (run by the scheduler)
def _km(a: tuple[float, float], b: tuple[float, float]) -> float:
    return 111 * math.hypot(a[0] - b[0], (a[1] - b[1]) * math.cos(math.radians(a[0])))


def travel_minutes(place: str | None) -> int:
    import os
    base = int(os.environ.get("JARVIS_TRAVEL_MINUTES", "40") or 40)
    home = os.environ.get("JARVIS_HOME_LATLON", "").strip()
    if place and home:
        from .holo import LANDMARKS
        try:
            lat, _, lon = home.partition(",")
            p = LANDMARKS[place]
            return int(12 + _km((float(lat), float(lon)), (p[0], p[1])) * 2.6)
        except (KeyError, ValueError):
            pass
    return base


def _trip_estimate(store, event: dict, loc: str, now: datetime) -> dict | None:
    """Travel time from where the owner is now (live route, traffic, rain), remembered for 20 minutes per event."""
    import json as _json
    key = f"leave_est:{event['id']}"
    try:
        cached = _json.loads(store.get(key) or "null")
        if cached and now - datetime.fromisoformat(cached["at"]) < timedelta(minutes=20):
            return cached
    except (ValueError, KeyError):
        pass
    try:
        from . import navigate
        o = navigate.options(store, loc)
    except Exception:  # noqa: BLE001
        return None
    if "error" in o:
        return None
    best = next(x for x in o["options"] if x["mode"] == o["best"])
    grab = next((x for x in o["options"] if x["mode"] == "grab"), None)
    how = f"{best['label'].lower()} ~{best['min']} min"
    if grab and best["mode"] != "grab":
        how += f" (Grab ~{grab['min']} min, ${grab['price'][0]}–{grab['price'][1]})"
    elif grab:
        how += f" (${grab['price'][0]}–{grab['price'][1]})"
    out = {"at": now.isoformat(), "min": best["min"], "how": how}
    store.set(key, _json.dumps(out))
    return out


def leave_now_check(store, bus) -> list[str]:
    """Telegram + spoken 'leave now' alerts for upcoming events that have a place (including just after midnight). Once per event."""
    from . import telegram as tg
    from .holo import place_of
    from .speech import announce
    now = datetime.now(settings.tz)
    today = now.date().isoformat()
    sent = []
    for e in store.list_events(today, (now.date() + timedelta(days=2)).isoformat()):
        loc = (e.get("location") or "").strip()
        if len(e["start"]) <= 10 or not loc or re.search(r"zoom|teams|online|meet\.google", loc, re.I):
            continue
        key = f"leave:{e['id']}:{e['start']}"
        if store.get(key):
            continue
        place = place_of(f"{e['title']} {loc}")
        start = datetime.fromisoformat(e["start"]).replace(tzinfo=settings.tz)
        if start - now > timedelta(hours=3):
            continue
        est = _trip_estimate(store, e, loc, now)   # real route from where you are, traffic, rain, Grab price
        mins = est["min"] if est else travel_minutes(place)
        leave_at = start - timedelta(minutes=mins + 10)
        if not (leave_at <= now < start):
            continue
        store.set(key, now.isoformat())
        rain = ""
        try:
            from .hud import weather_now
            w = weather_now()
            hrs = w["today"]["rainy_hours"] if w else []
            if isinstance(hrs, list) and any(abs(int(h[:2]) - start.hour) <= 1 for h in hrs):
                rain = " Rain around then, so take a Grab or an umbrella."
        except Exception:  # noqa: BLE001
            pass
        left = max(0, int((start - now).total_seconds() // 60) - mins)
        how = f" Best: {est['how']}." if est and est.get("how") else ""
        msg = (f"Time to leave{' in ' + str(left) + ' min' if left > 2 else ''} for {e['title']} at {start:%H:%M} "
               f"({loc}).{how}{rain}")
        if tg.ready():
            try:
                tg.send(f"🚗 {msg}")
            except Exception:  # noqa: BLE001
                pass
        announce(bus, "JARVIS", f"Sir, {msg}", phone=False)
        from . import phonelink
        import urllib.parse as _up
        phonelink.queue(store, "notify", title="🚗 Time to leave", text=msg, url="/map.html?nav=" + _up.quote(loc))
        sent.append(msg)
    return sent


NUDGES = ["Water break, Sir. Your brain is mostly made of it.", "Posture check: shoulders back, screen at eye level.",
          "You've been at it a while. Stand up and stretch for a minute.", "Eyes off the screen for 20 seconds. Look far away.",
          "Hydration reminder. The suit runs better on water than on bubble tea."]


def wellness_nudge(store, bus) -> str | None:
    """A gentle water / posture nudge while the owner is at the laptop (never in focus mode or quiet hours)."""
    import os
    import random
    from .life import in_focus
    from .speech import in_quiet_hours
    if os.environ.get("JARVIS_NUDGES", "on").lower() == "off" or in_focus(store) or in_quiet_hours():
        return None
    now = datetime.now(settings.tz)
    if not (10 <= now.hour < 21) or bus.screens == 0:
        return None
    last = store.get("owner:last_seen")
    if not last or datetime.fromisoformat(last) < now - timedelta(minutes=50):
        return None   # not actively at the laptop
    line = random.choice(NUDGES)
    bus.publish({"type": "nudge", "agent": "BANNER", "text": line})
    return line
