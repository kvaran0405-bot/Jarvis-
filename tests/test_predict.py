"""Predictive JARVIS: learns routines from where you've been and nudges you before your usual trips."""
import json
from datetime import datetime, timedelta

from jarvis import predict
from jarvis.config import settings

HOME, GYM = (1.3530, 103.9440), (1.3600, 103.9800)


def _seed(store, now):
    from jarvis import explore
    explore._ensure_locs(store)
    store.execute("DELETE FROM locs")
    store.set("places:saved", json.dumps({"home": list(HOME), "gym": list(GYM)}))
    for weeks in range(1, 4):                       # three Tuesdays: leave home ~18:10, reach the gym ~18:30
        day = now - timedelta(weeks=weeks)
        day = day - timedelta(days=(day.weekday() - 1) % 7)   # that week's Tuesday
        t = lambda h, m: day.replace(hour=h, minute=m, second=0, microsecond=0).timestamp()  # noqa: E731
        pts = [(t(17, 0), *HOME), (t(18, 8 + weeks), 1.3555, 103.9600), (t(18, 30), *GYM), (t(19, 40), *GYM), (t(20, 5), *HOME)]
        for ts, lat, lon in pts:
            store.execute("INSERT OR REPLACE INTO locs (ts, lat, lon, acc, speed) VALUES (?,?,?,?,?)", (ts, lat, lon, 10, 0))


def test_learns_a_weekly_habit():
    from jarvis import server
    now = datetime.now(settings.tz)
    _seed(server.store, now)
    rs = predict.learn(server.store)
    gym = [r for r in rs if r["from"] == "home" and r["to"] == "gym"]
    assert gym and gym[0]["days"] == [1] and gym[0]["at"].startswith("18:1"), rs
    assert predict.describe_days([0, 1, 2, 3, 4]) == "weekdays" and predict.describe_days([1]) == "Tuesdays"


def test_nudges_once_before_the_trip(monkeypatch):
    from jarvis import server, phonelink
    st = server.store
    st.set("predict:routines", json.dumps([{"from": "home", "to": "gym", "days": [1], "at": "18:10", "times": 3}]))
    st.set("phone:place", "home")
    st.set("predict:on", "on")
    tue = datetime.now(settings.tz)
    tue = (tue + timedelta(days=(1 - tue.weekday()) % 7)).replace(hour=17, minute=55, second=0, microsecond=0)
    for k in [k for k in [f"predict:sent:{tue.date()}:home>gym"]]:
        st.set(k, "")
    monkeypatch.setattr(predict, "nudge_text", lambda store, r: "You usually head to gym around 18:10 on Tuesdays, Sir.")
    import jarvis.speech as sp
    monkeypatch.setattr(sp, "in_quiet_hours", lambda now=None: False)
    sent = []
    monkeypatch.setattr(phonelink, "queue", lambda store, kind, **k: sent.append(k))
    assert predict.check(st, server.bus, tue) and sent
    assert predict.check(st, server.bus, tue + timedelta(minutes=5)) == []        # once a day
    st.set("phone:place", "smu")
    assert predict.due(st, tue + timedelta(days=7)) == []                         # not from where you are


def test_off_switch():
    from jarvis import server
    assert "off" in server.special(server.natural("routine nudges off"))[0]
    assert server.store.get("predict:on") == "off"
    server.special("routine nudges on")
