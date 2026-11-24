"""Tools the agents can call. Each tool = JSON schema for Claude + a Python function."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable

from .notify import notify_owner

AREAS = ["personal", "career", "academic", "health", "finance"]


@dataclass
class ToolContext:
    store: Any
    bus: Any
    settings: Any
    engine: Any
    agent: str
    depth: int = 0
    approved: bool = False   # running a plan the owner already said yes to

    def now(self) -> datetime:
        return datetime.now(self.settings.tz)

    def today(self) -> str:
        return self.now().date().isoformat()


@dataclass
class Tool:
    name: str
    description: str
    properties: dict[str, Any]
    required: list[str]
    fn: Callable[..., Any]

    def schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {"type": "object", "properties": self.properties, "required": self.required},
        }


REGISTRY: dict[str, Tool] = {}


def tool(name: str, description: str, properties: dict | None = None, required: list[str] | None = None):
    def wrap(fn):
        REGISTRY[name] = Tool(name, description, properties or {}, required or [], fn)
        return fn
    return wrap


S = {"type": "string"}
I = {"type": "integer"}
AREA = {"type": "string", "enum": AREAS}


def local_iso(ctx: ToolContext, value: str | None) -> str | None:
    """Store every date-time in the owner's own timezone (agents sometimes write UTC 'Z' times)."""
    if not value or len(value) <= 10:
        return value
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return value
    if dt.tzinfo is not None:
        dt = dt.astimezone(ctx.settings.tz).replace(tzinfo=None)
    return dt.isoformat(timespec="minutes")


def _days_ago(ctx: ToolContext, days: int) -> str:
    return (ctx.now().date() - timedelta(days=days)).isoformat()


# ------------------------------------------------------------------ time & overview
@tool("get_datetime", "Current local date, time and weekday for the owner.")
def get_datetime(ctx: ToolContext) -> dict:
    n = ctx.now()
    return {"iso": n.isoformat(timespec="minutes"), "weekday": n.strftime("%A"), "timezone": ctx.settings.timezone}


@tool("status_snapshot", "Overview of everything: open tasks (overdue, due today), today's and tomorrow's events, "
      "active goals, habits this week, career pipeline, spending this month, recent reports.")
def status_snapshot(ctx: ToolContext) -> dict:
    s, today = ctx.store, ctx.today()
    tomorrow = (ctx.now().date() + timedelta(days=1)).isoformat()
    day_after = (ctx.now().date() + timedelta(days=2)).isoformat()
    open_tasks = s.list_tasks("open", limit=200)
    return {
        "now": get_datetime(ctx),
        "overdue": [t for t in open_tasks if t["due"] and t["due"][:10] < today],
        "due_today": [t for t in open_tasks if t["due"] and t["due"][:10] == today],
        "open_task_count": len(open_tasks),
        "top_open_tasks": open_tasks[:15],
        "agent_queue": [t for t in open_tasks if t["assignee"]],
        "events_today_tomorrow": s.list_events(today, day_after),
        "events_next_14_days": [{k: e[k] for k in ("id", "title", "start", "end", "area")}
                                for e in s.list_events(today, (ctx.now().date() + timedelta(days=14)).isoformat())],
        "tomorrow": tomorrow,
        "goals": s.list_goals(),
        "habits_last_7_days": s.habit_status(_days_ago(ctx, 6)),
        "applications": s.list_applications(),
        "business_pipeline": [{k: g[k] for k in ("id", "client", "event_type", "event_date", "status", "next_step")}
                              for g in s.list_gigs("active", 15)],
        "recent_lectures": [{k: x[k] for k in ("id", "title", "status")} for x in s.list_lectures(3)],
        "exams_upcoming": [{"course": e["course"], "at": e["exam_at"]} for e in
                           s.query("SELECT course, exam_at FROM exams WHERE status='upcoming' AND exam_at >= ? "
                                   "ORDER BY exam_at LIMIT 6", (today,))],
        "money_this_month": s.spending_summary(ctx.now().date().replace(day=1).isoformat()),
        "completed_last_24h": [t for t in s.list_tasks("done", limit=50) if t["updated"] >= _days_ago(ctx, 1)],
        "recent_reports": [{k: r[k] for k in ("id", "kind", "agent", "title", "created")} for r in s.list_reports(5)],
        # already waiting for the owner - don't propose the same thing again
        "open_proposals": [{k: p[k] for k in ("id", "agent", "title")} for p in s.list_proposals("open", 30)],
        "emails_awaiting_reply": [{k: g[k] for k in ("id", "sender_name", "subject")}
                                  for g in s.list_suggestions("open", 20)],
        "messages_awaiting_approval": [{k: m[k] for k in ("id", "channel", "recipient_name", "subject")}
                                       for m in s.list_outbox("pending", 20)],
    }


