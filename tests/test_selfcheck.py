"""Nightly self-check: tests JARVIS, fixes what it can, and only messages the owner when something needs them."""
import json
from datetime import datetime, timedelta

from jarvis import selfcheck
from jarvis.config import settings


def test_reports_and_flags_phone_silence(monkeypatch):
    from jarvis import server
    st = server.store
    old = (datetime.now(settings.tz) - timedelta(hours=20)).isoformat()
    st.set("phone:state", json.dumps({"at": old}))
    r = selfcheck.run(st, live=False)
    names = {c["name"]: c for c in r["checks"]}
    assert names["Memory"]["status"] == "ok"
    assert names["Phone link"]["status"] == "needs_you" and "Tailscale" in names["Phone link"]["detail"]
    assert "⚠ Phone link" in r["summary"]
    st.set("phone:state", json.dumps({"at": datetime.now(settings.tz).isoformat()}))
    st.set("solo:last_pack", datetime.now(settings.tz).isoformat())
    names = {c["name"]: c for c in selfcheck.run(st, live=False)["checks"]}
    assert names["Phone link"]["status"] == "ok" and names["Phone's offline brain"]["status"] == "ok"


def test_quiet_unless_needed(monkeypatch):
    from jarvis import server, telegram
    sent = []
    monkeypatch.setattr(telegram, "send", lambda t, *a, **k: sent.append(t))
    monkeypatch.setattr(selfcheck, "run", lambda store, bus=None, live=True: {"checks": [{"name": "x", "status": "ok"}], "summary": "fine"})
    selfcheck.nightly(server.store, server.bus)
    assert not sent
    monkeypatch.setattr(selfcheck, "run", lambda store, bus=None, live=True: {"checks": [{"name": "x", "status": "needs_you"}], "summary": "⚠ x"})
    selfcheck.nightly(server.store, server.bus)
    assert sent == ["⚠ x"]


def test_voice_phrase_and_job(monkeypatch):
    from jarvis import server
    from jarvis.scheduler import Scheduler
    assert "self_check" in Scheduler.MAINTENANCE
    monkeypatch.setattr(selfcheck, "run", lambda store, bus=None, live=True: {"summary": "🩺 Self-check: 9/9 OK."})
    assert server.special(server.natural("Jarvis, run a system check"))[0].startswith("🩺")
