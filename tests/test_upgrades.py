"""Offline tests for Google Calendar sync, the lecture recorder and the business kit (no network, no AI)."""
import json
import sqlite3

import pytest

from jarvis import devices, gcal, lectures
from jarvis.agents import AGENTS
from jarvis.bus import Bus
from jarvis.config import settings
from jarvis.engine import Engine
from jarvis.store import Store
from jarvis.tools import REGISTRY, ToolContext, execute


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "timezone", "Asia/Singapore")
    store = Store(":memory:")
    bus = Bus(store)
    engine = Engine(store, bus, settings)
    gcal.attach(store)
    lectures.attach(engine)
    monkeypatch.setattr(devices, "WORKSPACE", tmp_path)
    monkeypatch.setattr(lectures, "FOLDER", tmp_path / "lectures")
    monkeypatch.setenv("JARVIS_GOOGLE_SCRIPT_URL", "")
    return store, bus, engine, ToolContext(store, bus, settings, engine, "PEPPER")


def test_old_database_gets_new_columns(tmp_path):
    path = tmp_path / "old.db"
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE events (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, start TEXT NOT NULL, "
               "end TEXT, location TEXT DEFAULT '', area TEXT DEFAULT 'personal', notes TEXT DEFAULT '')")
    db.commit()
    db.close()
    store = Store(path)
    cols = {r["name"] for r in store.query("PRAGMA table_info(events)")}
    assert "gid" in cols
    assert "attachment" in {r["name"] for r in store.query("PRAGMA table_info(outbox)")}


def test_every_agent_tool_exists():
    for agent in AGENTS.values():
        missing = [t for t in agent.tools if t not in REGISTRY]
        assert not missing, (agent.name, missing)
    assert "PEPPER" in AGENTS and "make_quote" in AGENTS["PEPPER"].tools
    assert "start_recording" in AGENTS["JARVIS"].tools


# ---------------------------------------------------------------- Google Calendar
class FakeGoogle:
    def __init__(self):
        self.events = {"g1": {"id": "g1", "title": "Dentist", "start": "2030-01-10T02:00:00.000Z",
                              "end": "2030-01-10T03:00:00.000Z", "allDay": False, "location": "", "notes": ""}}
        self.calls = []

    def __call__(self, url, payload, timeout=30):
        self.calls.append(payload)
        a = payload["action"]
        if a == "ping":
            return {"ok": True, "calendar": "kamal@example.com", "timezone": "Asia/Singapore"}
        if a == "list":
            return {"ok": True, "events": list(self.events.values())}
        if a == "create":
            gid = f"new{len(self.events)}"
            self.events[gid] = {"id": gid, "title": payload["title"], "start": payload["start"],
                                "end": payload["end"] or payload["start"], "allDay": payload["allDay"],
                                "location": "", "notes": ""}
            return {"ok": True, "id": gid}
        if a == "delete":
            self.events.pop(payload["id"], None)
            return {"ok": True, "deleted": True}
        raise AssertionError(a)


def test_google_connect_and_two_way_sync(env, monkeypatch):
    store, _bus, _engine, ctx = env
    fake = FakeGoogle()
    monkeypatch.setattr(gcal, "_post", fake)
    with pytest.raises(ValueError):
        gcal.connect("https://example.com/not-a-script")
    gcal.connect("https://script.google.com/macros/s/abc/exec")
    assert gcal.ready() and fake.calls[0]["key"] == gcal.key()
    assert gcal.key() in gcal.script_text()

    # JARVIS adds an event -> pushed to Google with the owner's timezone
    out, err = execute("add_event", ctx, {"title": "Site visit", "start": "2030-01-12T15:00"})
    assert not err and json.loads(out)["google_calendar"] == "added"
    create = next(c for c in fake.calls if c["action"] == "create")
    assert create["start"] == "2030-01-12T15:00:00+08:00" and create["end"] == "2030-01-12T16:00:00+08:00"

    # Google's events are pulled in, in local time, without duplicating the pushed one
    monkeypatch.setattr(gcal, "SYNC_DAYS_AHEAD", 10_000)
    assert gcal.sync(force=True)["synced"]
    titles = sorted((e["title"], e["start"]) for e in store.list_events("2030-01-01", "2030-02-01"))
    assert titles == [("Dentist", "2030-01-10T10:00"), ("Site visit", "2030-01-12T15:00")]

    # deleted in Google -> removed here on the next sync
    fake.events.pop("g1")
    gcal.sync(force=True)
    assert [e["title"] for e in store.list_events("2030-01-01", "2030-02-01")] == ["Site visit"]

    # deleted here -> deleted in Google
    eid = store.list_events("2030-01-01", "2030-02-01")[0]["id"]
    execute("delete_event", ctx, {"event_id": eid})
    assert not fake.events


