"""Tools for the lecture recorder and the events-business kit (PEPPER)."""
from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

from . import lectures
from .config import ROOT
from .tools import I, S, ToolContext, tool


# ------------------------------------------------------------------ lecture & meeting recorder
@tool("start_recording", "Start recording a lecture, class or meeting on the laptop's microphone. When it's stopped, "
      "it is transcribed on the laptop and turned into study notes (summary, key points, to-dos) automatically.",
      {"title": S, "course": {"type": "string", "description": "course or module name, if known"}})
def start_recording(ctx: ToolContext, title: str = "", course: str = "") -> dict:
    return lectures.start(ctx.store, ctx.bus, title, course)


@tool("stop_recording", "Stop the lecture/meeting recording that is running and start transcribing it.")
def stop_recording(ctx: ToolContext) -> dict:
    return lectures.stop(ctx.store, ctx.bus)


@tool("list_lectures", "Recorded lectures and meetings with their status (recording, transcribing, ready...) "
      "and a preview of each summary.")
def list_lectures(ctx: ToolContext) -> dict:
    return {"now": lectures.recording_status(ctx.store), "lectures": ctx.store.list_lectures(20)}


@tool("read_lecture", "Read a recorded lecture's notes and transcript. Pass `query` to get only the transcript "
      "lines that mention it (e.g. 'exam', 'NPV').", {"lecture_id": I, "query": S}, ["lecture_id"])
def read_lecture(ctx: ToolContext, lecture_id: int, query: str = "") -> dict:
    lec = ctx.store.get_lecture(lecture_id)
    if not lec:
        return {"error": f"No lecture #{lecture_id}"}
    transcript = lec["transcript"] or ""
    if query:
        words = [w for w in re.split(r"\W+", query.lower()) if len(w) > 2] or [query.lower()]
        lines = [ln for ln in transcript.splitlines() if any(w in ln.lower() for w in words)]
        transcript = "\n".join(lines[:80]) or "(no lines mention that)"
    return {"id": lec["id"], "title": lec["title"], "course": lec["course"], "status": lec["status"],
            "minutes": round((lec["duration_s"] or 0) / 60), "notes": lec["summary"],
            "transcript": transcript[:60_000]}


@tool("summarize_lecture", "Write (or rewrite) the study notes for a transcribed lecture, e.g. after JARVIS was "
      "paused while it was transcribed.", {"lecture_id": I}, ["lecture_id"])
def summarize_lecture(ctx: ToolContext, lecture_id: int) -> dict:
    lec = ctx.store.get_lecture(lecture_id)
    if not lec:
        return {"error": f"No lecture #{lecture_id}"}
    if not lec["transcript"]:
        return {"error": f"Lecture #{lecture_id} has no transcript yet (status: {lec['status']})."}
    import threading
    threading.Thread(target=lectures.summarise, args=(ctx.store, ctx.bus, lecture_id), daemon=True).start()
    return {"started": True, "note": "ATHENA is writing the notes; they arrive on Telegram and in Notes."}


# ------------------------------------------------------------------ events business (PEPPER)
GIG_STATUS = {"type": "string", "enum": ["enquiry", "quoted", "confirmed", "done", "lost"]}
GIG_PROPS = {"client": S, "contact": {"type": "string", "description": "phone, e-mail or Instagram"},
             "event_type": {"type": "string", "description": "wedding, engagement, birthday, corporate, ..."},
             "event_date": {"type": "string", "description": "YYYY-MM-DD"}, "venue": S, "guests": I,
             "budget": S, "status": GIG_STATUS, "next_step": S, "notes": S}


@tool("add_gig", "Log a client enquiry or booked event for the owner's events business. Always set a next_step.",
      GIG_PROPS, ["client"])
def add_gig(ctx: ToolContext, client: str, **fields) -> dict:
    gid = ctx.store.add_gig(client, **fields)
    ctx.bus.publish({"type": "data", "what": "gigs"})
    return {"gig_id": gid}


@tool("update_gig", "Update a client/event in the business pipeline (status, date, next step, deposit paid...).",
      {"gig_id": I, **GIG_PROPS, "quote_total": {"type": "number"}, "deposit_paid": {"type": "boolean"}}, ["gig_id"])
