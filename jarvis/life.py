"""Tools for the friend layer, study, the events business (crew, invoices, rundowns), fitness, focus and housekeeping."""
from __future__ import annotations

import re
import shutil
import threading
import urllib.parse
from datetime import date, datetime, timedelta
from pathlib import Path

from .config import ROOT
from .tools import I, S, ToolContext, tool

N = {"type": "number"}
B = {"type": "boolean"}


# ================================================================== celebrations
CHEERS = {
    "JARVIS": ["[proud] Splendidly done Sir.", "[amused] Another one off the list. I'm almost impressed Sir."],
    "FRIDAY": ["[excited] Boss! That's done and dusted!", "[cheerful] Look at you go!"],
    "ATHENA": ["[proud] Brilliant work. That one counts.", "[warm] Well done, truly."],
    "PEPPER": ["[proud] And that's how a business grows.", "[warm] Lovely. Booked and beautiful."],
    "STEVE": ["[proud] That's what showing up looks like!", "[cheerful] Streak's alive, soldier!"],
    "ZEUS": ["[triumphant] Victory. Next.", "[triumphant] That's how winners move."],
}


def celebrate(bus, agent: str, what: str) -> None:
    """Confetti on the dashboard and a quick proud line. Uses no AI."""
    import random
    from .speech import announce
    line = random.choice(CHEERS.get(agent, CHEERS["JARVIS"]))
    bus.publish({"type": "celebrate", "agent": agent, "text": what})
    announce(bus, agent, line, phone=False)


# ================================================================== friend layer
@tool("log_mood", "Record how the owner is feeling today (from a check-in or something they said). 1 = awful, "
      "5 = great. Any field can be left out.", {"mood": I, "energy": I, "sleep": I, "note": S})
def log_mood(ctx: ToolContext, mood: int | None = None, energy: int | None = None, sleep: int | None = None,
             note: str = "") -> dict:
    from .store import now_iso
    ctx.store.execute("INSERT INTO mood (day, mood, energy, sleep, note, created) VALUES (?,?,?,?,?,?)",
                      (ctx.today(), mood, energy, sleep, note, now_iso()))
    return {"logged": True}


@tool("mood_report", "The owner's mood, energy and sleep over the last N days (default 14), to spot patterns "
      "(low streaks, bad sleep, stress before deadlines).", {"days": I})
def mood_report(ctx: ToolContext, days: int = 14) -> dict:
    since = (ctx.now().date() - timedelta(days=days)).isoformat()
    rows = ctx.store.query("SELECT day, mood, energy, sleep, note FROM mood WHERE day >= ? ORDER BY id", (since,))

    def avg(k):
        v = [r[k] for r in rows if r[k]]
        return round(sum(v) / len(v), 1) if v else None
    return {"entries": rows, "average": {"mood": avg("mood"), "energy": avg("energy"), "sleep": avg("sleep")}}


@tool("log_gratitude", "Save one good thing from the owner's day (from the evening check-in).", {"text": S}, ["text"])
def log_gratitude(ctx: ToolContext, text: str) -> dict:
    ctx.store.execute("INSERT INTO gratitude (day, text) VALUES (?,?)", (ctx.today(), text))
    return {"saved": True}


@tool("good_moments", "The owner's saved good moments over the last N days (default 31), for the monthly look-back.",
      {"days": I})
def good_moments(ctx: ToolContext, days: int = 31) -> list:
    since = (ctx.now().date() - timedelta(days=days)).isoformat()
    return ctx.store.query("SELECT day, text FROM gratitude WHERE day >= ? ORDER BY day", (since,))


@tool("add_important_date", "Remember a yearly date: a birthday or anniversary of someone in the owner's life. "
      "date = YYYY-MM-DD or MM-DD.", {"person": S, "date": S, "kind": {"type": "string", "enum": [
          "birthday", "anniversary", "other"]}, "notes": S}, ["person", "date"])
