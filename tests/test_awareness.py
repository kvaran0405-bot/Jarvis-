"""Live awareness: agents know where the owner is and has been, without being told."""
import json
from datetime import datetime, timedelta

from jarvis import awareness, explore, phonelink
from jarvis.bus import Bus
from jarvis.config import settings
from jarvis.store import Store


def test_situation_and_time_at_places(monkeypatch):
    s = Store(":memory:")
    s.set("places:saved", json.dumps({"gym": [1.3400, 103.8500], "home": [1.3496, 103.9568]}))
    now = datetime.now(settings.tz)
    start = now.replace(hour=0, minute=5).timestamp()
    pts = [[start + i * 600, 1.3400, 103.8500, 10, 0] for i in range(6)]          # an hour at the gym
    pts += [[start + 3600 + 1800 + i * 600, 1.3496, 103.9568, 10, 0] for i in range(4)]   # then home
    phonelink.checkin(s, Bus(s), {"battery": 64, "charging": False, "lat": 1.3496, "lon": 103.9568, "speed": 0,
                                  "points": pts})
    hours = awareness.time_at_places(s, 7)
    assert hours["gym"] >= 0.8 and "home" in hours
    awareness._cache["at"] = 0
    txt = awareness.situation(s)
    assert "Phone location: home" in txt and "battery 64%" in txt and "gym → " in txt and "don't ask" in txt
    cid = phonelink.queue(s, "screentime")
    phonelink.done(s, cid, json.dumps({"total_minutes": 185, "apps": [{"app": "TikTok", "minutes": 95}]}))
    awareness._cache["at"] = 0
    assert "3h05m; top: TikTok 95m" in awareness.situation(s)


def test_context_block_includes_awareness(monkeypatch):
    from jarvis import server
    monkeypatch.setattr(awareness, "situation", lambda store: "Live situation (gathered automatically): TEST\n")
    assert "Live situation" in server.engine._context_block(server.AGENTS["JARVIS"])
    assert server.engine._context_block(server.AGENTS["GUEST"]) == ""    # visitors never see it