def update_gig(ctx: ToolContext, gig_id: int, **fields) -> dict:
    if "deposit_paid" in fields:
        fields["deposit_paid"] = int(bool(fields["deposit_paid"]))
    ok = ctx.store.update_gig(gig_id, **fields)
    ctx.bus.publish({"type": "data", "what": "gigs"})
    return {"updated": ok}


@tool("list_gigs", "The business pipeline. status: active (enquiry+quoted+confirmed, default) | enquiry | quoted | "
      "confirmed | done | lost | all.", {"status": S})
def list_gigs(ctx: ToolContext, status: str = "active") -> list:
    return ctx.store.list_gigs(None if status == "all" else status)


def business_details() -> dict:
    """'Key: value' lines from business.md (Business name, Phone, Email, Instagram, Website, UEN, Address, Payment)."""
    path = ROOT / "business.md"
    out: dict = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            m = re.match(r"^\s*[-*]?\s*(Business name|Phone|Email|Instagram|Website|UEN|Address|Payment|Currency)\s*:\s*(.+)$",
                         line, re.I)
            if m and m.group(2).strip():
                out[m.group(1).lower()] = m.group(2).strip()
    return out


def _money(v: float, cur: str) -> str:
    return f"-{cur}{-v:,.2f}" if v < 0 else f"{cur}{v:,.2f}"


def _nice_date(value: str | None) -> str:
    try:
        return date.fromisoformat((value or "")[:10]).strftime("%a %d %b %Y")
    except ValueError:
        return value or ""


@tool("make_quote", "Make a professional PDF quotation for a client of the owner's events business, saved on the "
      "laptop (and sent to the owner's phone). items: [{item, qty, unit_price, details}]. Prices come from business.md "
      "- never invent prices; ask the owner if one is missing. Returns the PDF path to attach with send_email "
      "(the owner approves before it goes to the client).",
      {"gig_id": I, "client": S, "event": {"type": "string", "description": "e.g. 'Wedding reception, 14 Feb 2027, "
                                                                            "Grand Ballroom, 300 pax'"},
       "items": {"type": "array", "items": {"type": "object", "properties": {
           "item": S, "qty": {"type": "number"}, "unit_price": {"type": "number"}, "details": S},
           "required": ["item", "unit_price"]}},
       "discount": {"type": "number", "description": "amount off the subtotal"},
       "deposit_pct": {"type": "number", "description": "default 30"}, "valid_days": I,
       "terms": S, "send_to_phone": {"type": "boolean"}},
      ["client", "items"])