def add_important_date(ctx: ToolContext, person: str, date: str, kind: str = "birthday", notes: str = "") -> dict:
    m = re.match(r"^(?:(\d{4})-)?(\d{2})-(\d{2})$", date.strip())
    if not m:
        return {"error": "Use YYYY-MM-DD or MM-DD"}
    ctx.store.execute("INSERT INTO dates (person, kind, month_day, year, notes) VALUES (?,?,?,?,?)",
                      (person, kind, f"{m.group(2)}-{m.group(3)}", int(m.group(1)) if m.group(1) else None, notes))
    return {"saved": True}


@tool("upcoming_dates", "Birthdays and anniversaries in the next N days (default 14).", {"days": I})
def upcoming_dates(ctx: ToolContext, days: int = 14) -> list:
    today = ctx.now().date()
    out = []
    for r in ctx.store.query("SELECT * FROM dates"):
        mm, dd = (int(x) for x in r["month_day"].split("-"))
        for year in (today.year, today.year + 1):
            try:
                d = date(year, mm, dd)
            except ValueError:   # 29 Feb
                d = date(year, 3, 1)
            if 0 <= (d - today).days <= days:
                out.append({"person": r["person"], "kind": r["kind"], "date": d.isoformat(),
                            "in_days": (d - today).days, "turning": year - r["year"] if r["year"] else None,
                            "notes": r["notes"]})
                break
    return sorted(out, key=lambda x: x["in_days"])


@tool("future_letter", "Save a letter from the owner to their future self, delivered on Telegram on a date.",
      {"letter": S, "deliver_on": {"type": "string", "description": "YYYY-MM-DD"}}, ["letter", "deliver_on"])
def future_letter(ctx: ToolContext, letter: str, deliver_on: str) -> dict:
    from .actions import _queue
    return _queue(ctx, "telegram", "", f"💌 A letter from you, written {ctx.today()}:\n\n{letter}",
                  reason="letter to future self", send_at=f"{deliver_on[:10]}T09:00")


# ================================================================== study
@tool("search_my_files", "Search the owner's own notes, slides, PDFs and documents on the laptop (Documents, "
      "OneDrive, Desktop, Downloads). Returns matching passages with the file name and page/slide. Use it for "
      "questions about their courses, readings, assignments and anything they've written.", {"query": S}, ["query"])
def search_my_files(ctx: ToolContext, query: str) -> dict:
    from . import files_index
    hits = files_index.search(ctx.store, query)
    if not hits and not ctx.store.query("SELECT 1 FROM file_index LIMIT 1"):
        threading.Thread(target=files_index.index, args=(ctx.store,), daemon=True).start()
        return {"results": [], "note": "I'm reading the owner's files for the first time now; ask again in a few "
                                       "minutes."}
    return {"results": hits}


@tool("add_exam", "Track an exam: creates a calendar event, starts exam mode (daily quizzes, countdown in the morning "
      "brief) and lets ATHENA plan revision.", {"course": S, "exam_at": {"type": "string", "description":
                                                                         "ISO datetime"}, "topics": S},
      ["course", "exam_at"])
def add_exam(ctx: ToolContext, course: str, exam_at: str, topics: str = "") -> dict:
    from .tools import REGISTRY, local_iso
    when = local_iso(ctx, exam_at)
    eid = ctx.store.execute("INSERT INTO exams (course, exam_at, topics) VALUES (?,?,?)", (course, when, topics))
    REGISTRY["add_event"].fn(ctx, title=f"EXAM: {course}", start=when, area="academic", notes=topics)
    return {"exam_id": eid, "next": "Propose a revision plan (study blocks on the calendar) if there isn't one."}


@tool("list_exams", "Upcoming exams with days left.")
def list_exams(ctx: ToolContext) -> list:
    today = ctx.now().date()
    rows = ctx.store.query("SELECT * FROM exams WHERE status = 'upcoming' AND exam_at >= ? ORDER BY exam_at",
                           (today.isoformat(),))
    for r in rows:
        r["days_left"] = (date.fromisoformat(r["exam_at"][:10]) - today).days
    return rows


@tool("read_aloud", "Turn text, a file on the laptop or a web article into audio and send it to the owner's phone "
      "(to listen on the go). Give exactly one of text / path / url.", {"text": S, "path": S, "url": S, "title": S})
