"""Phone powers: the tools queue the right commands, wait for results, and keep finance off limits."""
import json
import threading
import time

import pytest

from jarvis import phonelink
from jarvis.bus import Bus
from jarvis.config import settings
from jarvis.store import Store
from jarvis.tools import REGISTRY, ToolContext


@pytest.fixture
def ctx():
    s = Store(":memory:")
    phonelink.checkin(s, Bus(s), {"battery": 80})
    return ToolContext(s, Bus(s), settings, None, "JARVIS")


def answer(store, result, delay=0.3):
    """Act like the phone: pick up the next command and report a result."""
    def go():
        time.sleep(delay)
        for c in phonelink.checkin(store, Bus(store), {}):
            phonelink.done(store, c["id"], result if isinstance(result, str) else json.dumps(result))
    threading.Thread(target=go, daemon=True).start()


def last_cmd(store):
    r = store.query("SELECT kind, payload FROM phone_cmds ORDER BY id DESC LIMIT 1")[0]
    return r["kind"], json.loads(r["payload"])


def test_call_and_contacts(ctx):
    answer(ctx.store, "calling Mum")
    assert REGISTRY["phone_call"].fn(ctx, name="Mum")["result"] == "calling Mum"
    answer(ctx.store, [{"name": "Mum", "number": "+65 9123 4567"}])
    assert REGISTRY["phone_contacts"].fn(ctx, name="mum")["result"][0]["name"] == "Mum"


def test_alarm_timer_music(ctx):
    assert "error" in REGISTRY["phone_alarm"].fn(ctx, time="25:00")
    answer(ctx.store, "alarm set for 06:30")
    REGISTRY["phone_alarm"].fn(ctx, time="6:30", label="Gym")
    assert last_cmd(ctx.store) == ("alarm", {"hour": 6, "minute": 30, "label": "Gym"})
    answer(ctx.store, "ok")
    REGISTRY["phone_timer"].fn(ctx, minutes=10)
    assert last_cmd(ctx.store)[1]["seconds"] == 600
    answer(ctx.store, "playing")
    REGISTRY["phone_music"].fn(ctx, query="Coldplay Yellow", app="Spotify")
    assert last_cmd(ctx.store) == ("play", {"query": "Coldplay Yellow", "app": "spotify"})


def test_shopping_youtube_and_finance_block(ctx):
    answer(ctx.store, "opened")
    REGISTRY["phone_shop"].fn(ctx, store="Shopee", query="black sneakers")
    assert last_cmd(ctx.store)[1]["url"] == "https://shopee.sg/search?keyword=black+sneakers"
    answer(ctx.store, "opened")
    REGISTRY["phone_shop"].fn(ctx, store="shein", query="summer dress")
    assert last_cmd(ctx.store)[1]["url"] == "https://sg.shein.com/pdsearch/summer%20dress/"
    answer(ctx.store, "opened")
    REGISTRY["phone_youtube"].fn(ctx, query="lofi study")
    assert "youtube.com/results?search_query=lofi+study" in last_cmd(ctx.store)[1]["url"]
    n = ctx.store.query("SELECT COUNT(*) AS n FROM phone_cmds")[0]["n"]
    assert "error" in REGISTRY["phone_open"].fn(ctx, app="DBS PayLah")
    assert ctx.store.query("SELECT COUNT(*) AS n FROM phone_cmds")[0]["n"] == n


def test_open_camera_and_queue_when_asleep(ctx):
    phonelink.wait_result = lambda store, cid, seconds=25: None    # phone asleep
    try:
        out = REGISTRY["phone_open"].fn(ctx, app="Camera")
        assert out["queued"] and last_cmd(ctx.store)[0] == "camera"
    finally:
        import importlib
        importlib.reload(phonelink)


def test_screen_reading_drops_secrets(ctx):
    answer(ctx.store, {"app": "com.whatsapp", "text": "Pin chat\nYour OTP is 123456\nDinner at 8?\nCard 4111 1111 1111 1234"})
    res = REGISTRY["phone_screen"].fn(ctx)["result"]
    assert "OTP" not in res["text"] and "Dinner at 8?" in res["text"] and "1234" in res["text"] and "4111 1111" not in res["text"]


def test_photo_route(tmp_path, monkeypatch):
    import base64
    from fastapi.testclient import TestClient
    from jarvis import server
    from jarvis import config
    monkeypatch.setattr(config, "ROOT", tmp_path)
    c = TestClient(server.app, base_url="http://127.0.0.1:7334", client=("127.0.0.1", 5))
    r = c.post("/api/phone/photo", json={"name": "IMG_1.jpg", "image": "data:image/jpeg;base64," + base64.b64encode(b"jpg").decode()})
    assert r.json()["path"].endswith("-IMG_1.jpg") and r.json()["path"].startswith(str(tmp_path))


def test_link_watch_warns_once():
    import json as _json
    from datetime import datetime as _dt, timedelta as _td
    s = Store(":memory:")
    t0 = _dt.now(settings.tz)
    s.set("phone:state", _json.dumps({"at": (t0 - _td(hours=3)).isoformat()}))
    sent = []
    assert "Tailscale" in phonelink.link_watch(s, t0, sent.append) and len(sent) == 1
    assert phonelink.link_watch(s, t0 + _td(hours=1), sent.append) is None and len(sent) == 1   # only once
    s.set("phone:state", _json.dumps({"at": t0.isoformat()}))
    assert phonelink.link_watch(s, t0, sent.append) is None                                    # back online
    assert phonelink.link_watch(Store(":memory:"), t0, sent.append) is None                    # never linked: quiet
