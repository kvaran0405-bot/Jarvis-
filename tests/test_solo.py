"""Solo JARVIS: the phone's pack (what it needs to work alone) and merging back what it did while apart."""
import json
from datetime import datetime, timedelta

from jarvis import solo
from jarvis.config import ROOT, settings


def test_pack_has_what_the_phone_needs(monkeypatch):
    from jarvis import server
    st = server.store
    st.remember("Sir's gym is at Tampines Hub")
    st.add_task("Solo test task")
    soon = (datetime.now(settings.tz) + timedelta(hours=5)).isoformat(timespec="seconds")
    st.add_event("Solo test dinner", soon, location="Jewel")
    st.queue_message("telegram", "", "⏰ Reminder: solo test pill", "JARVIS", reason="reminder", status="approved", send_at=soon)
    st.set("places:saved", json.dumps({"home": [1.353, 103.944]}))
    p = solo.pack(st)
    assert "Sir's gym is at Tampines Hub" in p["memories"]
    assert any(t["title"] == "Solo test task" for t in p["tasks"])
    assert any(e["title"] == "Solo test dinner" and e["location"] == "Jewel" for e in p["events"])
    assert any(r["text"] == "solo test pill" for r in p["reminders"])
    assert p["places"]["home"] == [1.353, 103.944] and any(t["name"] == "JARVIS" for t in p["team"])
    json.dumps(p)   # goes over the wire as JSON


def test_keys_only_when_set(monkeypatch):
    monkeypatch.setattr(settings, "gemini_key", "AQ.test-key-1234567890123")
    monkeypatch.delenv("JARVIS_LTA_KEY", raising=False)
    monkeypatch.delenv("JARVIS_ONEMAP_EMAIL", raising=False)
    k = solo.keys()
    assert k["gemini"] == "AQ.test-key-1234567890123" and k["lta"] == "" and k["onemap_email"] == ""


def test_merge_applies_once():
    from jarvis import server
    st = server.store
    import uuid
    soon_ms = (datetime.now().timestamp() + 3600) * 1000
    run = uuid.uuid4().hex[:8]
    items = [{"uid": "m1" + run, "kind": "remember", "fact": "Sir likes kopi siew dai"},
             {"uid": "t1" + run, "kind": "task", "title": "Buy charger (from phone)"},
             {"uid": "e1" + run, "kind": "event", "title": "Phone-made lunch", "start": "2030-01-02T12:00:00+08:00"},
             {"uid": "n1" + run, "kind": "note", "title": "Idea", "body": "Shaabaz reels in Tamil"},
             {"uid": "r1" + run, "kind": "reminder", "text": "call Mum " + run, "at_ms": soon_ms},
             {"uid": "c1" + run, "kind": "chat", "who": "you", "text": "how do I get to Jewel"},
             {"uid": "x1" + run, "kind": "nonsense"}]
    out = server.phone_solo_sync(server.SoloSync(items=items))["merged"]
    assert out == {"remember": 1, "task": 1, "event": 1, "note": 1, "reminder": 1, "chat": 1}
    assert any(m["fact"] == "Sir likes kopi siew dai" for m in st.memories(200))
    assert any(t["title"] == "Buy charger (from phone)" for t in st.list_tasks("open", limit=500))
    # the phone owns its reminders: logged on the laptop, never queued to ring a second time
    assert not st.query("SELECT id FROM outbox WHERE body LIKE ?", (f'%call Mum {run}%',))
    assert server.phone_solo_sync(server.SoloSync(items=items))["merged"] == {}   # a retried upload changes nothing


def test_endpoints_and_page():
    from jarvis import server
    out = server.phone_solo()
    assert "pack" in out and "keys" in out
    page = (ROOT / "android/app/src/main/assets/solo.html").read_text()
    assert "SOLO-JARVIS" in page   # the app only accepts a downloaded page carrying this marker
    assert str(server.solo_page().path).endswith("solo.html")
