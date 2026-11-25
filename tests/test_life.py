"""Offline tests for the friend layer, ask-my-files, crew/invoices/rundowns, focus, protocols and phone replies."""
import json
import zipfile
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
    monkeypatch.setattr(devices, "WORKSPACE", tmp_path / "ws")
    return store, bus, engine, ToolContext(store, bus, settings, engine, "JARVIS")


def run(ctx, tool_name, **args):
    out, err = execute(tool_name, ctx, args)
    assert not err, out
    return json.loads(out)


def test_mood_gratitude_and_dates(env):
    store, _b, _e, ctx = env
    run(ctx, "log_mood", mood=2, energy=3, sleep=2, note="exam stress")
    run(ctx, "log_mood", mood=4)
    rep = run(ctx, "mood_report", days=7)
    assert rep["average"]["mood"] == 3.0 and len(rep["entries"]) == 2
    run(ctx, "log_gratitude", text="Nailed the presentation")
    assert run(ctx, "good_moments")[0]["text"] == "Nailed the presentation"
    soon = (ctx.now().date() + timedelta(days=3))
    run(ctx, "add_important_date", person="Mum", date=f"1970-{soon:%m-%d}")
    up = run(ctx, "upcoming_dates", days=7)
    assert up[0]["person"] == "Mum" and up[0]["in_days"] == 3 and up[0]["turning"] == soon.year - 1970


def test_ask_my_files(env, monkeypatch, tmp_path):
    store, _b, _e, ctx = env
    docs = tmp_path / "Documents"
    docs.mkdir()
    (docs / "fin302-notes.txt").write_text("Forward contracts hedge currency risk. The exam covers hedging strategies.")
    with zipfile.ZipFile(docs / "Week5.pptx", "w") as z:
        z.writestr("ppt/slides/slide1.xml", "<p:sld><a:p><a:t>Net present value</a:t></a:p></p:sld>")
        z.writestr("ppt/slides/slide2.xml", "<p:sld><a:p><a:t>Discounting cash flows at WACC</a:t></a:p></p:sld>")
    with zipfile.ZipFile(docs / "Essay.docx", "w") as z:
        z.writestr("word/document.xml", "<w:document><w:p><w:t>Globalisation and supply chains</w:t></w:p></w:document>")
    (docs / "DBS statement.txt").write_text("hedging secret balance")   # bank files are never read
    monkeypatch.setenv("JARVIS_STUDY_FOLDERS", str(docs))
    from jarvis import files_index
    assert files_index.index(store)["indexed"] == 3
    hits = run(ctx, "search_my_files", query="hedging")["results"]
    assert [h["file"] for h in hits] == ["fin302-notes.txt"]
    hit = run(ctx, "search_my_files", query="WACC")["results"][0]
    assert hit["file"] == "Week5.pptx" and hit["where"] == "slide 2"
    assert run(ctx, "search_my_files", query="supply chains")["results"][0]["file"] == "Essay.docx"
    assert files_index.index(store)["indexed"] == 0   # unchanged files aren't read again


def test_exam_mode(env):
    store, _b, _e, ctx = env
    when = (ctx.now() + timedelta(days=10)).strftime("%Y-%m-%dT09:00")
    run(ctx, "add_exam", course="FIN302", exam_at=when, topics="hedging, NPV")
    assert run(ctx, "list_exams")[0]["days_left"] == 10
    assert store.list_events(when[:10], "2100-01-01")[0]["title"] == "EXAM: FIN302"
    from jarvis.scheduler import Scheduler
    sc = Scheduler(ctx.engine)
    quiz = next(j for j in sc.jobs if j.name == "exam_quiz")
    assert quiz.when(sc) and quiz.deliver


def test_crew_payment_invoice_rundown(env):
    store, _b, _e, ctx = env
    gid = run(ctx, "add_gig", client="Priya", event_type="Wedding", event_date=(ctx.now().date() + timedelta(days=5)).isoformat())["gig_id"]
    store.update_gig(gid, quote_total=10000)
    a = run(ctx, "add_crew", name="Ali Hassan", phone="+65 9123 4567", role="usher")["crew_id"]
    b = run(ctx, "add_crew", name="Mei Ling", phone="91234568", role="usher")["crew_id"]
    run(ctx, "assign_crew", gig_id=gid, crew_ids=[a, b], role="usher", call_time="16:00")
    busy = run(ctx, "list_crew", event_date=store.get_gig(gid)["event_date"])
    assert all(c["booked_that_day"] for c in busy)
    links = run(ctx, "crew_message", gig_id=gid, message="Hi {name}, you're on at 4pm Sat!")["links"]
    assert "wa.me/6591234567?text=Hi%20Ali" in links[0]
    pay = run(ctx, "record_payment", gig_id=gid, amount=3000, note="deposit")
    assert pay["balance"] == 7000 and store.get_gig(gid)["deposit_paid"] == 1
    inv = run(ctx, "make_invoice", gig_id=gid, send_to_phone=False)
    from pypdf import PdfReader
    text = PdfReader(inv["pdf"]).pages[0].extract_text()
    assert "INVOICE" in text and "7,000.00" in text and inv["balance"] == 7000
    rd = run(ctx, "make_rundown", gig_id=gid, items=[{"time": "16:00", "what": "Crew call", "who": "All"},
                                                      {"time": "19:00", "what": "Grand entrance"}])
    assert rd["reminders_scheduled"] == 2 and "Grand entrance" in PdfReader(rd["pdf"]).pages[0].extract_text()


