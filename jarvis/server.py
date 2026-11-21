"""HTTP API + live dashboard for JARVIS OS."""
from __future__ import annotations

import asyncio
import json
import queue
import re
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .agents import AGENTS, roster
from .bus import Bus
from .config import ROOT, settings
from .engine import Engine
from . import channels as ch
from . import devices
from . import telegram as tg
from . import voice
from .notify import channels
from .scheduler import Scheduler
from .store import Store

store = Store(settings.db_path)
bus = Bus(store)
engine = Engine(store, bus, settings)
scheduler = Scheduler(engine)

@asynccontextmanager
async def lifespan(_app):
    # Don't fire the interval jobs the moment the server boots.
    for job in ("deadline_watch", "inbox_sweep"):
        if store.get(f"job:{job}:last") is None:
            store.set(f"job:{job}:last", datetime.now(settings.tz).isoformat())
    if settings.schedule_enabled:
        scheduler.start()
    tg.attach(store)
    from . import stt
    stt.warm_up()
    bot = tg.Bot(on_text=lambda text, voice=False: handle_owner_message(text, "Telegram", voice),
                 on_decision=lambda msg_id, yes: approve_message(msg_id) if yes else reject_message(msg_id),
                 log=lambda m: bus.log("JARVIS", m, "system"))
    bot.start()
    bus.log("JARVIS", "JARVIS OS online.", "system")
    yield
    bot.stop()
    scheduler.stop()


app = FastAPI(title="JARVIS OS", lifespan=lifespan)


class Command(BaseModel):
    text: str
    agent: str = "JARVIS"
    voice: bool = False   # spoken command: fast path, short spoken answer
    rid: str = ""         # request id, so the dashboard can match streamed text to its request


class TaskIn(BaseModel):
    title: str
    area: str = "personal"
    priority: int = 3
    due: str | None = None
    notes: str = ""
    assignee: str | None = None


class TaskPatch(BaseModel):
    status: str | None = None
    title: str | None = None
    priority: int | None = None
    due: str | None = None
    assignee: str | None = None


class Approval(BaseModel):
    body: str | None = None
    subject: str | None = None


class Incoming(BaseModel):
    text: str


class Speech(BaseModel):
    agent: str
    text: str


@app.get("/")
def index():
    return RedirectResponse("/command-centre.html?autostart=true")


@app.get("/api/agents")
def agents():
    return {"agents": roster(), "llm": settings.has_llm, "model": settings.model,
            "owner": settings.owner_name, "channels": channels(), "autonomy": settings.autonomy}


@app.get("/api/voices")
def voices():
    return {"provider": "elevenlabs" if voice.enabled() else "browser", "voices": voice.voices(),
            "wake_words": [w.strip().lower() for w in settings.wake_words.split(",") if w.strip()]}


@app.post("/api/tts")
async def tts(sp: Speech):
    if not voice.enabled():
        raise HTTPException(404, "No ElevenLabs key - the browser voice is used instead")
    try:
        path = await asyncio.to_thread(voice.synthesize, sp.agent, sp.text)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(502, f"Voice service error: {exc}") from exc
    return FileResponse(path, media_type="audio/mpeg")


@app.get("/api/connections")
def connections():
    tg.attach(store)
    return {"telegram": {"ready": tg.ready(), "enabled": tg.enabled(), "pair_code": tg.pair_code()},
            "whatsapp": ch.whatsapp_status(), "email_send": ch.email_ready(), "email_read": ch.email_read_ready(),
            "phone": devices.phone_ready(), "autonomy": settings.autonomy}


@app.get("/api/state")
def state():
    now = datetime.now(settings.tz)
    today = now.date().isoformat()
    week = (now.date() + timedelta(days=7)).isoformat()
    return {
        "now": now.isoformat(timespec="minutes"),
        "tasks": store.list_tasks("open", limit=100),
        "done_recent": store.list_tasks("done", limit=10),
        "events": store.list_events(today, week),
        "goals": store.list_goals(),
        "applications": store.list_applications(),
        "reports": store.list_reports(15),
        "activity": store.recent_activity(60),
        "jobs": scheduler.job_table(),
        "outbox_pending": store.list_outbox("pending", 50),
        "outbox_recent": [m for m in store.list_outbox(None, 30) if m["status"] != "pending"][:15],
        "routines": store.list_routines(),
    }


