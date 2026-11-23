"""One-word updates: version, after-boot report, new phone app notice, Telegram 'update'."""
from jarvis import updater
from jarvis.store import Store


def test_after_boot_reports(monkeypatch):
    s, sent = Store(":memory:"), []
    monkeypatch.setattr(updater, "app_version", lambda: "app1")
    assert updater.after_boot(s, sent.append) == []            # a normal start says nothing
    updater.mark_started(s)
    assert "already on the newest" in updater.after_boot(s, sent.append)[0]
    s.set("update:pending", "old")
    monkeypatch.setattr(updater, "latest_change", lambda: "Remove edge glow")
    monkeypatch.setattr(updater, "app_version", lambda: "app2")
    msgs = updater.after_boot(s, sent.append)
    assert "Updated" in msgs[0] and "Remove edge glow" in msgs[0] and "/installapp" in msgs[1]
    assert updater.after_boot(s, sent.append) == [] and len(sent) == 3


def test_version_is_stable():
    assert updater.version() == updater.version() and len(updater.version()) == 12


def test_telegram_update_words(monkeypatch):
    from jarvis import telegram
    bot = telegram.Bot(on_text=lambda t, voice=False: "AI:" + t, on_decision=lambda *a: "", log=lambda m: None)
    calls, out = [], []
    bot.on_update = lambda: calls.append(1) or "updating"
    monkeypatch.setattr(telegram, "chat_id", lambda: "42")
    monkeypatch.setattr(telegram, "send", lambda text, *a, **k: out.append(text))
    for word in ["update", "Update", "/update@MyBot", "update now"]:
        bot.handle({"update_id": 1, "message": {"text": word, "chat": {"id": 42}}})
    assert len(calls) == 4


def test_version_route():
    from fastapi.testclient import TestClient
    from jarvis import server
    c = TestClient(server.app, base_url="http://127.0.0.1:7334", client=("127.0.0.1", 5))
    assert c.get("/api/version").json()["version"] == updater.version()


def test_telegram_email_setup(monkeypatch):
    from jarvis import telegram
    out, calls, got = [], [], []
    bot = telegram.Bot(on_text=lambda t, voice=False: "AI:" + t, on_decision=lambda *a: "", log=lambda m: None)
    bot.on_email = lambda a, p: got.append((a, p)) or "connected"
    monkeypatch.setattr(telegram, "chat_id", lambda: "42")
    monkeypatch.setattr(telegram, "send", lambda text, *a, **k: out.append(text))
    monkeypatch.setattr(telegram, "api", lambda method, **p: calls.append((method, p)))
    msg = lambda t, i=1: {"update_id": i, "message": {"message_id": i, "text": t, "chat": {"id": 42}}}
    bot.handle(msg("me@gmail.com abcd efgh ijkl mnop"))
    assert not got                                                 # not asked for yet: goes to the AI as normal
    bot.handle(msg("set up my email"))
    assert "apppasswords" in out[-1]
    bot.handle(msg("me@gmail.com my password is hunter2", 7))
    assert ("deleteMessage", {"chat_id": "42", "message_id": 7}) in calls and not got and "again" in out[-1]
    bot.handle(msg("Me@Gmail.com  abcd efgh ijkl mnop", 8))
    assert got == [("Me@Gmail.com", "abcdefghijklmnop")] and out[-1] == "connected"
    assert ("deleteMessage", {"chat_id": "42", "message_id": 8}) in calls


def test_installapp_command(monkeypatch):
    from jarvis import telegram
    out = []
    bot = telegram.Bot(on_text=lambda t, voice=False: "AI", on_decision=lambda *a: "", log=lambda m: None)
    monkeypatch.setattr(telegram, "chat_id", lambda: "42")
    monkeypatch.setattr(telegram, "send", lambda text, *a, **k: out.append(text))
    monkeypatch.setattr(telegram.urllib.request, "urlopen", lambda *a, **k: (_ for _ in ()).throw(OSError("offline")))
    monkeypatch.setattr(telegram.threading, "Thread", lambda target, daemon=True: type("T", (), {"start": lambda self: target()})())
    for t in ("/installapp", "install the app", "/InstallApp@MyBot"):
        bot.handle({"update_id": 1, "message": {"message_id": 1, "text": t, "chat": {"id": 42}}})
    assert len(out) == 3 and all("releases/latest/download/JARVIS.apk" in x and "Play Protect" in x for x in out)
