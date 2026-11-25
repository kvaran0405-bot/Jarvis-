"""Offline tests: data layer, tools, scheduler timing, night shift wiring (no API calls)."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from jarvis.agents import AGENTS
from jarvis.bus import Bus
from jarvis.config import Settings
from jarvis.engine import Engine
from jarvis.scheduler import Scheduler, daily_at, every_hours
from jarvis.store import Store
from jarvis.tools import REGISTRY, ToolContext, execute


def make():
    store = Store(":memory:")
    bus = Bus(store)
    settings = Settings()
    return store, bus, settings, Engine(store, bus, settings)


def test_every_agent_tool_exists():
    for agent in AGENTS.values():
        for name in agent.tools:
            assert name in REGISTRY, (agent.name, name)


def test_tools_roundtrip():
    store, bus, settings, engine = make()
    ctx = ToolContext(store, bus, settings, engine, "JARVIS")
    out, err = execute("add_task", ctx, {"title": "Finish essay", "area": "academic", "due": "2000-01-01"})
    assert not err
    execute("add_task", ctx, {"title": "Research laptops", "assignee": "oracle"})
    execute("log_habit", ctx, {"name": "Gym"})
    execute("log_transaction", ctx, {"amount": -12.5, "category": "Food"})
    execute("add_application", ctx, {"company": "Acme", "role": "Intern", "status": "applied"})
    snap = REGISTRY["status_snapshot"].fn(ctx)
    assert snap["overdue"][0]["title"] == "Finish essay"
    assert snap["agent_queue"][0]["assignee"] == "ORACLE"
    assert snap["habits_last_7_days"][0]["done_count"] == 1
    assert snap["money_this_month"]["net"] == -12.5
    out, err = execute("nope", ctx, {})
    assert err
    out, err = execute("update_task", ctx, {"task_id": 1, "status": "done"})
    assert '"updated": true' in out


def test_publish_report_saves_without_channels():
    store, bus, settings, engine = make()
    ctx = ToolContext(store, bus, settings, engine, "FRIDAY")
    execute("publish_report", ctx, {"kind": "morning_brief", "title": "Brief", "body": "# Hi"})
    assert store.list_reports()[0]["agent"] == "FRIDAY"


def test_schedule_timing():
    tz = ZoneInfo("UTC")
    due = daily_at("07:00")
    at = datetime(2026, 11, 18, 7, 5, tzinfo=tz)
    assert due(at, None)
    assert not due(at, at.isoformat())                         # already ran today
    assert not due(at.replace(hour=6), None)                   # too early
    assert not due(at.replace(hour=11), None)                  # stale slot
    assert due(at, (at - timedelta(days=1)).isoformat())       # ran yesterday
    sunday = daily_at("18:00", weekday=6)
    assert not sunday(datetime(2026, 11, 18, 18, 1, tzinfo=tz), None)  # Wednesday
    assert sunday(datetime(2026, 11, 22, 18, 1, tzinfo=tz), None)
    assert every_hours(3)(at, (at - timedelta(hours=4)).isoformat())


def test_night_shift_skips_when_no_brain(monkeypatch):
    store, bus, settings, engine = make()
    from jarvis import brain
    monkeypatch.setattr(brain, "ready", lambda b: False)
    store.add_task("Research topic", assignee="ORACLE")
    result = Scheduler(engine).night_shift()
    assert "resting" in result
    assert store.list_tasks("open")[0]["status"] == "todo"


def test_night_shift_with_fake_engine(monkeypatch):
    store, bus, settings, engine = make()
    from jarvis import brain
    monkeypatch.setattr(brain, "pick", lambda store, background=False: "api")
    engine.run = lambda agent, prompt, **kw: f"{agent} finished it"
    store.add_task("Draft cover letter", area="career", assignee="ZEUS")
    Scheduler(engine).night_shift()
    t = store.list_tasks("done")[0]
    assert t["result"] == "ZEUS finished it"


def test_times_are_stored_in_owner_timezone(monkeypatch):
    store, bus, settings, engine = make()
    monkeypatch.setattr(settings, "timezone", "Africa/Lagos")
    ctx = ToolContext(store, bus, settings, engine, "ATHENA")
    execute("add_event", ctx, {"title": "Study", "start": "2026-11-23T17:00:00Z"})
    assert store.list_events("2026-11-23", "2026-11-24")[0]["start"] == "2026-11-23T18:00"
    execute("add_event", ctx, {"title": "Exam", "start": "2026-11-25T09:00"})
    assert store.list_events("2026-11-25", "2026-11-26")[0]["start"] == "2026-11-25T09:00"


def test_pages_are_never_stale():
    from fastapi.testclient import TestClient
    from jarvis import server
    r = TestClient(server.app).get("/gestures.js")
    assert r.status_code == 200 and r.headers.get("cache-control") == "no-cache"
