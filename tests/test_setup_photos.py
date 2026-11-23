"""One-tap setup and the photo sorter."""
import json

import pytest

from jarvis import access, photosort
from jarvis.store import Store
from jarvis.tools import REGISTRY, ToolContext


def test_setup_status_and_keys(tmp_path, monkeypatch):
    from jarvis import config
    monkeypatch.setattr(access, "ROOT", tmp_path)
    (tmp_path / ".env").write_text("GEMINI_API_KEY=\nOTHER=1\n")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("JARVIS_BIRTHDAY", raising=False)
    items = {i["id"]: i for i in access.status(Store(":memory:"))}
    assert {"brain", "gemini", "telegram", "phone", "autostart", "email", "calendar"} <= set(items)
    with pytest.raises(ValueError):
        access.save_key("ANTHROPIC_API_KEY", "x" * 30)          # only the keys the page is meant to set
    with pytest.raises(ValueError):
        access.save_key("JARVIS_BIRTHDAY", "5 April")
    access.save_key("GEMINI_API_KEY", "AQ.Test" + "b" * 40)        # newer key style (with a dot) is accepted
    access.save_key("GEMINI_API_KEY", "AIzaSyA" + "b" * 32)
    access.save_key("JARVIS_BIRTHDAY", "04-05")
    env = (tmp_path / ".env").read_text()
    assert "GEMINI_API_KEY=AIzaSyA" in env and "JARVIS_BIRTHDAY=04-05" in env and "OTHER=1" in env
    assert config.settings.gemini_key.startswith("AIzaSyA")
    monkeypatch.setattr(config.settings, "gemini_key", "")


def test_setup_routes_are_laptop_only():
    from fastapi.testclient import TestClient
    from jarvis import server
    local = TestClient(server.app, base_url="http://127.0.0.1:7334", client=("127.0.0.1", 5))
    assert local.get("/api/setup").json()["local"] is True
    assert local.get("/access.html").status_code == 200 and local.get("/tutorial.js").status_code == 200
    remote = TestClient(server.app, base_url="http://127.0.0.1:7334", client=("127.0.0.1", 5),
                        headers={"x-forwarded-for": "100.64.0.9"})
    assert remote.post("/api/setup/key", json={"name": "GEMINI_API_KEY", "value": "x" * 30}).status_code in (401, 403)


def test_photo_sorter(tmp_path, monkeypatch):
    from jarvis import config, vision
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setattr(photosort, "albums_dir", lambda: tmp_path / "Albums")
    inbox = tmp_path / "data" / "phone_photos" / "inbox"
    inbox.mkdir(parents=True)
    for n in ("20261123-010101-receipt", "20261123-010102-card", "20261123-010103-stage"):
        (inbox / f"{n}.jpg").write_bytes(b"jpg")
    answers = iter(['{"album": "Receipts", "caption": "Uniqlo receipt $49.90"}', '{"album": "PRIVATE"}',
                    'Sure: {"album": "event setups", "caption": "Tan wedding stage, white flowers"}'])
    monkeypatch.setattr(vision, "ask", lambda *a: next(answers))
    s = Store(":memory:")
    out = photosort.sort_inbox(s)
    assert out == {"sorted": 2, "albums": {"Receipts": 1, "Event Setups": 1}}
    assert (tmp_path / "Albums" / "Receipts" / "20261123-010101-receipt.jpg").exists()
    assert not list(inbox.glob("*.jpg"))                          # the bank card photo was thrown away, not filed
    ctx = ToolContext(s, None, config.settings, None, "JARVIS")
    hit = REGISTRY["find_photo"].fn(ctx, query="uniqlo receipt")
    assert hit["count"] == 1 and hit["photos"][0]["album"] == "Receipts"
    assert REGISTRY["find_photo"].fn(ctx, album="Event Setups")["photos"][0]["caption"].startswith("Tan wedding")
    photosort.received(s, inbox, 1763900000)
    assert s.get("photos:since") == "1763900000"
    photosort.request_new(s)
    cmd = s.query("SELECT kind, payload FROM phone_cmds")[0]
    assert cmd["kind"] == "photos" and json.loads(cmd["payload"])["since"] == 1763900000


def test_email_setup(tmp_path, monkeypatch):
    from jarvis import config
    monkeypatch.setattr(access, "ROOT", tmp_path)
    for v in ("JARVIS_SMTP_HOST", "JARVIS_SMTP_PORT", "JARVIS_IMAP_HOST", "JARVIS_SMTP_USER", "JARVIS_SMTP_PASSWORD"):
        monkeypatch.delenv(v, raising=False)   # restored after the test
    for k in ("smtp_host", "smtp_port", "imap_host", "smtp_user", "smtp_password"):
        monkeypatch.setattr(config.settings, k, getattr(config.settings, k))
    with pytest.raises(ValueError):
        access.save_email("not-an-email", "abcdabcdabcdabcd", check=False)
    with pytest.raises(ValueError):
        access.save_email("me@gmail.com", "myNormalPassword1", check=False)
    access.save_email("me@gmail.com", "abcd efgh ijkl mnop", check=False)
    env = (tmp_path / ".env").read_text()
    assert "JARVIS_SMTP_USER=me@gmail.com" in env and "JARVIS_SMTP_PASSWORD=abcdefghijklmnop" in env
    assert "JARVIS_IMAP_HOST=imap.gmail.com" in env
    from jarvis import channels
    assert channels.email_read_ready()