def make_quote(ctx: ToolContext, client: str, items: list, gig_id: int | None = None, event: str = "",
               discount: float = 0, deposit_pct: float = 30, valid_days: int = 14, terms: str = "",
               send_to_phone: bool = True) -> dict:
    from . import devices
    from .pdf import MARGIN, PAGE_W, Doc
    biz = business_details()
    cur = biz.get("currency", "$")
    name = biz.get("business name", "Shaabaz Weddings & Events")
    gig = ctx.store.get_gig(gig_id) if gig_id else None
    if gig and not event:
        event = ", ".join(str(x) for x in (gig["event_type"], _nice_date(gig["event_date"]), gig["venue"],
                                           f"{gig['guests']} pax" if gig["guests"] else "") if x)
    rows, subtotal = [], 0.0
    for it in items:
        qty = float(it.get("qty") or 1)
        price = float(it["unit_price"])
        subtotal += qty * price
        rows.append((str(it["item"]), str(it.get("details") or ""), qty, price, qty * price))
    total = max(0.0, subtotal - float(discount or 0))
    deposit = round(total * float(deposit_pct) / 100, 2)
    today = ctx.now().date()
    number = f"Q{today:%y%m%d}-{gig_id:03d}" if gig_id else f"Q{ctx.now():%y%m%d-%H%M}"

    accent, grey = (0.55, 0.38, 0.12), (0.4, 0.4, 0.4)
    d = Doc()
    right = PAGE_W - MARGIN
    d.rect(0, 842 - 8, PAGE_W, 8, accent)
    d.y -= 16
    d.text(MARGIN, d.y, name, 20, True, accent)
    d.text(right, d.y, "QUOTATION", 16, True, (0.2, 0.2, 0.2), "right")
    d.y -= 16
    contact = "  |  ".join(biz[k] for k in ("phone", "email", "instagram", "website") if k in biz)
    if contact:
        d.text(MARGIN, d.y, contact, 9, color=grey)
    d.text(right, d.y, f"No. {number}", 9, color=grey, align="right")
    d.y -= 12
    if "uen" in biz:
        d.text(MARGIN, d.y, f"UEN {biz['uen']}", 9, color=grey)
    d.text(right, d.y, f"Date: {today:%d %b %Y}   Valid until: {today + timedelta(days=valid_days):%d %b %Y}", 9,
           color=grey, align="right")
    d.y -= 26
    d.text(MARGIN, d.y, "PREPARED FOR", 8, True, grey)
    d.y -= 14
    d.text(MARGIN, d.y, client, 12, True)
    if event:
        d.paragraph(event, 10, color=(0.25, 0.25, 0.25))
    d.y -= 22
    cols = (MARGIN, 330, 400, right)   # item | qty | unit | amount (right edges for numbers)
    d.rect(MARGIN, d.y - 5, right - MARGIN, 18, (0.95, 0.92, 0.87))
    d.text(cols[0] + 6, d.y, "ITEM", 8, True, grey)
    d.text(cols[1] + 20, d.y, "QTY", 8, True, grey, "right")
    d.text(cols[2] + 70, d.y, "UNIT PRICE", 8, True, grey, "right")
    d.text(cols[3] - 6, d.y, "AMOUNT", 8, True, grey, "right")
    d.y -= 10
    for item, details, qty, price, amount in rows:
        d.need(40)
        d.y -= 16
        d.text(cols[0] + 6, d.y, item, 10, True)
        d.text(cols[1] + 20, d.y, f"{qty:g}", 10, align="right")
        d.text(cols[2] + 70, d.y, _money(price, cur), 10, align="right")
        d.text(cols[3] - 6, d.y, _money(amount, cur), 10, align="right")
        if details:
            for ln in d.wrap(details, 260, 8.5):
                d.y -= 11
                d.text(cols[0] + 6, d.y, ln, 8.5, color=grey)
        d.y -= 6
        d.line(MARGIN, d.y, right, d.y)
    d.need(90)
    d.y -= 18
    for label, value, bold in (("Subtotal", subtotal, False), *((("Discount", -float(discount), False),) if discount else ()),
                               ("Total", total, True), (f"Deposit to confirm ({deposit_pct:g}%)", deposit, False)):
        d.text(cols[2] + 70, d.y, label, 11 if bold else 10, bold, align="right")
        d.text(cols[3] - 6, d.y, _money(value, cur), 11 if bold else 10, bold, accent if bold else (0, 0, 0), "right")
        d.y -= 16
    d.y -= 10
    terms = terms or (f"A {deposit_pct:g}% deposit secures the date; the balance is due 7 days before the event. "
                      "Prices are valid until the date above. Final guest numbers are confirmed 14 days before the event.")
    d.text(MARGIN, d.y, "TERMS", 8, True, grey)
    d.paragraph(terms, 9, color=(0.25, 0.25, 0.25))
    if "payment" in biz:
        d.y -= 6
        d.text(MARGIN, d.y, "PAYMENT", 8, True, grey)
        d.paragraph(biz["payment"], 9, color=(0.25, 0.25, 0.25))
    d.y -= 20
    d.paragraph(f"Thank you for considering {name}. We'd love to make your day unforgettable.", 10, color=accent)

    folder = devices.WORKSPACE / "Business" / "Quotes"
    safe = re.sub(r"[^A-Za-z0-9]+", "-", client).strip("-")[:30] or "client"
    path = d.save(folder / f"{number}-{safe}.pdf")
    if gig:
        ctx.store.update_gig(gig["id"], quote_total=total, status="quoted" if gig["status"] == "enquiry" else gig["status"],
                             next_step=f"Follow up on quote {number}")
    sent = ""
    if send_to_phone:
        from . import telegram as tg
        if tg.ready():
            try:
                tg.send_file(str(path), caption=f"Quote {number} for {client}: {_money(total, cur)}")
                sent = "sent to your phone"
            except Exception as exc:  # noqa: BLE001
                sent = f"couldn't send to phone: {exc}"
    ctx.bus.publish({"type": "data", "what": "gigs"})
    return {"quote": number, "pdf": str(path), "total": total, "deposit": deposit, "phone": sent or "not sent",
            "next": "To e-mail it to the client, call send_email with attachment = the pdf path."}


