"""When one free Gemini model's allowance runs out, the next one answers; when all do, JARVIS stops trying for a while."""
import io
import urllib.error

import pytest

from jarvis import brains


def _err(code, msg=""):
    return urllib.error.HTTPError("u", code, "x", {}, io.BytesIO(msg.encode()))


def test_next_model_answers(monkeypatch):
    brains._gem_spent.clear()
    tried = []

    def once(body, model):
        tried.append(model)
        if len(tried) == 1:
            raise _err(429, "GenerateRequestsPerDayPerProjectPerModel-FreeTier")
        return {"ok": model}
    monkeypatch.setattr(brains, "_gemini_once", once)
    assert brains._gemini_call({})["ok"] == tried[1] and tried[0] != tried[1]
    assert brains._gem_spent[tried[0]] > 0


def test_all_used_up_then_resting(monkeypatch):
    brains._gem_spent.clear()
    monkeypatch.setattr(brains, "_gemini_once", lambda b, m: (_ for _ in ()).throw(_err(429, "PerDay")))
    with pytest.raises(brains.LimitReached):
        brains._gemini_call({})
    assert brains.gemini_resting()
    brains._gem_spent.clear()
