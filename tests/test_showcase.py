"""Showcase: a customer-facing demo under its own brand, with demo data only."""
import re

from jarvis.config import ROOT

P = (ROOT / "web/showcase.html").read_text(encoding="utf-8")


def test_own_brand_no_personal_or_marvel_names():
    assert "KAIROS" in P
    for name in ("JARVIS", "VERONICA", "EDITH", "FRIDAY", "PEPPER", "Kamal", "Stark"):
        assert name not in P, name
    assert not re.search(r"[\w.+-]+@[\w-]+\.\w+", P)       # no email addresses
    assert "demo data" in P.lower()


def test_live_and_interactive():
    assert 'src="vendor/three.min.js"' in P                  # works offline from the laptop
    assert "ShaderMaterial" in P and "pointermove" in P and "pinch0" in P
    assert "function play(" in P and "speechSynthesis" in P  # spoken briefing with a scrubber
    assert "function scamCheck(" in P and "queue.push(q)" in P  # never drops a request


def test_fits_phone_and_laptop():
    assert "@media (max-width:560px)" in P and "minmax(0,1fr)" in P
    assert "prefers-reduced-motion" in P


def test_training_mission():
    assert 'id: "showcase"' in (ROOT / "web/tutorial.js").read_text(encoding="utf-8")
