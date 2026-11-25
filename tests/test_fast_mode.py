"""Fast mode: checks Gemini before switching on, covers every reply, falls back to the main brain."""
from jarvis import brain
from jarvis.config import settings


def test_fast_mode_needs_a_working_key(monkeypatch):
    from jarvis import server
    monkeypatch.setattr(brain, "gemini_check", lambda: (False, 0.0, "Google says the key isn't valid"))
    msg = server.special("fast mode on")[0]
    assert "can't switch on" in msg and "/gemini" in msg and server.store.get("voice:fast") != "on"
    monkeypatch.setattr(brain, "gemini_check", lambda: (True, 0.8, ""))
    assert "0.8 seconds" in server.special("fast mode on")[0] and server.store.get("voice:fast") == "on"
    assert "off" in server.special("fast mode off")[0] and server.store.get("voice:fast") == "off"


def test_fast_mode_falls_back(monkeypatch):
    from jarvis import server
    eng = server.engine
    monkeypatch.setattr(settings, "gemini_key", "AQ.test-key-1234567890123")
    monkeypatch.setattr(brain, "pick", lambda *a, **k: "pro")
    monkeypatch.setattr(brain, "fast_voice", lambda store: True)
    used = []

    def think(which, agent, prompt, *a, **k):
        used.append(which)
        if which == "gemini":
            raise RuntimeError("Gemini error 503")
        return "answer from " + which
    monkeypatch.setattr(eng, "_think", think)
    assert eng.run("JARVIS", "hi", chat=True) == "answer from pro" and used == ["gemini", "pro"]
    used.clear()
    eng.run("JARVIS", "night job", background=True)
    assert used == ["pro"]                       # scheduled work never uses fast mode


def test_telegram_gemini_setup(monkeypatch):
    from jarvis import telegram
    out, calls, got = [], [], []
    bot = telegram.Bot(on_text=lambda t, voice=False: "AI", on_decision=lambda *a: "", log=lambda m: None)
    bot.on_gemini = lambda k: got.append(k) or "connected"
    monkeypatch.setattr(telegram, "chat_id", lambda: "42")
    monkeypatch.setattr(telegram, "send", lambda text, *a, **k: out.append(text))
    monkeypatch.setattr(telegram, "api", lambda method, **p: calls.append((method, p)))
    msg = lambda t, i=1: {"update_id": i, "message": {"message_id": i, "text": t, "chat": {"id": 42}}}
    bot.handle(msg("/gemini"))
    assert "aistudio.google.com/apikey" in out[-1]
    bot.handle(msg("here it is AQ.Example-testtesttesttest_xyz", 5))
    assert got == ["AQ.Example-testtesttesttest_xyz"] and ("deleteMessage", {"chat_id": "42", "message_id": 5}) in calls


def test_gemini_check_tries_other_free_models(monkeypatch):
    from jarvis import brains, access
    monkeypatch.setattr(settings, "gemini_key", "AQ.test-key-1234567890123")
    monkeypatch.setattr(settings, "gemini_model", "gemini-flash-latest")
    saved = {}
    monkeypatch.setattr(access, "_write_env", lambda v: saved.update(v))
    tried = []

    def call(body, model=None):
        tried.append(model)
        if model in ("gemini-flash-latest", "gemini-2.5-flash"):
            raise brains.LimitReached("Gemini free limit reached: limit: 0")
        return {"candidates": [{"content": {"parts": [{"text": "OK"}]}}]}
    monkeypatch.setattr(brains, "_gemini_call", call)
    ok, _secs, why = brain.gemini_check()
    assert ok and tried[:3] == ["gemini-flash-latest", "gemini-2.5-flash", "gemini-2.5-flash-lite"]
    assert saved == {"JARVIS_GEMINI_MODEL": "gemini-2.5-flash-lite"} and settings.gemini_model == "gemini-2.5-flash-lite"
    monkeypatch.setattr(brains, "_gemini_call", lambda body, model=None: (_ for _ in ()).throw(brains.LimitReached("x")))
    assert brain.gemini_check() == (False, 0.0, brain.LIMITED)   # a valid key with no allowance left right now
