"""Instant answers: everyday questions answered from JARVIS's own data in a blink, without the AI."""
import asyncio
import json
import time
from datetime import datetime, timedelta

from jarvis import quick
from jarvis.config import settings


def test_matches_only_simple_questions():
    from jarvis import server
    st = server.store
    for q in ["what time is it", "Jarvis, what's the time?", "time pls", "what's next", "my tasks", "how many steps today",
              "where am I", "phone battery", "hi jarvis", "thanks lah", "what day is it today"]:
        assert quick.answer(st, q), q
    for q in ["what time should I leave for Jewel", "remind me about my tasks at 5", "thanks, now send it to Mum",
              "where am I going tomorrow", "how many steps did I do last week compared to this week"]:
        assert quick.answer(st, q) is None, q


def test_uses_real_data():
    from jarvis import server
    st = server.store
    now = datetime.now(settings.tz)
    st.set(f"steps:{now.date().isoformat()}", "9123")
    assert "9,123" in quick.answer(st, "how many steps")
    st.set("phone:state", json.dumps({"at": now.isoformat(), "battery": 18, "charging": False}))
    assert "18%" in quick.answer(st, "phone battery") and "charger" in quick.answer(st, "phone battery")
    soon = (now + timedelta(minutes=50)).replace(second=0, microsecond=0)
    if soon.date() == now.date():
        st.add_event("Quick test gym", soon.isoformat(timespec="seconds"), location="Tampines Hub")
        r = quick.answer(st, "what's next")
        assert "Tampines Hub" in r or "Next up" in r


def test_fast_through_the_command_path(monkeypatch):
    from jarvis import server
    called = []
    monkeypatch.setattr(server.engine, "run", lambda *a, **k: called.append(1) or "brain")
    t0 = time.time()
    out = asyncio.run(server.command(server.Command(text="what time is it", voice=True, rid="q1")))
    assert out["agent"] == "JARVIS" and ":" in out["reply"] and not called and time.time() - t0 < 1
    assert server.handle_owner_message("thanks jarvis", "Telegram") and not called