@tool("gig_checklist", "Create the planning checklist for a confirmed event as dated tasks counting back from the "
      "event date. steps: [{title, days_before}], e.g. {title: 'Confirm florist', days_before: 30}.",
      {"gig_id": I, "steps": {"type": "array", "items": {"type": "object", "properties": {
          "title": S, "days_before": I}, "required": ["title", "days_before"]}}}, ["gig_id", "steps"])
def gig_checklist(ctx: ToolContext, gig_id: int, steps: list) -> dict:
    gig = ctx.store.get_gig(gig_id)
    if not gig:
        return {"error": f"No gig #{gig_id}"}
    if not gig["event_date"]:
        return {"error": "Set the event date first (update_gig)."}
    day = date.fromisoformat(gig["event_date"][:10])
    made = []
    for st in steps:
        due = max(ctx.now().date(), day - timedelta(days=int(st["days_before"])))
        tid = ctx.store.add_task(f"[{gig['client']}] {st['title']}", "career", 2, due.isoformat(),
                                 f"Gig #{gig_id}: {gig['event_type']} on {gig['event_date']}", "")
        made.append(tid)
    ctx.bus.publish({"type": "data", "what": "tasks"})
    return {"tasks_created": len(made), "task_ids": made}


# ------------------------------------------------------------------ weather (free, no key: open-meteo.com)
WEATHER_CODES = {0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "cloudy", 45: "foggy", 48: "foggy",
                 51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 61: "light rain", 63: "rain",
                 65: "heavy rain", 80: "showers", 81: "heavy showers", 82: "violent showers",
                 95: "thunderstorms", 96: "thunderstorms with hail", 99: "thunderstorms with hail"}


@tool("weather", "Today's and tomorrow's weather where the owner lives (rain chance by time of day, temperature). "
      "Use it in briefings and before outdoor plans or events.")
def weather(ctx: ToolContext) -> dict:
    import json as _json
    import os
    import urllib.request
    lat, _, lon = os.environ.get("JARVIS_WEATHER_LATLON", "1.3521,103.8198").partition(",")   # default: Singapore
    url = ("https://api.open-meteo.com/v1/forecast?latitude=" + lat.strip() + "&longitude=" + lon.strip() +
           "&hourly=precipitation_probability,temperature_2m,weather_code&daily=temperature_2m_max,"
           "temperature_2m_min,precipitation_probability_max,weather_code&forecast_days=2&timezone=auto")
    try:
        with urllib.request.urlopen(url, timeout=15) as r:
            d = _json.load(r)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"weather service unreachable: {exc}"}
    days = []
    for i, day in enumerate(d["daily"]["time"]):
        hours = [(t[11:16], p, c) for t, p, c in zip(d["hourly"]["time"], d["hourly"]["precipitation_probability"],
                                                     d["hourly"]["weather_code"]) if t.startswith(day)]
        wet = [f"{h} {p}%" for h, p, _c in hours if p is not None and p >= 40]
        days.append({"date": day, "sky": WEATHER_CODES.get(d["daily"]["weather_code"][i], "mixed"),
                     "min_c": d["daily"]["temperature_2m_min"][i], "max_c": d["daily"]["temperature_2m_max"][i],
                     "rain_chance_max": d["daily"]["precipitation_probability_max"][i],
                     "rainy_hours": wet[:8] or "none likely"})
    return {"today": days[0], "tomorrow": days[1] if len(days) > 1 else None}
