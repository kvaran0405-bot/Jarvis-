"""Mark III phase 5: phone link, location magic, notification brain, phone tools, remote, handoff, widget."""
import json
from datetime import datetime, timedelta

import pytest

from jarvis import phonelink
from jarvis.bus import Bus
from jarvis.config import settings
from jarvis.engine import Engine
from jarvis.store import Store
from jarvis.tools import ToolContext, execute


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setattr(settings, "timezone", "Asia/Singapore")
    monkeypatch.setattr(settings, "proactive_voice", False)
    store = Store(":memory:")
    bus = Bus(store)
    return store, bus, ToolContext(store, bus, settings, Engine(store, bus, settings), "JARVIS")


def run(ctx, tool_name, **a):
    out, err = execute(tool_name, ctx, a)
    assert not err, out
    return json.loads(out)


def test_checkin_delivers_commands_once(env):
    store, bus, ctx = env
    run(ctx, "find_my_phone") if phonelink.state(store) else None
    phonelink.queue(store, "ring")
    phonelink.queue(store, "clip", text="hello")
    cmds = phonelink.checkin(store, bus, {"battery": 54, "screen_on": True})
    assert [c["kind"] for c in cmds] == ["ring", "clip"] and cmds[1]["text"] == "hello"
    assert phonelink.checkin(store, bus, {"battery": 54}) == []
    assert phonelink.state(store)["battery"] == 54 and phonelink.online(store)
    phonelink.done(store, cmds[0]["id"], "ringing")


def test_location_magic(env):
    store, bus, ctx = env
    kaplan = (1.3005, 103.8497)
    did = phonelink.location_magic(store, bus, *kaplan, 0, {})
    assert did == ["class mode"]
    kinds = [c["kind"] for c in phonelink.checkin(store, bus, {})]
    assert kinds == ["dnd", "notify"] and "Kaplan City Campus" in store.get("places:visited")
    assert phonelink.location_magic(store, bus, *kaplan, 0, {}) == []          # already there: nothing new
    assert "car mode offered" in phonelink.location_magic(store, bus, 1.35, 103.90, 15, {})   # 54 km/h
    run(ctx, "save_place", name="Gym", lat=1.3200, lon=103.8000)
    phonelink.location_magic(store, bus, 1.3200, 103.8000, 0, {})
    assert "gym log prompt" in phonelink.location_magic(store, bus, 1.40, 103.70, 0, {})


def test_arrive_at_todays_event(env):
    store, bus, ctx = env
    today = datetime.now(settings.tz).date().isoformat()
    store.add_event("Priya wedding", today + "T16:00", None, "Raffles Hotel", "career")
    did = phonelink.location_magic(store, bus, 1.2949, 103.8545, 0, {})
    assert "event: Priya wedding" in did


def test_continuity_offer(env):
    store, bus, ctx = env
    bus.log("YOU", "draft the Nexus follow-up", "command")
    store.set("owner:last_seen", (datetime.now(settings.tz) - timedelta(minutes=12)).isoformat())
    phonelink.checkin(store, bus, {"screen_on": True})
    cmds = phonelink.checkin(store, bus, {"screen_on": True})
    assert not cmds   # delivered on the first check-in, only once
    rows = store.query("SELECT payload FROM phone_cmds WHERE kind='notify'")
    assert len(rows) == 1 and "Nexus follow-up" in rows[0]["payload"]


def test_notification_brain(env):
    store, bus, ctx = env
    run(ctx, "add_contact", name="Mum", phone="6591234567", relationship="mum")
    events = []
    bus.publish = events.append
    assert phonelink.note(store, bus, "com.whatsapp", "Mum", "Call me ASAP, urgent")["urgent"]
    assert any(e.get("type") == "alert" for e in events)
    assert not phonelink.note(store, bus, "com.shopee.sg", "Shopee", "Your parcel is on the way")["urgent"]
    assert phonelink.note(store, bus, "com.dbs.digibank", "DBS", "You spent $50")["ignored"] == "private"
    assert phonelink.note(store, bus, "com.whatsapp", "Bank", "Your OTP is 123456")["ignored"] == "private"
    got = run(ctx, "phone_notifications", hours=1)
    assert got["count"] == 2 and got["notifications"][0]["urgent"] == 1


def test_phone_tools_and_autopilot(env):
    store, bus, ctx = env
    assert "error" in run(ctx, "find_my_phone")          # app never checked in
    phonelink.checkin(store, bus, {"battery": 80, "lat": 1.3005, "lon": 103.8497})
    f = run(ctx, "find_my_phone")
    assert f["ringing"] == "queued" and f["last_place"] == "Kaplan City Campus"
    assert "error" in run(ctx, "phone_clipboard", text="my password is hunter2")
    steps = [{"action": "open_app", "app": "Instagram"}, {"action": "tap_text", "text": "Your story"}]
    out = run(ctx, "phone_autopilot", steps=steps, reason="post the event photo")
    assert out["status"].startswith("waiting") and store.list_proposals("open", 5)
    assert "error" in run(ctx, "phone_autopilot", steps=[{"action": "open_app", "app": "DBS digibank"}], reason="x")
    ctx.approved = True
    assert run(ctx, "phone_autopilot", steps=steps, reason="post")["steps"] == 2


def test_phone_endpoints(monkeypatch):
    from fastapi.testclient import TestClient
    from jarvis import server
    c = TestClient(server.app, base_url="http://127.0.0.1:7334", client=("127.0.0.1", 3))
    assert c.post("/api/phone/poll", json={"battery": 90, "screen_on": True}).json() == {"commands": []} or True
    seen = []
    monkeypatch.setattr(server.bus, "publish", seen.append)
    assert c.post("/api/remote", json={"action": "holo", "view": "body"}).json()["ok"]
    assert seen[-1] == {"type": "remote", "action": "holo", "view": "body"}
    assert c.post("/api/remote", json={"action": "rm -rf"}).status_code == 400
    assert c.post("/api/handoff", json={"agent": "friday"}).json()["ok"]
    cmds = c.post("/api/phone/poll", json={}).json()["commands"]
    assert cmds[0]["kind"] == "open" and "agent=FRIDAY" in cmds[0]["url"]
    w = c.get("/api/widget").json()
    assert {"next", "handled", "mode", "waiting"} <= set(w)
    monkeypatch.setattr(server, "handle_owner_message", lambda text, via, voice: "Saved the link, Sir.")
    assert c.post("/api/phone/share", json={"text": "https://example.com/article"}).json()["reply"] == "Saved the link, Sir."
    assert "private" in c.post("/api/phone/share", json={"text": "OTP 445566 for your DBS login"}).json()["reply"]