def test_google_errors_dont_break_the_calendar(env, monkeypatch):
    store, _bus, _engine, ctx = env
    monkeypatch.setenv("JARVIS_GOOGLE_SCRIPT_URL", "https://script.google.com/macros/s/abc/exec")

    def down(*a, **k):
        raise RuntimeError("offline")
    monkeypatch.setattr(gcal, "_post", down)
    out, err = execute("add_event", ctx, {"title": "Gym", "start": "2030-03-01T07:00"})
    assert not err and "retry" in json.loads(out)["google_calendar"]
    assert store.list_events("2030-03-01", "2030-03-02")[0]["title"] == "Gym"
    assert not gcal.sync(force=True)["synced"] and "offline" in gcal.status()["error"]


# ---------------------------------------------------------------- lecture recorder
def test_recording_is_transcribed_and_summarised(env, monkeypatch):
    store, bus, engine, _ctx = env
    from jarvis import brain, stt
    monkeypatch.setattr(stt, "available", lambda: True)
    monkeypatch.setattr(stt, "transcribe_long", lambda path, model="", on_progress=None:
                        ([(0.0, "Welcome to FIN302."), (65.0, "The exam will cover hedging, remember that.")], 600.0))
    monkeypatch.setattr(brain, "pick", lambda store, background=False, preferred="": "gemini")
    prompts = []

    def fake_run(agent, prompt, **kw):
        prompts.append((agent, prompt, kw))
        return "## Summary\nHedging.\n## Key points\n- [01:05] exam covers hedging"
    monkeypatch.setattr(engine, "run", fake_run)
    audio = lectures.new_upload_path("week 6.m4a")
    audio.write_bytes(b"x" * 2000)
    lid = store.add_lecture("FIN302 week 6", "FIN302", str(audio), "transcribing")
    lectures.process(store, bus, lid)
    lec = store.get_lecture(lid)
    assert lec["status"] == "ready" and lec["duration_s"] == 600
    assert "[01:05] The exam will cover hedging" in lec["transcript"]
    assert prompts[0][0] == "ATHENA" and prompts[0][2]["background"] and "FIN302" in prompts[0][1]
    note = store.search_notes("hedging")[0]
    assert note["title"] == "Lecture: FIN302 week 6" and "## Transcript" in note["body"]
    out, _ = execute("read_lecture", ToolContext(store, bus, settings, engine, "ATHENA"),
                     {"lecture_id": lid, "query": "exam"})
    assert "hedging" in json.loads(out)["transcript"] and "Welcome" not in json.loads(out)["transcript"]


def test_paused_recording_keeps_transcript_for_later(env, monkeypatch):
    store, bus, _engine, _ctx = env
    from jarvis import brain, stt
    monkeypatch.setattr(stt, "available", lambda: True)
    monkeypatch.setattr(stt, "transcribe_long", lambda *a, **k: ([(0.0, "Hello class")], 60.0))
    monkeypatch.setattr(brain, "pick", lambda *a, **k: None)
    lid = store.add_lecture("Week 1", "", "x.m4a", "transcribing")
    lectures.process(store, bus, lid)
    assert store.get_lecture(lid)["status"] == "transcribed"
    assert store.search_notes("Hello class")


def test_no_speech_marks_failed(env, monkeypatch):
    store, bus, _engine, _ctx = env
    from jarvis import stt
    monkeypatch.setattr(stt, "available", lambda: True)
    monkeypatch.setattr(stt, "transcribe_long", lambda *a, **k: ([], 30.0))
    lid = store.add_lecture("Silence", "", "x.m4a", "transcribing")
    lectures.process(store, bus, lid)
    assert store.get_lecture(lid)["status"] == "failed"


# ---------------------------------------------------------------- business kit
def test_gig_pipeline_quote_and_checklist(env, monkeypatch):
    store, _bus, _engine, ctx = env
    out, _ = execute("add_gig", ctx, {"client": "Priya & Arun", "event_type": "wedding", "event_date": "2030-02-14",
                                      "venue": "Raffles", "guests": 300, "next_step": "send quote"})
    gid = json.loads(out)["gig_id"]
    out, err = execute("make_quote", ctx, {"gig_id": gid, "client": "Priya & Arun", "discount": 500,
                                           "items": [{"item": "Gold package", "unit_price": 12000,
                                                      "details": "Coordination, ushers, emcee"},
                                                     {"item": "Photo booth", "qty": 1, "unit_price": 900}],
                                           "send_to_phone": False})
    q = json.loads(out)
    assert not err and q["total"] == 12400 and q["deposit"] == 3720
    from pypdf import PdfReader
    text = PdfReader(q["pdf"]).pages[0].extract_text()
    assert "QUOTATION" in text and "Priya & Arun" in text and "12,400.00" in text
    gig = store.get_gig(gid)
    assert gig["status"] == "quoted" and gig["quote_total"] == 12400

    out, _ = execute("gig_checklist", ctx, {"gig_id": gid, "steps": [{"title": "Confirm florist", "days_before": 30},
                                                                       {"title": "Final numbers", "days_before": 14}]})
    assert json.loads(out)["tasks_created"] == 2
    t = [x for x in store.list_tasks("open") if "Confirm florist" in x["title"]][0]
    assert t["due"] == "2030-01-15" and t["title"].startswith("[Priya & Arun]")
    assert [g["client"] for g in json.loads(execute("list_gigs", ctx, {})[0])] == ["Priya & Arun"]