@app.get("/api/boot")
def boot():
    """Roll-call lines for the boot sequence, built from live data (no LLM needed)."""
    now = datetime.now(settings.tz)
    today = now.date().isoformat()
    open_tasks = store.list_tasks("open", limit=1000)
    overdue = [t for t in open_tasks if t["due"] and t["due"][:10] < today]
    due_today = [t for t in open_tasks if t["due"] and t["due"][:10] == today]
    events = store.list_events(today, (now.date() + timedelta(days=1)).isoformat())
    apps = store.list_applications()
    active_apps = [a for a in apps if a["status"] in ("applied", "interview")]
    academic = [t for t in open_tasks if t["area"] == "academic"]
    queue_ = [t for t in open_tasks if t["assignee"]]
    habits = store.habit_status((now.date() - timedelta(days=6)).isoformat())
    money = store.spending_summary(now.date().replace(day=1).isoformat())
    last_brief = store.list_reports(1, "morning_brief")
    owner = settings.owner_name
    n = len(AGENTS) - 1

    def plural(k, word):
        return f"{k} {word}{'' if k == 1 else 's'}"

    lines = [
        ("JARVIS", "All systems standing by."),
        ("JARVIS", "Agents, assemble. All agents report in."),
        ("JARVIS", f"JARVIS online. Prime orchestrator active. {n} agents standing by. What are your orders, {owner}?"
         if settings.has_llm else
         f"JARVIS online in local mode. Add an API key to bring my reasoning core online, {owner}."),
        ("FRIDAY", "FRIDAY here. " + (f"Latest brief: {last_brief[0]['title']}." if last_brief
                                      else "Daily intelligence brief scheduled for "
                                           f"{settings.morning_brief_at}.") + " All systems active."),
        ("ORACLE", "ORACLE active. Research and web intelligence online."),
        ("ATHENA", f"ATHENA online. {plural(len(academic), 'academic task')} on the board."),
        ("ZEUS", f"ZEUS online. {plural(len(apps), 'application')} tracked, {len(active_apps)} in play."),
        ("HERALD", f"HERALD reporting in. {plural(len(events), 'event')} on today's calendar."),
        ("STEVE", f"STEVE here. {plural(len(habits), 'habit')} tracked this week. Ready to ship on your command."),
        ("VERONICA", f"VERONICA online. Net this month: {money['net']:+.2f}."),
        ("BANNER", "BANNER standing by. Wellbeing diagnostics monitored."),
        ("EDITH", "EDITH online. Laptop" + (" and phone" if devices.phone_ready() else "")
                  + f" linked. {plural(len(store.list_routines(True)), 'custom routine')} running."),
        ("SENTINEL", f"SENTINEL active. {plural(len(overdue), 'overdue item')}, {len(due_today)} due today. "
                     f"{plural(len(queue_), 'task')} queued for the night shift. You are protected, {owner}."),
    ]
    pending = store.list_outbox("pending", 100)
    if pending:
        lines.insert(-1, ("HERALD", f"{plural(len(pending), 'message')} waiting for your approval in the outbox."))
    return {"lines": [{"agent": a, "text": t} for a, t in lines]}


@app.post("/api/command")
async def command(cmd: Command):
    agent = cmd.agent.upper()
    if agent not in AGENTS:
        raise HTTPException(404, f"Unknown agent {agent}")
    bus.log("YOU", ("🎙 " if cmd.voice else "") + cmd.text, "command")

    def stream_out(text: str) -> None:
        bus.publish({"type": "delta", "rid": cmd.rid, "agent": agent, "text": text})

    reply = await asyncio.to_thread(engine.run, agent, cmd.text, chat=True, on_text=stream_out, voice=cmd.voice)
    bus.publish({"type": "delta_end", "rid": cmd.rid, "agent": agent})
    bus.log(agent, reply, "reply")
    return {"agent": agent, "reply": reply}


@app.post("/api/reset")
def reset(agent: str | None = None):
    engine.reset_chat(agent)
    return {"ok": True}


@app.post("/api/jobs/{name}/run")
def run_job(name: str):
    if name not in {j.name for j in scheduler.jobs}:
        raise HTTPException(404, "Unknown job")
    scheduler.run_job_async(name)
    return {"started": name}


# ---------------------------------------------------------------- outbox (approvals)
def approve_message(msg_id: int, body: str | None = None, subject: str | None = None) -> str:
    msg = store.get_message(msg_id)
    if not msg or msg["status"] not in ("pending", "failed"):
        return f"#{msg_id} is not waiting for approval"
    store.set_message(msg_id, status="approved", body=body, subject=subject, error="")
    msg = store.get_message(msg_id)
    if msg["send_at"] and msg["send_at"] > datetime.now(settings.tz).isoformat(timespec="seconds"):
        bus.publish({"type": "data", "what": "outbox"})
        return f"#{msg_id} approved, will send at {msg['send_at'][11:16]}"
    ok = ch.deliver(store, bus, msg)
    msg = store.get_message(msg_id)
    if msg["channel"] == "computer":
        return f"#{msg_id} ran:\n{msg['result'][:1500]}" if ok else f"#{msg_id} failed: {msg['error']}"
    return f"#{msg_id} sent to {msg['recipient_name'] or msg['recipient']}" if ok else f"#{msg_id} failed: {msg['error']}"


