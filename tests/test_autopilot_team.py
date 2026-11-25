"""The owner's picks (Nov 2026): held-till-awake messages, budgets, subscriptions, follow-ups, scam shield, deadline
nudges, laptop care, Steam deals, and the agents' new daily jobs."""
import json
from datetime import datetime, timedelta
from types import SimpleNamespace

from jarvis import autopilot, deals, jobs, money, notify, scam, speech
from jarvis.config import settings
from jarvis.store import Store

BUS = SimpleNamespace(publish=lambda e: None, store=None, log=lambda *a, **k: None)


def test_messages_wait_until_the_owner_is_awake(monkeypatch, tmp_path):
    monkeypatch.setattr(notify, "_held_path", lambda: tmp_path / "held.json")
    sent = []
    monkeypatch.setattr(notify, "channels", lambda: ["telegram"])
    monkeypatch.setattr(notify.tg, "send", lambda text, buttons=None: sent.append(text))
    monkeypatch.setattr(speech, "in_quiet_hours", lambda now=None: True)
    assert notify.notify_owner("ZEUS", "52 jobs lined up") == ["held until you wake up"] and not sent
    notify.notify_owner("SENTINEL", "scam!", urgent=True)
    assert len(sent) == 1                                   # urgent goes through at once
    monkeypatch.setattr(speech, "in_quiet_hours", lambda now=None: False)
    assert notify.flush_held() == 1 and "While you slept" in sent[-1] and "52 jobs" in sent[-1]
    assert notify.flush_held() == 0


def test_budgets_warn_once_at_80_and_100(monkeypatch):
    st = Store(":memory:")
    said = []
    monkeypatch.setattr("jarvis.speech.announce", lambda bus, agent, text, **k: said.append(text) or True)
    monkeypatch.setattr("jarvis.notify.notify_owner", lambda *a, **k: ["ok"])
    st.set("money:budgets", json.dumps({"food": 100}))
    day = datetime.now(settings.tz).date().isoformat()
    st.log_transaction(day, -85, "food", "KOUFU · DBS (alert)")
    assert len(money.budget_check(st, BUS)) == 1 and "85" in said[0]
    assert money.budget_check(st, BUS) == []                       # once per level
    st.log_transaction(day, -20, "food", "KFC · DBS (alert)")
    assert "over budget" in money.budget_check(st, BUS)[0]


def test_subscriptions_are_found():
    st = Store(":memory:")
    today = datetime.now(settings.tz).date().replace(day=5)
    for k in range(3):
        d = (today - timedelta(days=31 * k)).isoformat()
        st.log_transaction(d, -15.98, "subscriptions", "NETFLIX.COM · DBS (alert)")
        st.log_transaction(d, -4.2 - k * 3, "food", "KOUFU · DBS (alert)")
    st.log_transaction(today.isoformat(), -9.9, "other", "SPOTIFY · DBS (alert)")
    names = {s["merchant"] for s in money.subscriptions(st)}
    assert "NETFLIX.COM" in names and "SPOTIFY" in names and "KOUFU" not in names


def test_follow_ups_after_a_week(monkeypatch):
    from jarvis import channels as ch
    st = Store(":memory:")
    jobs.add_job(st, {"source": "MCF", "title": "Event Coordinator", "company": "Big Events", "url": "u", "apply_email": "hr@big.sg"})
    old = (datetime.now(settings.tz) - timedelta(days=8)).isoformat(timespec="minutes")
    st.execute("UPDATE jobs SET status = 'emailed', acted = ?", (old,))
    fu = jobs.followups(st)
    assert len(fu) == 1 and "Event Coordinator" in jobs.followup_text(fu[0])
    sent = []
    monkeypatch.setattr(ch, "email_ready", lambda: True)
    monkeypatch.setattr(ch, "deliver", lambda store, bus, msg: sent.append(msg) or True)
    assert jobs.send_followups(st, BUS, [fu[0]["id"]])["sent"] == 1 and jobs.followups(st) == []
    assert sent[0]["subject"].startswith("Following up")


def test_scam_shield():
    for bad in ("Your parcel is held at customs. Pay the $2.50 fee here: bit.ly/x1",
                "Part time job! Like videos and earn $300 a day, contact us on Telegram t.me/jobsg",
                "DBS: your account will be suspended. Verify your account details at https://dbs-secure.xyz/login",
                "This is ICA officer, there is a case against you, transfer funds now"):
        assert scam.check(bad)["scam"], bad
    for fine in ("Hey bro, dinner at 8?", "Your Shopee order has been shipped", "Interview invitation: Marketing Executive, Friday 3pm"):
        assert not scam.check(fine)["scam"], fine
    st = Store(":memory:")
    assert not jobs.add_job(st, {"title": "Earn $500 a day liking videos", "company": "?", "url": "u", "descr": "part time, earn commission, Telegram"})


def test_deadline_nudges_3_days_and_1_day(monkeypatch):
    st = Store(":memory:")
    said = []
    monkeypatch.setattr("jarvis.speech.announce", lambda bus, agent, text, **k: said.append((agent, text)) or True)
    monkeypatch.setattr("jarvis.notify.notify_owner", lambda *a, **k: ["ok"])
    now = datetime.now(settings.tz).replace(hour=14, minute=0, second=0, microsecond=0)
    st.add_task("Submit IS111 assignment", due=(now + timedelta(days=2, hours=3)).isoformat(timespec="minutes"))
    assert len(autopilot.deadline_nudges(st, BUS, now)) == 1 and said[0][0] == "ATHENA"
    assert autopilot.deadline_nudges(st, BUS, now) == []                          # once per stage
    assert "tomorrow" in autopilot.deadline_nudges(st, BUS, now + timedelta(days=1, hours=6))[0]


def test_laptop_health_has_a_shape():
    out = autopilot.laptop_health()
    assert {"issues", "info", "checked"} <= set(out)


def test_steam_wishlist_sales(monkeypatch):
    st = Store(":memory:")
    st.set("deals:steam_id", "76561198000000000")
    pages = {"IWishlistService": {"response": {"items": [{"appid": 1245620}, {"appid": 570}]}},
             "filters=basic": {"1245620": {"data": {"name": "ELDEN RING"}}},
             "filters=price_overview": {"1245620": {"success": True, "data": {"price_overview": {"final": 3490, "initial": 6990, "discount_percent": 50}}},
                                        "570": {"success": True, "data": []}}}
    monkeypatch.setattr(deals, "_get", lambda url, timeout=20: json.dumps(next(v for k, v in pages.items() if k in url)).encode())
    out = deals.steam_sync(st)
    assert out["wishlist"] == 2 and out["deals"][0]["name"] == "ELDEN RING" and out["deals"][0]["price"] == 34.9
    assert deals.steam_sync(st)["deals"] == []                                   # told once per sale


def test_the_team_has_its_new_daily_jobs():
    from jarvis.engine import Engine
    from jarvis.bus import Bus
    from jarvis.scheduler import Scheduler
    st = Store(":memory:")
    sc = Scheduler(Engine(st, Bus(st), settings))
    names = {j.name for j in sc.jobs}
    assert {"afternoon_checkin", "evening_checkin", "intel", "career_weekly"} <= names
    assert {"held_flush", "deadline_nudges", "laptop_health", "steam_deals"} <= set(Scheduler.MAINTENANCE)
    assert settings.quiet_hours.startswith("02:00") or settings.quiet_hours   # quiet while the owner sleeps