def test_email_attachment_is_checked_and_queued(env, tmp_path):
    store, _bus, _engine, ctx = env
    out, _ = execute("send_email", ctx, {"to": "a@b.com", "subject": "Quote", "body": "Attached", "reason": "quote",
                                         "attachment": str(tmp_path / "missing.pdf")})
    assert "No file" in out
    f = tmp_path / "Q1.pdf"
    f.write_bytes(b"%PDF-1.4")
    execute("send_email", ctx, {"to": "a@b.com", "subject": "Quote", "body": "Attached", "reason": "quote",
                                "attachment": str(f)})
    assert store.list_outbox("pending")[0]["attachment"] == str(f)


# ---------------------------------------------------------------- claps, home, weather, job hunt, voices
def _audio_run(sig):
    import numpy as np
    from jarvis.clap import BLOCK, RATE, ClapDetector
    fired = []
    d = ClapDetector(lambda: fired.append(1))
    for k in range(0, len(sig) - BLOCK, BLOCK):
        b = sig[k:k + BLOCK]
        d.feed(k / RATE, float(abs(b).max()), float(np.sqrt((b ** 2).mean())))
    return len(fired)


def test_double_clap_only():
    np = pytest.importorskip("numpy")
    rng = np.random.default_rng(1)

    def room(sec):
        return rng.normal(0, 0.005, int(sec * 16000))

    def clap(sig, at):
        n = 480
        i = int(at * 16000)
        sig[i:i + n] += rng.normal(0, 0.4, n) * np.exp(-np.linspace(0, 6, n))
    s = room(4); clap(s, 1.0); clap(s, 1.4)
    assert _audio_run(s) == 1
    s = room(4); clap(s, 1.0)
    assert _audio_run(s) == 0
    s = room(4); clap(s, 1.0); clap(s, 1.4); clap(s, 1.8)
    assert _audio_run(s) == 0
    s = room(4); t = np.arange(32000) / 16000; s[16000:48000] += 0.3 * np.sin(2 * np.pi * 220 * t)
    assert _audio_run(s) == 0


def test_home_phrases():
    from jarvis.server import HOME_RE
    for t in ("Jarvis, I'm home", "im home", "I'm back!", "honey I'm home", "hey jarvis i am home"):
        assert HOME_RE.match(t), t
    for t in ("I'm home late tomorrow, remind me", "what's at home"):
        assert not HOME_RE.match(t), t


def test_clap_after_being_away_welcomes_home(monkeypatch):
    from datetime import datetime, timedelta
    from jarvis import server
    started = []
    monkeypatch.setattr(server.threading, "Thread", lambda target, daemon=True: type(
        "T", (), {"start": lambda self: started.append(target.__name__)})())
    events = []
    monkeypatch.setattr(server.bus, "publish", events.append)
    server.store.set("owner:last_seen", (datetime.now(settings.tz) - timedelta(hours=5)).isoformat())
    server.on_double_clap()
    assert started == ["welcome_home"]
    server.store.set("owner:last_seen", datetime.now(settings.tz).isoformat())
    server.on_double_clap()
    assert any(e.get("say") == "Yes Sir?" for e in events)


def test_weather_tool(env, monkeypatch):
    import io
    import urllib.request
    _store, _bus, _engine, ctx = env
    data = {"daily": {"time": ["2030-01-01", "2030-01-02"], "temperature_2m_max": [32, 31],
                      "temperature_2m_min": [26, 25], "precipitation_probability_max": [80, 10],
                      "weather_code": [95, 1]},
            "hourly": {"time": ["2030-01-01T15:00", "2030-01-01T16:00", "2030-01-02T15:00"],
                       "precipitation_probability": [70, 20, 5], "weather_code": [95, 3, 1]}}
    monkeypatch.setattr(urllib.request, "urlopen", lambda url, timeout=15: io.BytesIO(json.dumps(data).encode()))
    out = json.loads(execute("weather", ctx, {})[0])
    assert out["today"]["sky"] == "thunderstorms" and out["today"]["rainy_hours"] == ["15:00 70%"]
    assert out["tomorrow"]["rainy_hours"] == "none likely"


def test_job_hunt_is_scheduled(env):
    from jarvis.scheduler import Scheduler
    _store, _bus, engine, _ctx = env
    jobs = {j.name: j for j in Scheduler(engine).jobs}
    assert jobs["job_hunt"].agent == "ZEUS" and "list_applications" in jobs["job_hunt"].prompt
    assert "weather" in AGENTS["FRIDAY"].tools


def test_slow_voicestudio_hands_live_replies_to_quick_voices(monkeypatch):
    from jarvis import voice
    monkeypatch.setattr(voice, "_vs_speed", {"chars": 100, "secs": 10.0})   # 0.1 s per character
    assert voice.vs_too_slow_for("x" * 60) and not voice.vs_too_slow_for("Yes Sir.")