# ------------------------------------------------------------------ tasks
@tool("add_task", "Create a task. Set 'assignee' to an agent name (e.g. ORACLE, ATHENA) if that agent should "
      "do the work autonomously during the night shift; leave empty for tasks the owner must do.",
      {"title": S, "area": AREA, "priority": {"type": "integer", "minimum": 1, "maximum": 5,
                                              "description": "1 = most important"},
       "due": {"type": "string", "description": "ISO date (YYYY-MM-DD) or datetime"}, "notes": S,
       "assignee": {"type": "string", "description": "Agent name for autonomous work"}},
      ["title"])
def add_task(ctx: ToolContext, title: str, area: str = "personal", priority: int = 3, due: str | None = None,
             notes: str = "", assignee: str | None = None) -> dict:
    task_id = ctx.store.add_task(title, area, priority, local_iso(ctx, due), notes, assignee or None)
    ctx.bus.publish({"type": "data", "what": "tasks"})
    return {"created_task_id": task_id}


@tool("list_tasks", "List tasks. status: open (default) | todo | doing | done | all.",
      {"status": S, "area": AREA, "assignee": S})
def list_tasks(ctx: ToolContext, status: str = "open", area: str | None = None, assignee: str | None = None) -> list:
    return ctx.store.list_tasks(status, area, assignee)


@tool("update_task", "Update fields of a task (title, status, priority, due, notes, assignee, result).",
      {"task_id": I, "title": S, "status": {"type": "string", "enum": ["todo", "doing", "done", "cancelled"]},
       "priority": I, "due": S, "notes": S, "assignee": S, "result": S}, ["task_id"])
def update_task(ctx: ToolContext, task_id: int, **fields) -> dict:
    before = ctx.store.query("SELECT * FROM tasks WHERE id = ?", (task_id,))
    ok = ctx.store.update_task(task_id, **fields)
    if ok and fields.get("status") == "done" and before and before[0]["status"] != "done" and (
            before[0]["priority"] <= 2 or before[0]["area"] == "academic"):
        from .life import celebrate
        celebrate(ctx.bus, ctx.agent, before[0]["title"])
    ctx.bus.publish({"type": "data", "what": "tasks"})
    return {"updated": ok}


# ------------------------------------------------------------------ calendar
@tool("add_event", "Add a calendar event / class / meeting / deadline block.",
      {"title": S, "start": {"type": "string", "description": "ISO datetime"}, "end": S, "location": S,
       "area": AREA, "notes": S}, ["title", "start"])
def add_event(ctx: ToolContext, title: str, start: str, end: str | None = None, location: str = "",
              area: str = "personal", notes: str = "") -> dict:
    from . import gcal
    eid = ctx.store.add_event(title, local_iso(ctx, start), local_iso(ctx, end), location, area, notes)
    out: dict = {"created_event_id": eid}
    if gcal.ready():
        try:
            gcal.push_event(ctx.store, ctx.store.get_event(eid))
            out["google_calendar"] = "added"
        except Exception as exc:  # noqa: BLE001 - it's still in JARVIS's calendar; the next sync retries
            out["google_calendar"] = f"not added yet ({exc}); will retry on the next sync"
    ctx.bus.publish({"type": "data", "what": "events"})
    return out


@tool("list_events", "List events between two ISO dates (end exclusive). Defaults to the next 7 days.",
      {"start": S, "end": S})
def list_events(ctx: ToolContext, start: str | None = None, end: str | None = None) -> list:
    from . import gcal
    if gcal.ready():
        gcal.sync()   # no-op if synced in the last few minutes
    start = start or ctx.today()
    end = end or (ctx.now().date() + timedelta(days=7)).isoformat()
    return ctx.store.list_events(start, end)


@tool("delete_event", "Delete a calendar event by id (also from Google Calendar if it's synced).",
      {"event_id": I}, ["event_id"])