def read_aloud(ctx: ToolContext, text: str = "", path: str = "", url: str = "", title: str = "") -> dict:
    from . import devices, telegram as tg, voice
    if path:
        p = Path(path).expanduser()
        if p.suffix.lower() in (".docx", ".pptx"):
            from .files_index import extract
            text = "\n".join(t for _l, t in extract(p))
        else:
            text = devices.read_file(path, 60000)
        title = title or p.stem
    elif url:
        import html
        import urllib.request
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30) as r:
            raw = r.read(3_000_000).decode("utf-8", "ignore")
        raw = re.sub(r"(?is)<(script|style|nav|footer|header)[^>]*>.*?</\1>", " ", raw)
        paras = re.findall(r"(?is)<p[^>]*>(.*?)</p>", raw)
        text = html.unescape("\n".join(re.sub(r"<[^>]+>", "", x).strip() for x in paras if len(x) > 60))
        title = title or url
    text = text.strip()[:40000]
    if not text:
        return {"error": "Nothing readable found."}
    if not tg.ready():
        return {"error": "Telegram isn't linked, so I can't send the audio to the phone."}
    out = voice.long_audio(ctx.agent if ctx.agent in ("ATHENA", "JARVIS") else "JARVIS", text)
    tg.api_file("sendAudio", "audio", str(out), chat_id=tg.chat_id(), title=(title or "JARVIS reads")[:60])
    return {"sent": True, "minutes": round(len(text) / 900, 1)}


# ================================================================== business: crew, invoices, rundowns
@tool("add_crew", "Add a part-timer to the crew list for the events business.",
      {"name": S, "phone": S, "role": S, "rate": S, "notes": S}, ["name"])
def add_crew(ctx: ToolContext, name: str, phone: str = "", role: str = "", rate: str = "", notes: str = "") -> dict:
    from .store import normalize_phone
    cid = ctx.store.execute("INSERT INTO crew (name, phone, role, rate, notes) VALUES (?,?,?,?,?)",
                            (name, normalize_phone(phone) if phone else "", role, rate, notes))
    return {"crew_id": cid}


@tool("list_crew", "The crew list, with how many events each person did and their no-shows. Pass event_date "
      "(YYYY-MM-DD) to see who's already booked that day.", {"role": S, "event_date": S})
def list_crew(ctx: ToolContext, role: str = "", event_date: str = "") -> list:
    rows = ctx.store.query(
        "SELECT c.*, SUM(gc.status IN ('attended')) AS events_done, SUM(gc.status = 'no-show') AS no_shows "
        "FROM crew c LEFT JOIN gig_crew gc ON gc.crew_id = c.id WHERE c.active = 1 AND c.role LIKE ? "
        "GROUP BY c.id ORDER BY c.name", (f"%{role}%",))
    if event_date:
        busy = {r["crew_id"] for r in ctx.store.query(
            "SELECT gc.crew_id FROM gig_crew gc JOIN gigs g ON g.id = gc.gig_id WHERE g.event_date LIKE ? "
            "AND gc.status IN ('asked','confirmed')", (event_date[:10] + "%",))}
        for r in rows:
            r["booked_that_day"] = r["id"] in busy
    return rows


@tool("assign_crew", "Put crew on an event, or update their status (asked | confirmed | declined | attended | no-show).",
      {"gig_id": I, "crew_ids": {"type": "array", "items": I}, "role": S, "call_time": S,
       "status": {"type": "string", "enum": ["asked", "confirmed", "declined", "attended", "no-show"]}},
      ["gig_id", "crew_ids"])
def assign_crew(ctx: ToolContext, gig_id: int, crew_ids: list, role: str = "", call_time: str = "",
                status: str = "asked") -> dict:
    for cid in crew_ids:
        ctx.store.execute("INSERT INTO gig_crew (gig_id, crew_id, role, call_time, status) VALUES (?,?,?,?,?) "
                          "ON CONFLICT(gig_id, crew_id) DO UPDATE SET status = excluded.status, "
                          "role = COALESCE(NULLIF(excluded.role, ''), role), "
                          "call_time = COALESCE(NULLIF(excluded.call_time, ''), call_time)",
                          (gig_id, int(cid), role, call_time, status))
    return {"updated": len(crew_ids)}