def test_workouts_and_streak(env):
    store, _b, _e, ctx = env
    for d in range(3):
        day = (ctx.now().date() - timedelta(days=d)).isoformat()
        run(ctx, "log_workout", sets=[{"exercise": "Bench press", "sets": 3, "reps": 8, "weight_kg": 60 + d}], day=day)
    hist = run(ctx, "workout_history")
    assert hist["best"][0]["best_kg"] == 62 and len(hist["sessions"]) == 3


def test_focus_and_clean_slate(env):
    store, _b, _e, ctx = env
    from jarvis.life import in_focus
    run(ctx, "focus_mode", minutes=30, task="essay")
    assert in_focus(store)
    run(ctx, "focus_mode", minutes=0)
    assert not in_focus(store)
    store.add_task("Overdue thing", due=(ctx.now().date() - timedelta(days=2)).isoformat())
    store.add_task("Later thing", due=(ctx.now().date() + timedelta(days=5)).isoformat())
    assert run(ctx, "clean_slate")["moved"] == 1


def test_special_phrases(monkeypatch):
    from jarvis import server
    d, a, p = server.special("Jarvis, suit up for 25 minutes on the essay")
    assert "25 minutes" in d and a is None
    assert server.special("Jarvis clean slate protocol")[0].startswith("🧹")
    assert server.special("i can't sleep")[1] == "BANNER"
    assert server.special("hype me up for my interview")[1] == "ZEUS"
    assert server.special("what should I do now?")[1] == "JARVIS"
    assert server.special("house party protocol")[1] == "PEPPER"
    assert server.special("remind me to suit up tomorrow") == (None, None, None)
    server.special("end focus")


def test_phone_smart_replies(monkeypatch):
    from fastapi.testclient import TestClient
    from jarvis import brain, server
    client = TestClient(server.app, base_url="http://127.0.0.1:7334", client=("127.0.0.1", 50000))
    tok = client.get("/api/phone/token").json()["token"]
    monkeypatch.setattr(brain, "pick", lambda *a, **k: "gemini")
    monkeypatch.setattr(server.engine, "run", lambda agent, prompt, **k:
                        'Sure! {"replies": ["Yes, see you at 8!", "Can we do 9?"]}')
    body = {"sender": "Priya", "text": "Dinner tonight at 8?"}
    assert client.post("/api/phone/notification", json=body, headers={"X-Jarvis-Device": "wrong"}).status_code == 401
    r = client.post("/api/phone/notification", json=body, headers={"X-Jarvis-Device": tok}).json()
    assert r["replies"] == ["Yes, see you at 8!", "Can we do 9?"]
    otp = {"sender": "Bank", "text": "Your OTP is 123456"}
    assert client.post("/api/phone/notification", json=otp, headers={"X-Jarvis-Device": tok}).json()["replies"] == []
    grp = {**body, "group": True}
    assert client.post("/api/phone/notification", json=grp, headers={"X-Jarvis-Device": tok}).json()["replies"] == []


def test_housekeeping_dry_run(monkeypatch, tmp_path):
    import os
    from jarvis import life
    monkeypatch.setattr(life.Path, "home", lambda: tmp_path)
    dl = tmp_path / "Downloads"
    dl.mkdir()
    old = dl / "old.zip"
    old.write_text("x")
    os.utime(old, (0, 0))
    (dl / "new.pdf").write_text("y")
    out = life.housekeeping(dry_run=True)
    assert out["moved_to_old"] == 1 and old.exists()


def test_checkin_delivery_routes_reply_to_same_agent(env, monkeypatch):
    from jarvis import telegram as tg
    from jarvis.scheduler import Scheduler
    store, _b, engine, _ctx = env
    sent = []
    monkeypatch.setattr(tg, "ready", lambda: True)
    monkeypatch.setattr(tg, "send", lambda text, **k: sent.append(text))
    monkeypatch.setattr(settings, "telegram_voice", False)
    from jarvis import speech
    monkeypatch.setattr(speech, "in_quiet_hours", lambda *a, **k: False)   # awake: deliver now (asleep is held)
    sc = Scheduler(engine)
    sc.deliver("BANNER", "How did today really go?")
    assert sent == ["BANNER: How did today really go?"]
    assert store.get("telegram:last_agent").startswith("BANNER|")
    names = {j.name for j in sc.jobs}
    assert {"evening_checkin", "heart_to_heart", "fitness_weekly", "monthly_report", "career_weekly"} <= names
