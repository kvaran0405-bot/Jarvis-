"""Brain choice, the pause switch, limit fallback and the Gemini loop - all offline."""
import json

import pytest

from jarvis import brain, brains
from jarvis.bus import Bus
from jarvis.config import settings
from jarvis.engine import Engine
from jarvis.store import Store


@pytest.fixture
def eng(monkeypatch):
    store = Store(":memory:")
    monkeypatch.setattr(settings, "brain", "auto")
    monkeypatch.setattr(settings, "automation_brain", "auto")
    return Engine(store, Bus(store), settings)


def test_pause_resume_saver_phrases(eng, monkeypatch):
    s = eng.store
    monkeypatch.setattr(brain, "ready", lambda b: b in ("pro", "gemini"))
    assert brain.pick(s) == "pro" and brain.pick(s, background=True) == "gemini"  # routines spare your plan
    assert "Paused until" in brain.handle_control(s, "Jarvis, pause for 2 hours")
    assert brain.pick(s) is None and brain.pick(s, background=True) is None
    assert "I'm paused" in eng.run("JARVIS", "hello")
    assert "Saver mode" in brain.handle_control(s, "save my claude")
    assert brain.pick(s) == "gemini"
    assert "Back online" in brain.handle_control(s, "resume")
    assert brain.pick(s) == "pro"
    for not_control in ("pause my spotify playlist", "what's my status on the essay", "remind me to resume work"):
        assert brain.handle_control(s, not_control) is None
    assert brain.handle_control(s, "/pause 30m") and brain.get_mode(s)["until"]


def test_pause_expires(eng):
    brain.set_mode(eng.store, "paused", hours=-1)  # already in the past
    assert brain.get_mode(eng.store)["mode"] == "on"


def test_pro_limit_falls_back_to_gemini(eng, monkeypatch):
    monkeypatch.setattr(brain, "ready", lambda b: b in ("pro", "gemini"))
    used = []

    def fake_think(which, *a, **k):
        used.append(which)
        if which == "pro":
            raise brains.LimitReached("Claude usage limit reached")
        return "answer from gemini"
    monkeypatch.setattr(eng, "_think", fake_think)
    assert eng.run("JARVIS", "hi") == "answer from gemini"
    assert used == ["pro", "gemini"] and brain.pro_limited(eng.store)
    assert brain.pick(eng.store) == "gemini"  # stays on the backup until the limit window passes


def test_gemini_tool_loop(eng, monkeypatch):
    monkeypatch.setattr(settings, "gemini_key", "g")
    sent = []
    replies = iter([
        {"candidates": [{"content": {"role": "model", "parts": [
            {"functionCall": {"name": "add_task", "args": {"title": "Read chapter 4", "area": "academic"}},
             "thoughtSignature": "sig123"}]}}]},
        {"candidates": [{"content": {"role": "model", "parts": [{"text": "Added it, Sir."}]}}]},
    ])
    monkeypatch.setattr(brains, "_gemini_call", lambda body: sent.append(json.loads(json.dumps(body))) or next(replies))
    monkeypatch.setattr(brain, "ready", lambda b: b == "gemini")
    out = eng.run("ATHENA", "add reading chapter 4", chat=True)
    assert out == "Added it, Sir."
    assert eng.store.list_tasks()[0]["title"] == "Read chapter 4"
    second = sent[1]["contents"]
    assert second[1]["parts"][0]["thoughtSignature"] == "sig123"          # model turn sent back verbatim
    assert second[2]["parts"][0]["functionResponse"]["name"] == "add_task"
    decls = sent[0]["tools"][0]["functionDeclarations"]
    assert all("parameters" not in d or d["parameters"]["type"] == "object" for d in decls)
