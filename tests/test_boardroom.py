"""The boardroom: the team's daily briefing, once a day, when the boss first opens JARVIS (noon is fine)."""
from datetime import datetime, timedelta

from jarvis import boardroom
from jarvis.config import ROOT, settings
from jarvis.store import Store


def test_everyone_with_news_reports_in(monkeypatch):
    monkeypatch.setattr(boardroom, "weather_line", lambda: "Today's sunny, 26 to 32 degrees.")
    st = Store(":memory:")
    now = datetime.now(settings.tz).replace(hour=12, minute=5)
    y = (now.date() - timedelta(days=1)).isoformat()
    st.log_transaction(y, -31, "food", "GRAB*FOOD · DBS (alert)")
    st.log_transaction(y, -17, "transport", "GRAB · DBS (alert)")
    from jarvis import jobs
    jobs.add_job(st, {"source": "MCF", "title": "Marketing Executive", "company": "ACME", "url": "u"})
    st.execute("UPDATE jobs SET fit = 86")
    b = boardroom.briefing(st, now)
    who = [l["agent"] for l in b["lines"]]
    assert who[0] == "JARVIS" and "Good afternoon" in b["lines"][0]["text"] and "sunny" in b["lines"][0]["text"]
    assert "VERONICA" in who and "ZEUS" in who and who[-1] == "JARVIS"
    v = next(l["text"] for l in b["lines"] if l["agent"] == "VERONICA")
    assert "$48" in v and "food" in v and "Month so far" in v
    assert "86%" in next(l["text"] for l in b["lines"] if l["agent"] == "ZEUS")


def test_only_once_a_day_and_telegram_by_1pm(monkeypatch):
    monkeypatch.setattr(boardroom, "weather_line", lambda: "")
    st = Store(":memory:")
    now = datetime.now(settings.tz).replace(hour=12)
    assert boardroom.first_open(st, now)["new"] is True
    assert boardroom.first_open(st, now + timedelta(minutes=5))["new"] is False      # the other screen doesn't repeat it
    assert boardroom.first_open(st, now + timedelta(days=1))["new"] is True
    sent = []
    import jarvis.notify as notify
    monkeypatch.setattr(notify, "notify_owner", lambda title, body, **k: sent.append(body))
    boardroom.fallback(Store(":memory:"), None)
    assert sent and "JARVIS:" in sent[0]


def test_screens_play_it():
    for page in ("web/home.html", "web/command-centre.html", "android/app/src/main/assets/solo.html"):
        assert "JarvisBriefing" in (ROOT / page).read_text(encoding="utf-8"), page
    assert "briefing.js" in (ROOT / "android/app/build.gradle").read_text(encoding="utf-8")
