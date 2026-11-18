"""HTTP API + live dashboard for JARVIS OS."""
from __future__ import annotations

import asyncio
import json
import queue
from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .agents import AGENTS, roster
from .bus import Bus
from .config import ROOT, settings
from .engine import Engine
from .notify import channels
from .scheduler import Scheduler
from .store import Store

store = Store(settings.db_path)
bus = Bus(store)
engine = Engine(store, bus, settings)
scheduler = Scheduler(engine)

app = FastAPI(title="JARVIS OS")


@app.on_event("startup")
def _startup() -> None:
    # Don't fire the interval watch the moment the server boots.
    if store.get("job:deadline_watch:last") is None:
        store.set("job:deadline_watch:last", datetime.now(settings.tz).isoformat())
    if settings.schedule_enabled:
        scheduler.start()
    bus.log("JARVIS", "JARVIS OS online.", "system")


class Command(BaseModel):
    text: str
    agent: str = "JARVIS"


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


@app.get("/")
def index():
    return RedirectResponse("/command-centre.html?autostart=true")


@app.get("/api/agents")
def agents():
    return {"agents": roster(), "llm": settings.has_llm, "model": settings.model,
            "owner": settings.owner_name, "channels": channels()}


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
        ("SENTINEL", f"SENTINEL active. {plural(len(overdue), 'overdue item')}, {len(due_today)} due today. "
                     f"{plural(len(queue_), 'task')} queued for the night shift. You are protected, {owner}."),
    ]
    return {"lines": [{"agent": a, "text": t} for a, t in lines]}


@app.post("/api/command")
async def command(cmd: Command):
    agent = cmd.agent.upper()
    if agent not in AGENTS:
        raise HTTPException(404, f"Unknown agent {agent}")
    bus.log("YOU", cmd.text, "command")
    reply = await asyncio.to_thread(engine.run, agent, cmd.text, chat=True)
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