@tool("crew_for_gig", "Who's on an event: names, roles, call times and status.", {"gig_id": I}, ["gig_id"])
def crew_for_gig(ctx: ToolContext, gig_id: int) -> list:
    return ctx.store.query("SELECT c.id, c.name, c.phone, gc.role, gc.call_time, gc.status FROM gig_crew gc "
                           "JOIN crew c ON c.id = gc.crew_id WHERE gc.gig_id = ? ORDER BY gc.role, c.name", (gig_id,))


@tool("crew_message", "Get a shift message to the crew of an event out quickly and safely: sends the owner one "
      "Telegram message with a tap-to-send WhatsApp link per person (the message is already typed in; the owner "
      "presses send). Use {name} in the message for each person's first name.",
      {"gig_id": I, "message": S, "only_status": S}, ["gig_id", "message"])
def crew_message(ctx: ToolContext, gig_id: int, message: str, only_status: str = "") -> dict:
    from . import telegram as tg
    people = [p for p in crew_for_gig(ctx, gig_id) if p["phone"] and (not only_status or p["status"] == only_status)]
    if not people:
        return {"error": "No crew with phone numbers on this event yet (assign_crew first)."}
    lines = []
    for p in people:
        text = message.replace("{name}", p["name"].split()[0])
        lines.append(f"• {p['name']}: https://wa.me/{p['phone']}?text={urllib.parse.quote(text)}")
    if tg.ready():
        tg.send(f"📣 Shift message for gig #{gig_id} - tap each link, WhatsApp opens with it typed, press send:\n\n"
                + "\n".join(lines))
        return {"sent_to_owner": True, "people": len(people)}
    return {"links": lines}


@tool("record_payment", "Record money received from a client for an event (deposit or balance).",
      {"gig_id": I, "amount": N, "note": S}, ["gig_id", "amount"])
def record_payment(ctx: ToolContext, gig_id: int, amount: float, note: str = "") -> dict:
    gig = ctx.store.get_gig(gig_id)
    if not gig:
        return {"error": f"No gig #{gig_id}"}
    paid = float(gig.get("paid") or 0) + float(amount)
    ctx.store.update_gig(gig_id, paid=paid, deposit_paid=1)
    ctx.store.execute("INSERT INTO transactions (amount, category, note, day) VALUES (?,?,?,?)",
                      (float(amount), "business income", f"{gig['client']}: {note}".strip(": "), ctx.today()))
    balance = float(gig.get("quote_total") or 0) - paid
    return {"paid_total": paid, "balance": round(balance, 2)}


@tool("make_invoice", "Make a PDF invoice for an event (from its quote total, minus what's been paid) and send it to "
      "the owner's phone. Attach it with send_email for the client (owner approves).",
      {"gig_id": I, "items": {"type": "array", "items": {"type": "object", "properties": {
          "item": S, "qty": N, "unit_price": N, "details": S}, "required": ["item", "unit_price"]}},
       "due_days": I, "send_to_phone": B}, ["gig_id"])