def delete_event(ctx: ToolContext, event_id: int) -> dict:
    from . import gcal
    ev = ctx.store.get_event(event_id)
    out: dict = {"deleted": ctx.store.delete_event(event_id)}
    if ev and ev.get("gid") and gcal.ready():
        try:
            gcal.delete_event(ev["gid"])
        except Exception as exc:  # noqa: BLE001
            out["google_calendar"] = f"couldn't delete it in Google: {exc}"
    ctx.bus.publish({"type": "data", "what": "events"})
    return out


@tool("sync_calendar", "Sync with the owner's Google Calendar now (pull their events, push JARVIS's new ones).")
def sync_calendar(ctx: ToolContext) -> dict:
    from . import gcal
    if not gcal.ready():
        return {"error": "Google Calendar isn't connected. The owner sets it up once: dashboard → Autopilot → "
                         "Google Calendar → Set up."}
    out = gcal.sync(force=True)
    ctx.bus.publish({"type": "data", "what": "events"})
    return out


# ------------------------------------------------------------------ notes & memory
@tool("save_note", "Save a note / document / draft / study material / research output.",
      {"title": S, "body": S, "tags": {"type": "string", "description": "comma separated"}}, ["title", "body"])
def save_note(ctx: ToolContext, title: str, body: str, tags: str = "") -> dict:
    nid = ctx.store.add_note(title, body, tags, ctx.agent)
    ctx.bus.publish({"type": "data", "what": "notes"})
    return {"note_id": nid}


@tool("search_notes", "Search saved notes by keyword (empty query = most recent).", {"query": S})
def search_notes(ctx: ToolContext, query: str = "") -> list:
    return ctx.store.search_notes(query)


@tool("remember", "Store a long-term fact about the owner (preferences, people, routines, constraints). "
      "Use whenever the owner tells you something worth knowing later.", {"fact": S}, ["fact"])
def remember(ctx: ToolContext, fact: str) -> dict:
    return {"memory_id": ctx.store.remember(fact)}


@tool("recall", "Read the long-term facts stored about the owner.")
def recall(ctx: ToolContext) -> list:
    return ctx.store.memories()


# ------------------------------------------------------------------ goals & habits
@tool("add_goal", "Create a goal (personal, career, academic, health, finance).",
      {"title": S, "area": AREA, "target_date": S, "notes": S}, ["title"])
def add_goal(ctx: ToolContext, title: str, area: str = "personal", target_date: str | None = None,
             notes: str = "") -> dict:
    return {"goal_id": ctx.store.add_goal(title, area, target_date, notes)}


@tool("update_goal", "Update a goal's progress (0-100), notes, target date or status (active|achieved|dropped).",
      {"goal_id": I, "progress": I, "notes": S, "target_date": S, "status": S}, ["goal_id"])
def update_goal(ctx: ToolContext, goal_id: int, **fields) -> dict:
    return {"updated": ctx.store.update_goal(goal_id, **fields)}


@tool("list_goals", "List active goals.")
def list_goals(ctx: ToolContext) -> list:
    return ctx.store.list_goals()


@tool("log_habit", "Mark a habit as done for a day (creates the habit if new). Day defaults to today.",
      {"name": S, "day": S}, ["name"])
def log_habit(ctx: ToolContext, name: str, day: str | None = None) -> dict:
    ctx.store.log_habit(name.strip().lower(), day or ctx.today())
    return {"logged": name, "day": day or ctx.today()}


@tool("habit_report", "Habit completion counts over the last N days (default 7).", {"days": I})
def habit_report(ctx: ToolContext, days: int = 7) -> list:
    return ctx.store.habit_status(_days_ago(ctx, max(days - 1, 0)))


# ------------------------------------------------------------------ career
@tool("add_application", "Track a job / internship / scholarship application.",
      {"company": S, "role": S, "status": {"type": "string",
                                           "enum": ["interested", "applied", "interview", "offer", "rejected"]},
       "link": S, "next_step": S}, ["company", "role"])
def add_application(ctx: ToolContext, company: str, role: str, status: str = "interested", link: str = "",
                    next_step: str = "") -> dict:
    return {"application_id": ctx.store.add_application(company, role, status, link, next_step)}


@tool("update_application", "Update an application's status or next step.",
      {"application_id": I, "status": S, "next_step": S, "link": S}, ["application_id"])
def update_application(ctx: ToolContext, application_id: int, **fields) -> dict:
    return {"updated": ctx.store.update_application(application_id, **fields)}


