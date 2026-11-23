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
    assert "Updated" in msgs[0] and "Remove edge glow" in msgs[0] and "releases/latest" in msgs[1]
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