def make_invoice(ctx: ToolContext, gig_id: int, items: list | None = None, due_days: int = 7,
                 send_to_phone: bool = True) -> dict:
    from .extras import _business_pdf, _money, _nice_date, business_details
    gig = ctx.store.get_gig(gig_id)
    if not gig:
        return {"error": f"No gig #{gig_id}"}
    if not items:
        if not gig["quote_total"]:
            return {"error": "No quote total on this gig: pass the items."}
        items = [{"item": f"{gig['event_type'] or 'Event'} services", "unit_price": gig["quote_total"],
                  "details": "As per quotation"}]
    rows, total = [], 0.0
    for it in items:
        qty = float(it.get("qty") or 1)
        total += qty * float(it["unit_price"])
        rows.append((str(it["item"]), str(it.get("details") or ""), qty, float(it["unit_price"]),
                     qty * float(it["unit_price"])))
    paid = float(gig.get("paid") or 0)
    today = ctx.now().date()
    number = f"INV{today:%y%m%d}-{gig_id:03d}"
    biz = business_details()
    event = ", ".join(str(x) for x in (gig["event_type"], _nice_date(gig["event_date"]), gig["venue"]) if x)
    path = _business_pdf("INVOICE", number, gig["client"], event, rows,
                         [("Total", total, False), ("Paid to date", -paid, False), ("Balance due", total - paid, True)],
                         f"Date: {today:%d %b %Y}   Due: {today + timedelta(days=due_days):%d %b %Y}",
                         biz.get("payment", "Payment by bank transfer or PayNow."),
                         f"Thank you for choosing {biz.get('business name', 'us')}. It was a pleasure.", "Invoices")
    ctx.store.update_gig(gig_id, next_step=f"Balance {_money(total - paid, biz.get('currency', '$'))} due "
                                           f"{today + timedelta(days=due_days):%d %b}")
    if send_to_phone:
        from . import telegram as tg
        if tg.ready():
            tg.send_file(str(path), caption=f"Invoice {number}: balance {_money(total - paid, biz.get('currency', '$'))}")
    return {"invoice": number, "pdf": str(path), "balance": round(total - paid, 2)}


@tool("make_rundown", "Event-day rundown: a minute-by-minute schedule PDF for the crew, sent to the owner's phone. "
      "With remind=true the owner also gets Telegram pings 10 minutes before each item on the day.",
      {"gig_id": I, "items": {"type": "array", "items": {"type": "object", "properties": {
          "time": {"type": "string", "description": "HH:MM"}, "what": S, "who": S}, "required": ["time", "what"]}},
       "remind": B}, ["gig_id", "items"])
def make_rundown(ctx: ToolContext, gig_id: int, items: list, remind: bool = True) -> dict:
    from . import devices, telegram as tg
    from .extras import _nice_date
    from .pdf import MARGIN, PAGE_W, Doc
    gig = ctx.store.get_gig(gig_id)
    if not gig or not gig["event_date"]:
        return {"error": "Gig not found or it has no event date."}
    items = sorted(items, key=lambda x: x["time"])
    d = Doc()
    accent = (0.55, 0.38, 0.12)
    d.y -= 6
    d.text(MARGIN, d.y, f"RUNDOWN · {gig['client']}", 18, True, accent)
    d.y -= 16
    d.text(MARGIN, d.y, ", ".join(x for x in (gig["event_type"], _nice_date(gig["event_date"]), gig["venue"]) if x),
           10, color=(0.35, 0.35, 0.35))
    d.y -= 24
    for it in items:
        d.need(30)
        d.text(MARGIN, d.y, it["time"], 12, True)
        lines = d.wrap(it["what"], 330, 11)
        for k, ln in enumerate(lines):
            d.text(MARGIN + 70, d.y - k * 14, ln, 11)
        if it.get("who"):
            d.text(PAGE_W - MARGIN, d.y, it["who"], 10, color=(0.4, 0.4, 0.4), align="right")
        d.y -= 14 * len(lines) + 6
        d.line(MARGIN, d.y + 4, PAGE_W - MARGIN, d.y + 4)
        d.y -= 8
    crew = crew_for_gig(ctx, gig_id)
    if crew:
        d.y -= 10
        d.text(MARGIN, d.y, "CREW", 9, True, (0.4, 0.4, 0.4))
        for c in crew:
            d.paragraph(f"{c['name']} - {c['role'] or 'crew'}{' - call ' + c['call_time'] if c['call_time'] else ''}", 10)
    safe = re.sub(r"[^A-Za-z0-9]+", "-", gig["client"]).strip("-")[:30]
    path = d.save(devices.WORKSPACE / "Business" / "Rundowns" / f"Rundown-{gig['event_date'][:10]}-{safe}.pdf")
    reminders = 0
    if remind:
        from .actions import _queue
        day = gig["event_date"][:10]
        for it in items:
            try:
                at = datetime.fromisoformat(f"{day}T{it['time']}") - timedelta(minutes=10)
            except ValueError:
                continue
            if at > ctx.now().replace(tzinfo=None):
                _queue(ctx, "telegram", "", f"⏱ In 10 min ({it['time']}): {it['what']}"
                       + (f" - {it['who']}" if it.get("who") else ""), reason="event rundown",
                       send_at=at.isoformat(timespec="minutes"))
                reminders += 1
    if tg.ready():
        tg.send_file(str(path), caption=f"Rundown for {gig['client']} ({len(items)} items)")
    return {"pdf": str(path), "reminders_scheduled": reminders}