def reject_message(msg_id: int) -> str:
    msg = store.get_message(msg_id)
    if not msg or msg["status"] != "pending":
        return f"#{msg_id} is not waiting for approval"
    store.set_message(msg_id, status="rejected")
    bus.log(msg["agent"], f"✉ #{msg_id} cancelled by you", "job")
    bus.publish({"type": "data", "what": "outbox"})
    return f"#{msg_id} cancelled"


@app.post("/api/outbox/{msg_id}/approve")
def approve(msg_id: int, a: Approval | None = None):
    return {"result": approve_message(msg_id, a.body if a else None, a.subject if a else None)}


@app.post("/api/outbox/{msg_id}/reject")
def reject(msg_id: int):
    return {"result": reject_message(msg_id)}


@app.post("/api/routines/{routine_id}/toggle")
def toggle_routine(routine_id: int):
    r = next((x for x in store.list_routines() if x["id"] == routine_id), None)
    if not r:
        raise HTTPException(404)
    store.update_routine(routine_id, enabled=0 if r["enabled"] else 1)
    return {"enabled": not r["enabled"]}


@app.delete("/api/routines/{routine_id}")
def remove_routine(routine_id: int):
    return {"deleted": store.delete_routine(routine_id)}


# ---------------------------------------------------------------- WhatsApp remote control
APPROVAL_RE = re.compile(r"^\s*(yes|y|approve|ok|send|no|n|reject|cancel)\s+#?(\d+|all)\s*$", re.I)


def handle_owner_message(text: str, via: str = "WhatsApp", voice: bool = False) -> str:
    """An order the owner sent from their phone (Telegram bot chat or WhatsApp 'Message yourself' chat)."""
    m = APPROVAL_RE.match(text)
    if m:
        yes = m.group(1).lower() in ("yes", "y", "approve", "ok", "send")
        ids = [x["id"] for x in store.list_outbox("pending", 100)] if m.group(2).lower() == "all" else [int(m.group(2))]
        if not ids:
            return "Nothing is waiting for approval."
        return "\n".join(approve_message(i) if yes else reject_message(i) for i in ids)
    if text.strip().lower() in ("pending", "outbox"):
        items = store.list_outbox("pending", 20)
        return "\n\n".join(f"#{x['id']} {x['channel']} → {x['recipient_name'] or x['recipient']}: {x['body'][:200]}"
                             for x in items) or "Nothing is waiting for approval."
    target = "JARVIS"
    first = text.strip().split(maxsplit=1)
    if first and first[0].strip(",:").upper() in AGENTS and len(first) > 1:
        target, text = first[0].strip(",:").upper(), first[1]
    bus.log("YOU", f"({via}) {text}", "command")
    reply = engine.run(target, text + f"\n\n(Sent from the owner's phone via {via} - keep the reply short.)",
                       chat=True, voice=voice)
    bus.log(target, reply, "reply")
    return f"{target}: {reply}" if target != "JARVIS" else reply


@app.post("/api/whatsapp/incoming")
def whatsapp_incoming(msg: Incoming, x_jarvis_token: str = Header(default="")):
    if not settings.bridge_token or x_jarvis_token != settings.bridge_token:
        raise HTTPException(403, "bad token")

    def work():
        if not ch.whatsapp_ready():
            return
        try:
            answer = handle_owner_message(msg.text, "WhatsApp")
        except Exception as exc:  # noqa: BLE001
            answer = f"Error: {exc}"
        try:
            ch.send_whatsapp(settings.owner_whatsapp, f"🤖 {answer}"[:60000])
        except Exception as exc:  # noqa: BLE001
            bus.log("JARVIS", f"Could not reply on WhatsApp: {exc}", "error")

    threading.Thread(target=work, daemon=True).start()
    return {"ok": True}


@app.get("/api/reports/{report_id}")
def report(report_id: int):
    r = store.get_report(report_id)
    if not r:
        raise HTTPException(404)
    return r


@app.post("/api/tasks")
def create_task(t: TaskIn):
    tid = store.add_task(t.title, t.area, t.priority, t.due, t.notes, t.assignee)
    bus.publish({"type": "data", "what": "tasks"})
    return {"id": tid}


@app.patch("/api/tasks/{task_id}")
def patch_task(task_id: int, p: TaskPatch):
    ok = store.update_task(task_id, **p.model_dump(exclude_none=True))
    bus.publish({"type": "data", "what": "tasks"})
    return {"updated": ok}


@app.get("/api/stream")
async def stream():
    q = bus.subscribe()

    async def gen():
        try:
            yield "retry: 3000\n\n"
            while True:
                try:
                    event = await asyncio.to_thread(q.get, True, 15)
                    yield f"data: {json.dumps(event, default=str)}\n\n"
                except queue.Empty:
                    yield ": keep-alive\n\n"
        finally:
            bus.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream")


app.mount("/", StaticFiles(directory=ROOT / "web"), name="web")
