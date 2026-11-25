"""Holo Hands one-hand control: spread/squeeze to resize, fist to carry and toss, twist to spin, peace and thumbs-up."""
from jarvis.config import ROOT

H = (ROOT / "web/hands.html").read_text(encoding="utf-8")


def test_one_hand_gestures_are_there():
    assert "function readPose(" in H and "thumbsUp" in H and "peace" in H
    assert "scaleT * Math.exp(d * .9)" in H          # spread = bigger, squeeze = smaller
    assert "carry = {" in H and "function letGo(" in H and "toss = {" in H   # fist = carry, let go fast = toss
    assert "function twist(" in H                     # wrist twist = spin
    assert "fist: fingers === 0 && open < 1.15 && !thumbsUp" in H


def test_hero_holograms():
    for m in ("gauntlet(){", "armor(){", "king(){"):
        assert m in H, m
    assert '"gauntlet", "armor", "king"' in H and "HANDCURL" in H and "REPULSOR" in H
    for f in ("web/home.html", "web/hud-fx.js"):   # they can be thrown between screens too
        assert '"gauntlet", "armor", "king"' in (ROOT / f).read_text(encoding="utf-8")
