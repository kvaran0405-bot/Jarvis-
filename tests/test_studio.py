"""Mark III phase 6: floor plans, mood boards, portfolio, backup & restore, rebrand."""
import json
import zipfile

import pytest

from jarvis import devices, studio
from jarvis.bus import Bus
from jarvis.config import settings
from jarvis.engine import Engine
from jarvis.store import Store
from jarvis.tools import ToolContext, execute


@pytest.fixture
def env(monkeypatch, tmp_path):
    store = Store(":memory:")
    bus = Bus(store)
    monkeypatch.setattr(devices, "WORKSPACE", tmp_path / "JARVIS")
    return store, ToolContext(store, bus, settings, Engine(store, bus, settings), "PEPPER"), tmp_path


def run(ctx, tool_name, **a):
    out, err = execute(tool_name, ctx, a)
    assert not err, out
    return json.loads(out)


def test_auto_layout_fits_guests_without_overlaps():
    lay = studio.auto_layout(24, 18, 180, "wedding")
    tables = [i for i in lay["items"] if i["type"] == "round_table"]
    assert lay["fits"] and len(tables) == 18 and lay["capacity"] == 180
    kinds = {i["type"] for i in lay["items"]}
    assert {"stage", "dance_floor", "buffet", "bar", "photo_booth", "entrance"} <= kinds
    for t in tables:   # inside the room and clear of each other (3 m pitch)
        assert 0 <= t["x"] and t["x"] + t["w"] <= 24 and 0 <= t["y"] and t["y"] + t["h"] <= 18
    centres = [(t["x"] + .9, t["y"] + .9) for t in tables]
    assert all(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** .5 >= 2.9 for i, a in enumerate(centres) for b in centres[i + 1:])
    small = studio.auto_layout(10, 10, 300, "corporate")
    assert not small["fits"] and "bigger room" in small["note"]


def test_plan_layout_saves_to_gig(env):
    store, ctx, _ = env
    gid = store.add_gig("Priya", event_type="Wedding", guests=180)
    out = run(ctx, "plan_layout", gig_id=gid, room_w=24, room_l=18, guests=180)
    assert out["fits"] and "/planner.html?gig=" in out["open"]
    assert json.loads(store.get_gig(gid)["layout"])["client"] == "Priya"


def test_moodboard_pdf(env):
    _s, ctx, _ = env
    out = run(ctx, "make_moodboard", client="Priya & Arun", theme="Royal Garden", palette=["#1f3b2d", "#c9a24a", "#f3e9dc", "#7a1f2b"],
              story="Old-world romance under fairy lights.", keywords=["gold", "garden", "candlelight"],
              elements=[{"area": "Florals", "idea": "Cascading white orchids with eucalyptus"},
                        {"area": "Lighting", "idea": "Warm canopy of fairy lights"}], send_to_phone=False)
    from pypdf import PdfReader
    text = PdfReader(out["pdf"]).pages[0].extract_text()
    assert "Royal Garden" in text and "Florals".upper() in text and "#C9A24A" in text


def test_portfolio_site_and_brand_kit(env, monkeypatch):
    store, ctx, tmp = env
    monkeypatch.setattr(studio, "ROOT", tmp)
    (tmp / "business.md").write_text("- Business name: Shaabaz Weddings & Events\n- Phone: +65 9000 0000\n"
                                     "- Event types: weddings, engagements, corporate\n- Team: ~30 part-timers\n"
                                     "## Packages\n- Gold - $12,000 - Full coordination\n")
    out = run(ctx, "build_portfolio", testimonials=[{"quote": "Flawless day", "name": "Priya"}])
    html = open(out["site"]).read()
    assert "Shaabaz Weddings &amp; Events" in html and "Gold" in html and "Flawless day" in html and "30" in html
    assert out["packages_found"] == 1 and open(out["logo"]).read().startswith("<svg")
    assert out["business_card_qr"].endswith(".svg")


def test_backup_and_restore(env, monkeypatch, tmp_path):
    root = tmp_path / "root"
    (root / "data").mkdir(parents=True)
    monkeypatch.setattr(studio, "ROOT", root)
    db = root / "data" / "jarvis.db"
    s = Store(db)
    s.add_note("Secret plan", "Propose in Bali")
    monkeypatch.setattr(settings, "db_path", db)
    (root / "profile.md").write_text("Kamal")
    (root / ".env").write_text("JARVIS_SMTP_PASSWORD=x")
    z = studio.backup(include_settings=False)
    names = zipfile.ZipFile(z).namelist()
    assert "data/jarvis.db" in names and "profile.md" in names and ".env" not in names
    (root / "profile.md").write_text("changed")
    assert set(studio.restore(str(z))) >= {"data/jarvis.db", "profile.md"}
    assert (root / "profile.md").read_text() == "Kamal" and (root / "profile.md.before-restore").exists()
    assert Store(db).search_notes("Bali")[0]["title"] == "Secret plan"


def test_layout_api_and_brand():
    from fastapi.testclient import TestClient
    from jarvis import server
    c = TestClient(server.app, base_url="http://127.0.0.1:7334", client=("127.0.0.1", 4))
    lay = c.post("/api/layout/auto", json={"room_w": 20, "room_l": 15, "guests": 100}).json()
    assert lay["fits"] and c.post("/api/layout", json={"layout": lay}).json()["ok"]
    assert c.get("/api/layout").json()["guests"] == 100
    assert c.get("/api/agents").json()["brand"]["name"] == settings.brand_name