@tool("list_applications", "List tracked applications, optionally by status.", {"status": S})
def list_applications(ctx: ToolContext, status: str | None = None) -> list:
    return ctx.store.list_applications(status)


# ------------------------------------------------------------------ money
@tool("log_transaction", "Log money spent (negative amount) or received (positive amount).",
      {"amount": {"type": "number"}, "category": S, "note": S, "day": S}, ["amount"])
def log_transaction(ctx: ToolContext, amount: float, category: str = "other", note: str = "",
                    day: str | None = None) -> dict:
    return {"transaction_id": ctx.store.log_transaction(day or ctx.today(), amount, category.lower(), note)}


@tool("spending_summary", "Net money and totals by category over the last N days (default 30).", {"days": I})
def spending_summary(ctx: ToolContext, days: int = 30) -> dict:
    return ctx.store.spending_summary(_days_ago(ctx, days))


# ------------------------------------------------------------------ reports & comms
@tool("publish_report", "Save a finished report to the dashboard and send it to the owner's configured "
      "channels (email / Telegram). Use for briefings, daily/weekly reports and completed research.",
      {"kind": {"type": "string", "description": "morning_brief | evening_report | weekly_review | research | alert | other"},
       "title": S, "body": {"type": "string", "description": "Markdown body"}, "send": {"type": "boolean"},
       "spoken": {"type": "string", "description": "1-3 sentences to SAY OUT LOUD to the owner, in your voice and "
                                                   "personality: the headline and what needs them. No lists, no "
                                                   "Markdown."}},
      ["kind", "title", "body", "spoken"])
def publish_report(ctx: ToolContext, kind: str, title: str, body: str, send: bool = True, spoken: str = "") -> dict:
    from .speech import announce
    rid = ctx.store.save_report(kind, ctx.agent, title, body)
    ctx.bus.publish({"type": "report", "id": rid, "agent": ctx.agent, "title": title, "kind": kind})
    delivery = notify_owner(f"[{ctx.agent}] {title}", body) if send else ["not sent"]
    announce(ctx.bus, ctx.agent, spoken or title, critical=(kind == "alert"))
    return {"report_id": rid, "delivery": delivery}


@tool("delegate", "Hand a sub-task to a specialist agent and get its answer back. Give full context: the agent "
      "does not see this conversation.",
      {"agent": S, "task": S}, ["agent", "task"])
def delegate(ctx: ToolContext, agent: str, task: str) -> str:
    if ctx.depth >= 2:
        return "Delegation depth limit reached - do this yourself."
    return ctx.engine.run(agent.upper(), task, depth=ctx.depth + 1)


def execute(name: str, ctx: ToolContext, args: dict) -> tuple[str, bool]:
    """Run a tool; return (json-ish string, is_error)."""
    t = REGISTRY.get(name)
    if not t:
        return f"Unknown tool {name}", True
    try:
        result = t.fn(ctx, **(args or {}))
        return (result if isinstance(result, str) else json.dumps(result, default=str, ensure_ascii=False)), False
    except TypeError as exc:
        return f"Bad arguments for {name}: {exc}", True
    except Exception as exc:  # noqa: BLE001 - surface to the model so it can recover
        return f"{name} failed: {exc}", True


# Real-world tools (messaging, inboxes, routines, laptop and phone) register themselves on import.
from . import actions as _actions  # noqa: E402,F401
from . import extras as _extras  # noqa: E402,F401  (lecture recorder, business kit)
from . import life as _life  # noqa: E402,F401  (friend layer, study, crew, fitness, focus)
from . import butler as _butler  # noqa: E402,F401  (deep memory, home manager, Stark Daily)
from . import desktop as _desktop  # noqa: E402,F401  (laptop command: windows, media, Office files, screen)
from . import phonelink as _phonelink  # noqa: E402,F401  (phone link: find my phone, silent, clipboard, autopilot)
from . import photosort as _photosort  # noqa: E402,F401  (photo sorter: albums, find_photo)
from . import explore as _explore  # noqa: E402,F401  (places explored, route planning)
from . import awareness as _awareness  # noqa: E402,F401  (live situation, time at places)
from . import navigate as _navigate  # noqa: E402,F401  (navigation inside JARVIS)
from . import predict as _predict  # noqa: E402,F401  (learned routines, nudges before you ask)
from . import studio as _studio  # noqa: E402,F401  (floor plans, mood boards, portfolio, backups)