# ================================================================== fitness
@tool("log_workout", "Log exercises from a workout. sets: [{exercise, sets, reps, weight_kg, notes}].",
      {"sets": {"type": "array", "items": {"type": "object", "properties": {
          "exercise": S, "sets": I, "reps": I, "weight_kg": N, "notes": S}, "required": ["exercise"]}},
       "day": S}, ["sets"])
def log_workout(ctx: ToolContext, sets: list, day: str = "") -> dict:
    day = day or ctx.today()
    for s in sets:
        ctx.store.execute("INSERT INTO workouts (day, exercise, sets, reps, weight, notes) VALUES (?,?,?,?,?,?)",
                          (day, s["exercise"], s.get("sets"), s.get("reps"), s.get("weight_kg"), s.get("notes", "")))
    ctx.store.log_habit("gym", day)
    streak = workout_streak(ctx.store, ctx.now().date())
    if streak and streak % 7 == 0:
        celebrate(ctx.bus, "STEVE", f"{streak}-day gym streak")
    return {"logged": len(sets), "weekly_streak_days": streak}


def workout_streak(store, today: date) -> int:
    days = {r["day"] for r in store.query("SELECT DISTINCT day FROM workouts")}
    n, d = 0, today
    while d.isoformat() in days:
        n += 1
        d -= timedelta(days=1)
    return n


@tool("workout_history", "Recent workouts and best lifts per exercise (last N days, default 30).", {"days": I})
def workout_history(ctx: ToolContext, days: int = 30) -> dict:
    since = (ctx.now().date() - timedelta(days=days)).isoformat()
    return {"sessions": ctx.store.query("SELECT * FROM workouts WHERE day >= ? ORDER BY day DESC, id LIMIT 200",
                                        (since,)),
            "best": ctx.store.query("SELECT exercise, MAX(weight) AS best_kg, MAX(reps) AS best_reps FROM workouts "
                                    "GROUP BY exercise ORDER BY exercise")}


# ================================================================== focus & protocols
@tool("focus_mode", "'Suit up': start a focus session for N minutes. JARVIS holds non-urgent announcements, opens "
      "focus music if set, and checks in at the end. minutes=0 ends it early.", {"minutes": I, "task": S})
def focus_mode(ctx: ToolContext, minutes: int = 50, task: str = "") -> dict:
    import os
    from . import devices
    if minutes <= 0:
        ctx.store.set("focus:until", "")
        ctx.bus.publish({"type": "focus", "until": None})
        return {"focus": "ended"}
    until = (ctx.now() + timedelta(minutes=minutes)).replace(tzinfo=None).isoformat(timespec="minutes")
    ctx.store.set("focus:until", until)
    ctx.store.set("focus:task", task)
    ctx.store.set("focus:count", str(int(ctx.store.get("focus:count") or 0) + 1))
    music = os.environ.get("JARVIS_FOCUS_MUSIC", "").strip()
    if music:
        try:
            devices.open_url(music)
        except Exception:  # noqa: BLE001
            pass
    closed = []
    for name in [x.strip() for x in os.environ.get("JARVIS_FOCUS_CLOSE", "").split(",") if x.strip()]:
        closed += _close_app(name)
    from .actions import _queue
    _queue(ctx, "telegram", "", f"🛡 Focus session over{': ' + task if task else ''}. How did it go?",
           reason="focus end", send_at=until)
    ctx.bus.publish({"type": "focus", "until": until, "task": task})
    return {"focus_until": until, "closed_apps": closed}


def _close_app(name: str) -> list:
    try:
        import psutil
    except ImportError:
        return []
    out = []
    for p in psutil.process_iter(["name"]):
        if (p.info["name"] or "").lower().startswith(name.lower()):
            try:
                p.terminate()
                out.append(p.info["name"])
            except Exception:  # noqa: BLE001
                pass
    return out


