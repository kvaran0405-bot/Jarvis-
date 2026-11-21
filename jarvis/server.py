"""HTTP API + live dashboard for JARVIS OS."""
from __future__ import annotations

import asyncio
import json
import queue
import re
import threading
import urllib.parse
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .agents import AGENTS, roster
from .bus import Bus
from .config import ROOT, settings
from .engine import Engine
from . import brain
from . import channels as ch
from . import devices
from . import telegram as tg
from . import voice
from .notify import channels
from .scheduler import Scheduler
from .store import Store
from .tools import ToolContext, execute

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
    bot = tg.Bot(on_reply=pick_reply, on_proposal=answer_proposal,
                 on_text=lambda text, voice=False: handle_owner_message(text, "Telegram", voice),
                 on_decision=lambda msg_id, yes: approve_message(msg_id) if yes else reject_message(msg_id),
                 log=lambda m: bus.log("JARVIS", m, "system"))
    bot.start()
    bus.log("JARVIS", "JARVIS OS online.", "system")
    yield
    bot.stop()
    scheduler.stop()


app = FastAPI(title="JARVIS OS", lifespan=lifespan)


# ---------------------------------------------------------------- phone access: PIN lock
# On the laptop itself (127.0.0.1) no PIN is needed. Opened from anywhere else - your phone through Tailscale -
# every page and API call needs the PIN once (then a 30-day cookie).
OPEN_PATHS = {"/login.html", "/api/login", "/manifest.webmanifest", "/sw.js", "/icon-192.png", "/icon-512.png",
              "/favicon.ico"}
_failed: list[float] = []


def _is_local(request: Request) -> bool:
    host = (request.headers.get("host") or "").split(":")[0].lower()
    proxied = any(request.headers.get(h) for h in ("x-forwarded-for", "x-forwarded-host", "forwarded",
                                                    "tailscale-user-login"))
    client = request.client.host if request.client else ""
    return host in ("127.0.0.1", "localhost") and not proxied and client in ("127.0.0.1", "::1", "testclient")


def _auth_cookie() -> str:
    import hashlib
    import hmac
    return hmac.new(settings.bridge_token.encode(), f"pin:{settings.access_pin}".encode(), hashlib.sha256).hexdigest()


@app.middleware("http")
async def pin_lock(request: Request, call_next):
    path = request.url.path
    if (_is_local(request) or path in OPEN_PATHS or path.startswith("/mcp/")
            or path == "/api/whatsapp/incoming"):   # these two check their own secret token
        return await call_next(request)
    if not settings.access_pin:
        return JSONResponse({"detail": "Set JARVIS_PIN in .env to use JARVIS from your phone."}, status_code=403)
    if request.cookies.get("jarvis_auth") == _auth_cookie():
        return await call_next(request)
    if path.startswith("/api/"):
        return JSONResponse({"detail": "PIN required"}, status_code=401)
    return RedirectResponse(f"/login.html?next={urllib.parse.quote(path)}")


class Pin(BaseModel):
    pin: str


@app.post("/api/login")
def login(p: Pin, request: Request):
    import hmac
    import time as _time
    now = _time.time()
    _failed[:] = [t for t in _failed if now - t < 600]
    if len(_failed) >= 5:
        raise HTTPException(429, "Too many wrong PINs. Wait 10 minutes.")
    if not settings.access_pin or not hmac.compare_digest(p.pin.strip(), settings.access_pin):
        _failed.append(now)
        raise HTTPException(401, "Wrong PIN")
    resp = JSONResponse({"ok": True})
    secure = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
    resp.set_cookie("jarvis_auth", _auth_cookie(), max_age=30 * 86400, httponly=True, samesite="lax", secure=secure)
    return resp


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


class BrainMode(BaseModel):
    mode: str
    hours: float | None = None


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


