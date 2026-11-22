"""Mark III phase 4: laptop command, Office files, screen and camera vision."""
import json
import os
import time

import pytest

from jarvis import desktop, devices
from jarvis.bus import Bus
from jarvis.config import settings
from jarvis.engine import Engine
from jarvis.store import Store
from jarvis.tools import ToolContext, execute


@pytest.fixture
def env(monkeypatch, tmp_path):
    store = Store(":memory:")
    bus = Bus(store)
    engine = Engine(store, bus, settings)
    monkeypatch.setattr(devices, "HOME", tmp_path)
    monkeypatch.setattr(devices, "WORKSPACE", tmp_path / "JARVIS")
    return store, ToolContext(store, bus, settings, engine, "EDITH"), tmp_path


def run(ctx, tool_name, **a):
    out, err = execute(tool_name, ctx, a)
    assert not err, out
    return json.loads(out)


def test_window_tools_explain_off_windows(env):
    _s, ctx, _h = env
    if desktop.WIN:
        pytest.skip("running on Windows")
    assert "Windows" in run(ctx, "media_control", action="play_pause")["error"]
    assert "Windows" in run(ctx, "window_action", title="Chrome", action="close")["error"]


def test_workspaces(env, monkeypatch):
    store, ctx, home = env
    opened = []
    monkeypatch.setattr(devices, "open_url", lambda u: opened.append(("url", u)))
    monkeypatch.setattr(devices, "open_app", lambda a: opened.append(("app", a)))
    run(ctx, "save_workspace", name="Exam mode", items=["https://kaplan.edu.sg", "notepad"])
    assert "exam mode" in run(ctx, "open_workspace")["workspaces"]
    run(ctx, "open_workspace", name="exam mode")
    assert opened == [("url", "https://kaplan.edu.sg"), ("app", "notepad")]
    assert "error" in run(ctx, "save_workspace", name="x", items=["https://www.dbs.com.sg/ibanking"])


def test_file_chores_preview_then_approved(env):
    store, ctx, home = env
    dl = home / "Downloads"
    dl.mkdir()
    for n in ("notes.pdf", "pic.png", "song.mp3", "IMG_001 copy.jpg", "IMG_002 copy.jpg"):
        (dl / n).write_text("x")
    prev = run(ctx, "organise_folder", folder="~/Downloads")
    assert prev["moves"] == 5 and "preview" in prev["status"] and (dl / "notes.pdf").exists()
    r = run(ctx, "rename_files", folder="Downloads", find=" copy", replace="")
    assert r["renames"] == 2 and (dl / "IMG_001 copy.jpg").exists()
    ctx.approved = True
    run(ctx, "rename_files", folder="Downloads", find=" copy", replace="")
    assert (dl / "IMG_001.jpg").exists()
    assert run(ctx, "organise_folder", folder="~/Downloads")["moved"] == 5
    assert (dl / "Documents" / "notes.pdf").exists() and (dl / "Images" / "IMG_001.jpg").exists()
    assert "error" in run(ctx, "organise_folder", folder="/etc")


def test_office_files(env):
    _s, ctx, home = env
    deck = run(ctx, "make_slides", title="FX Hedging", send_to_phone=False,
               slides=[{"title": "Forwards", "bullets": ["Lock a rate", "No upside"], "notes": "say it slowly"},
                       {"title": "Options", "bullets": ["Pay a premium", "Keep the upside"]}])
    from pptx import Presentation
    prs = Presentation(deck["pptx"])
    assert len(prs.slides) == 3 and prs.slides[1].shapes.title.text == "Forwards"
    xl = run(ctx, "make_spreadsheet", name="Tan wedding budget", send_to_phone=False,
             sheets=[{"name": "Budget", "columns": ["Item", "Cost"], "rows": [["Venue", 8000], ["Florist", 1200]], "totals": ["Cost"]}])
    from openpyxl import load_workbook
    ws = load_workbook(xl["xlsx"])["Budget"]
    assert ws["A1"].value == "Item" and ws["B4"].value == "=SUM(B2:B3)"


def test_look_at_screen_refuses_banking(env, monkeypatch):
    _s, ctx, _h = env
    monkeypatch.setattr(desktop, "foreground_title", lambda: "DBS digibank - Google Chrome")
    assert "bank" in run(ctx, "look_at_screen", question="what's this?")["error"].lower()


def test_new_screenshots_found_once(env):
    store, _ctx, home = env
    shots = home / "Pictures" / "Screenshots"
    shots.mkdir(parents=True)
    store.set("desk:shots_since", str(time.time() - 5))
    (shots / "Screenshot 2026-11-22 101010.png").write_bytes(b"png")
    assert len(desktop.new_screenshots(store)) == 1
    assert desktop.new_screenshots(store) == []


def test_live_vision_parses_boxes(monkeypatch):
    from jarvis import vision
    monkeypatch.setattr(vision, "ask", lambda data, mime, prompt: 'Sure: {"answer": "Navy suit wins.", "items": '
                        '[{"label": "Navy suit", "note": "better for evening", "box": [0.1, 0.2, 0.3, 1.4]}, {"label": "bad"}]}')
    out = vision.live(b"img", "image/jpeg", "outfit")
    assert out["answer"] == "Navy suit wins." and out["items"] == [
        {"label": "Navy suit", "note": "better for evening", "box": [0.1, 0.2, 0.3, 1.0]}]


def test_vision_endpoint(monkeypatch):
    import base64
    from fastapi.testclient import TestClient
    from jarvis import brain, server, vision
    c = TestClient(server.app, base_url="http://127.0.0.1:7334", client=("127.0.0.1", 9))
    monkeypatch.setattr(brain, "pick", lambda *a, **k: "gemini")
    seen = {}
    monkeypatch.setattr(vision, "live", lambda data, mime, mode, q: seen.update(data=data, mime=mime, mode=mode) or {"answer": "A cup.", "items": []})
    img = "data:image/jpeg;base64," + base64.b64encode(b"jpegbytes").decode()
    r = c.post("/api/vision", json={"image": img, "mode": "meal"}).json()
    assert r["answer"] == "A cup." and seen == {"data": b"jpegbytes", "mime": "image/jpeg", "mode": "meal"}
    assert c.post("/api/screenshot/analyse", json={"path": "/etc/passwd"}).status_code == 400