def in_focus(store) -> bool:
    until = store.get("focus:until")
    if not until:
        return False
    from .config import settings
    return datetime.fromisoformat(until) > datetime.now(settings.tz).replace(tzinfo=None)


@tool("clean_slate", "'Clean Slate Protocol': move every open task due today or earlier to tomorrow (or a date).",
      {"to_date": S})
def clean_slate(ctx: ToolContext, to_date: str = "") -> dict:
    to = to_date or (ctx.now().date() + timedelta(days=1)).isoformat()
    moved = 0
    for t in ctx.store.list_tasks("open", limit=500):
        if t["due"] and t["due"][:10] <= ctx.today():
            ctx.store.update_task(t["id"], due=to)
            moved += 1
    ctx.bus.publish({"type": "data", "what": "tasks"})
    return {"moved": moved, "to": to}


# ================================================================== email search, housekeeping
@tool("search_email", "Search the owner's inbox (last N days, default 60) by words in the sender or subject, e.g. "
      "'receipt', 'subscription', 'shipped', 'delivery'. Bank mail is never shown.", {"query": S, "days": I},
      ["query"])
def search_email(ctx: ToolContext, query: str, days: int = 60) -> dict:
    from . import channels as ch
    from .guard import blocked
    if not ch.email_read_ready():
        return {"error": "E-mail isn't set up yet (JARVIS_SMTP_USER / JARVIS_SMTP_PASSWORD in .env)."}
    words = [w.lower() for w in query.split() if w]
    hits = []
    for m in ch.recent_mail(days=days, limit=600):
        hay = f"{m.get('from', '')} {m.get('subject', '')} {m.get('body', '')}".lower()
        if any(w in hay for w in words) and not blocked(m.get("from"), m.get("subject"), m.get("body")):
            hits.append({"uid": m["uid"], "date": m["date"], "from": m["from"], "subject": m["subject"],
                         "excerpt": (m.get("body") or "")[:300]})
    return {"results": hits[:40]}


@tool("tidy_laptop", "Weekly housekeeping: files in Downloads untouched for 30+ days move into Downloads\\Old\\<month> "
      "(nothing is deleted), and JARVIS's own data and profile are backed up to ~/JARVIS/Backups (last 4 kept).",
      {"dry_run": B})
def tidy_laptop(ctx: ToolContext, dry_run: bool = False) -> dict:
    return housekeeping(dry_run)


def housekeeping(dry_run: bool = False) -> dict:
    import time
    from . import devices
    dl = Path.home() / "Downloads"
    moved = []
    cutoff = time.time() - 30 * 86400
    if dl.exists():
        for p in dl.iterdir():
            if p.name == "Old" or p.name.startswith((".", "~$")) or p.name.endswith((".crdownload", ".part")):
                continue
            try:
                if p.stat().st_mtime < cutoff:
                    dest = dl / "Old" / datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m")
                    moved.append(p.name)
                    if not dry_run:
                        dest.mkdir(parents=True, exist_ok=True)
                        shutil.move(str(p), str(dest / p.name))
            except OSError:
                continue
    backup = ""
    if not dry_run:
        folder = devices.WORKSPACE / "Backups" / datetime.now().strftime("%Y-%m-%d")
        folder.mkdir(parents=True, exist_ok=True)
        for f in ("profile.md", "business.md", ".env"):
            if (ROOT / f).exists() and f != ".env":   # never copy secrets around
                shutil.copy2(ROOT / f, folder / f)
        db = ROOT / "data" / "jarvis.db"
        if db.exists():
            import sqlite3
            src = sqlite3.connect(str(db))
            dst = sqlite3.connect(str(folder / "jarvis.db"))
            src.backup(dst)
            src.close()
            dst.close()
        olds = sorted((devices.WORKSPACE / "Backups").iterdir())
        for old in olds[:-4]:
            shutil.rmtree(old, ignore_errors=True)
        backup = str(folder)
    return {"moved_to_old": len(moved), "examples": moved[:10], "backup": backup}