# ---------------------------------------------------------------- suggested replies
def pick_reply(sid: int, option: int | None, custom: str = "") -> str:
    from .actions import choose_reply, ignore_reply
    if option is None and not custom:
        return ignore_reply(store, bus, sid)
    r = choose_reply(store, bus, sid, option, custom)
    if r.get("error") and not r.get("to"):
        return r["error"]
    return f"✉ Sent to {r['to']}." if r["sent"] else f"Couldn't send: {r['error']}"


# ---------------------------------------------------------------- natural answers ("yes", "nah", "send B")
def answer_naturally(text: str) -> str | None:
    """If `text` is a bare answer to the latest open question, act on it. Uses no AI."""
    from . import answers
    parsed = answers.parse(text)
    if not parsed:
        return None
    latest = answers.latest_open(store)
    if not latest:
        return None  # nothing on file: let the agent you're talking to answer its own question ("Shall I…?" "Yes")
    kind, row = latest
    verdict, idx = parsed
    if kind == "proposal":
        if verdict == "option":
            return None
        return answer_proposal(row["id"], verdict == "yes")
    if kind == "suggestion":
        if verdict == "no":
            return pick_reply(row["id"], None)
        if verdict == "yes":
            if len(row["options"]) == 1:
                return pick_reply(row["id"], 0)
            return "Which one - " + ", ".join(f"{'ABCD'[i]}: {o['label']}" for i, o in enumerate(row["options"])) + "?"
        return pick_reply(row["id"], idx)
    if verdict == "option":
        return None
    return approve_message(row["id"]) if verdict == "yes" else reject_message(row["id"])


# ---------------------------------------------------------------- proposals (yes / no)
def answer_proposal(pid: int, yes: bool) -> str:
    """Owner answered a proposal. 'Yes' runs the agent's plan in the background and reports back when done."""
    from .actions import decide_proposal
    p = store.get_proposal(pid)
    if not p or p["status"] != "open":
        return f"Proposal #{pid} isn't waiting any more."
    if not yes:
        return decide_proposal(engine, pid, False)

    def work():
        result = decide_proposal(engine, pid, True)
        bus.log(p["agent"], result, "reply")
        if tg.ready():
            try:
                tg.send(f"✅ {result}")
            except Exception as exc:  # noqa: BLE001
                bus.log("JARVIS", f"Telegram send failed: {exc}", "error")

    threading.Thread(target=work, daemon=True).start()
    return "👍 On it, Sir - doing it now."


PROPOSAL_RE = re.compile(r"^\s*(yes|y|ok|do it|no|n|nope)\s+(?:to\s+)?(?:idea|proposal|p)\s*#?(\d+)\s*$", re.I)


@app.post("/api/proposals/{pid}/{answer}")
def proposal_answer(pid: int, answer: str):
    if answer not in ("yes", "no"):
        raise HTTPException(400, "answer must be yes or no")
    return {"result": answer_proposal(pid, answer == "yes")}


REPLY_RE = re.compile(r"^\s*reply\s+#?(\d+)\s*(?:[:,-]\s*|\s+)(?:([abcd])\s*$|(.+))", re.I | re.S)


class ReplyChoice(BaseModel):
    option: int | None = None
    body: str = ""


@app.post("/api/suggestions/{sid}/choose")
def choose(sid: int, c: ReplyChoice):
    return {"result": pick_reply(sid, c.option, c.body)}


@app.post("/api/suggestions/{sid}/ignore")
def ignore(sid: int):
    return {"result": pick_reply(sid, None)}


# ---------------------------------------------------------------- brain & pause switch
def control(text: str) -> str | None:
    """Pause / saver / resume / status commands - handled instantly, without any AI."""
    reply = brain.handle_control(store, text)
    if reply:
        bus.publish({"type": "brain", **brain.describe(store)})
    return reply


@app.get("/api/brain")
def get_brain():
    return brain.describe(store)


@app.post("/api/brain")
def set_brain(b: BrainMode):
    try:
        brain.set_mode(store, b.mode, b.hours)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    state = brain.describe(store)
    bus.publish({"type": "brain", **state})
    bus.log("JARVIS", {"on": "▶ Back online.", "saver": "🔋 Saver mode: leaving your Claude plan alone.",
                       "paused": "⏸ Paused. No AI use until you resume."}[b.mode], "system")
    return state


