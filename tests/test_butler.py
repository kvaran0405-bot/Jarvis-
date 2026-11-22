"""Mark III phase 3: deep memory, home manager, Stark Daily, leave-now alerts, nudges, context radar."""
import json
from datetime import datetime, timedelta

import pytest

from jarvis import devices
from jarvis.bus import Bus
from jarvis.config import settings
from jarvis.engine import Engine
from jarvis.store import Store
from jarvis.tools import ToolContext, execute


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "timezone", "Asia/Singapore")
    store = Store(":memory:")
    bus = Bus(store)
    engine = Engine(store, bus, settings)
    monkeypatch.setattr(devices, "WORKSPACE", tmp_path)
    return store, bus, engine, ToolContext(store, bus, settings, engine, "JARVIS")


def run(ctx, tool_name, **a):
    out, err = execute(tool_name, ctx, a)
    assert not err, out
    return json.loads(out)


def test_find_anything_searches_everywhere(env):
    store, bus, _e, ctx = env
    store.add_note("Venue contract", "Raffles ballroom contract signed by Mei")
    store.add_event("Site visit Raffles", "2030-01-02T10:00", None, "Raffles Hotel", "career")
    store.add_gig("Priya", venue="Raffles Hotel")
    bus.log("YOU", "remember the raffles parking is at level B2", "command")
    out = run(ctx, "find_anything", query="raffles contract")
    assert out["notes"][0]["title"] == "Venue contract"
    assert out["events"] and out["clients"] and out["conversations"]


def test_network_and_coaching(env):
    store, _b, _e, ctx = env
    run(ctx, "log_meeting", person="Daniel Tan", where="Nexus D&D", notes="daughter's wedding next year")
    run(ctx, "log_meeting", person="Daniel Tan", where="Kaplan careers fair", notes="hiring analysts")
    c = store.query("SELECT notes FROM contacts WHERE name='Daniel Tan'")[0]["notes"]
    assert "Nexus D&D" in c and "hiring analysts" in c
    assert run(ctx, "network_radar", days=0)[0]["name"] == "Daniel Tan"
    run(ctx, "coach_agent", agent="friday", note="He likes short hype, no lists")
    assert store.agent_notes("FRIDAY")[0]["note"] == "He likes short hype, no lists"
    assert "error" in run(ctx, "coach_agent", agent="GUEST", note="x")


def test_home_manager(env):
    store, _b, _e, ctx = env
    assert run(ctx, "grocery_list", action="add", items=["Eggs", "milo", "eggs"])["grocery_list"] == ["Eggs", "milo"]
    assert run(ctx, "grocery_list", action="remove", items=["EGGS"])["grocery_list"] == ["milo"]
    exp = (ctx.now().date() + timedelta(days=90)).isoformat()
    assert run(ctx, "track_expiry", name="Passport", expires=exp)["reminders"] == 3
    assert store.list_events(exp, "2100-01-01")[0]["title"] == "Expires: Passport"


def test_stark_daily_pdf(env):
    store, _b, _e, ctx = env
    out = run(ctx, "publish_newspaper", headline="Raffles Wedding Tonight", lead="Crew of 12 ready; storms at six.",
              stories=[{"section": "Business", "title": "Nexus goes quiet", "body": "Pepper suggests a follow-up."},
                       {"section": "Markets", "title": "STI flat", "body": "SGD steady."}], quote="Sometimes you gotta run.")
    from pypdf import PdfReader
    text = PdfReader(out["pdf"]).pages[0].extract_text()
    assert "The Stark Daily" in text and "Raffles Wedding Tonight" in text and "Nexus goes quiet" in text
    assert store.list_reports(1)[0]["kind"] == "newspaper"


def test_leave_now_alert_once(env, monkeypatch):
    store, bus, _e, ctx = env
    from jarvis import butler, telegram as tg
    monkeypatch.setenv("JARVIS_TRAVEL_MINUTES", "40")
    monkeypatch.setattr(tg, "ready", lambda: False)
    monkeypatch.setattr("jarvis.hud.weather_now", lambda: None)
    start = (datetime.now(settings.tz) + timedelta(minutes=35)).replace(tzinfo=None).isoformat(timespec="minutes")
    store.add_event("Priya wedding", start, None, "Raffles Hotel", "career")
    store.add_event("Zoom call", start, None, "Zoom", "career")
    said = []
    monkeypatch.setattr(bus, "publish", said.append)
    monkeypatch.setattr(settings, "proactive_voice", True)
    monkeypatch.setattr(settings, "quiet_hours", "00:00-00:01")
    sent = butler.leave_now_check(store, bus)
    assert len(sent) == 1 and "Priya wedding" in sent[0] and "Raffles" in sent[0]
    assert butler.leave_now_check(store, bus) == []


def test_nudge_only_when_present(env, monkeypatch):
    store, bus, _e, _ctx = env
    from jarvis import butler
    monkeypatch.setattr(settings, "quiet_hours", "00:00-00:01")
    monkeypatch.setattr(butler, "datetime", type("D", (), {"now": staticmethod(lambda tz=None: datetime(2030, 1, 1, 14, 0, tzinfo=tz)),
                                                          "fromisoformat": staticmethod(datetime.fromisoformat)}))
    bus._subs.append(object())   # a dashboard is connected
    assert butler.wellness_nudge(store, bus) is None          # owner not seen recently
    store.set("owner:last_seen", datetime(2030, 1, 1, 13, 50, tzinfo=settings.tz).isoformat())
    events = []
    monkeypatch.setattr(bus, "publish", events.append)
    assert butler.wellness_nudge(store, bus) in butler.NUDGES and events[0]["type"] == "nudge"


def test_context_radar_and_style(env):
    store, bus, engine, _ctx = env
    from jarvis.agents import AGENTS
    bus.log("YOU", "bro can u tell pepper the tan family wan the gold package", "command")
    bus.log("PEPPER", "Noted, gold package for the Tans.", "reply")
    block = engine._context_block(AGENTS["HERALD"])
    assert "Today's conversation" in block and "gold package" in block and "How the owner writes" in block
    assert "How the owner writes" not in engine._context_block(AGENTS["STEVE"])


def test_butler_phrases_and_jobs(env):
    from jarvis import server
    assert server.special("plan a date night for saturday")[1] == "ORACLE"
    assert server.special("mission briefing for the DBS interview")[1] == "JARVIS"
    from jarvis.scheduler import Scheduler
    _s, _b, engine, ctx = env
    sc = Scheduler(engine)
    names = {j.name for j in sc.jobs}
    assert {"anticipate", "team_tuneup", "mission_briefing"} <= names
    assert not sc.big_day()
    engine.store.add_event("FIN302 EXAM", ctx.today() + "T09:00", None, "", "academic")
    assert sc.big_day()