# ---------------------------------------------------------------- MCP endpoint (tools for the Claude Code brain)
@app.get("/mcp/{agent_name}")
def mcp_get(agent_name: str):
    return Response(status_code=405)  # no server-initiated stream needed


@app.post("/mcp/{agent_name}")
async def mcp(agent_name: str, request: Request, depth: int = 0, approved: int = 0,
              x_jarvis_token: str = Header(default="")):
    if not settings.bridge_token or x_jarvis_token != settings.bridge_token:
        raise HTTPException(403, "bad token")
    agent = AGENTS.get(agent_name.upper())
    if agent is None:
        raise HTTPException(404, "unknown agent")
    payload = await request.json()
    batch = payload if isinstance(payload, list) else [payload]
    answers = [a for a in [await _mcp_handle(agent, depth, m, bool(approved)) for m in batch] if a is not None]
    if not answers:
        return Response(status_code=202)
    return JSONResponse(answers if isinstance(payload, list) else answers[0])


async def _mcp_handle(agent, depth: int, msg: dict, approved: bool = False) -> dict | None:
    method, msg_id, params = msg.get("method"), msg.get("id"), msg.get("params") or {}
    if msg_id is None:
        return None  # notification (e.g. notifications/initialized)
    if method == "initialize":
        result = {"protocolVersion": params.get("protocolVersion", "2025-06-18"),
                  "capabilities": {"tools": {"listChanged": False}},
                  "serverInfo": {"name": "jarvis", "version": "1.0"}}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        from .tools import REGISTRY
        result = {"tools": [{"name": n, "description": REGISTRY[n].description,
                             "inputSchema": REGISTRY[n].schema()["input_schema"]}
                            for n in engine.tool_names_for(agent)]}
    elif method == "tools/call":
        name, args = params.get("name", ""), params.get("arguments") or {}
        if name not in engine.tool_names_for(agent):
            output, is_error = f"Tool {name} is not available to {agent.name}", True
        else:
            from .engine import _describe_call
            bus.log(agent.name, _describe_call(name, args), "tool")
            ctx = ToolContext(store, bus, settings, engine, agent.name, depth, approved)
            output, is_error = await asyncio.to_thread(execute, name, ctx, args)
        result = {"content": [{"type": "text", "text": output[:20000]}], "isError": is_error}
    else:
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32601, "message": f"Unknown method {method}"}}
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


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
        "suggestions": store.list_suggestions("open", 20),
        "proposals": store.list_proposals("open", 20),
        "proposals_done": store.list_proposals("done", 5),
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
    if (reply := control(cmd.text)) is not None or (reply := answer_naturally(cmd.text)) is not None:
        bus.publish({"type": "delta", "rid": cmd.rid, "agent": "JARVIS", "text": reply})
        bus.publish({"type": "delta_end", "rid": cmd.rid, "agent": "JARVIS"})
        bus.log("JARVIS", reply, "reply")
        return {"agent": "JARVIS", "reply": reply}

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
    if (reply := control(text)) is not None:
        bus.log("YOU", f"({via}) {text}", "command")
        return reply
    if (reply := answer_naturally(text)) is not None:  # "yes", "nah leave it", "send the second one"
        bus.log("YOU", f"({via}) {text}", "command")
        return reply
    if m := PROPOSAL_RE.match(text):  # "yes idea 4" / "no idea 4"
        return answer_proposal(int(m.group(2)), m.group(1).lower() in ("yes", "y", "ok", "do it"))
    if m := REPLY_RE.match(text):  # "reply 3: my own words"  /  "reply 3 b"
        letter, words = m.group(2), m.group(3)
        return pick_reply(int(m.group(1)), "abcd".index(letter.lower()) if letter else None, (words or "").strip())
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
