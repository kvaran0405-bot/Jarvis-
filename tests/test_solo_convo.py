"""Solo mode: cinematic voices in the pack, instant answers, no-tap follow-ups, Gmail from notifications."""
from jarvis import gemtts, solo
from jarvis.config import ROOT

SOLO = (ROOT / "android/app/src/main/assets/solo.html").read_text(encoding="utf-8")


def test_every_agent_has_a_cinematic_voice():
    for name, (voice, who) in gemtts.VOICES.items():
        assert voice and len(who) > 40, name
    assert "Irish" in gemtts.VOICES["FRIDAY"][1] and "velvety" in gemtts.VOICES["PEPPER"][1]


def test_pack_carries_attitude_and_acting_note():
    v = solo._voices()
    assert v["cast"]["VERONICA"][2] == "sarcastic"
    assert "{who}" in v["acting"] and "{mood}" in v["acting"]
    assert "accent" in gemtts.direction("FRIDAY", "Morning!")


def test_solo_follows_up_without_a_tap():
    assert "followUntil = Date.now() + 8000" in SOLO
    assert "that'?s (all|it)" in SOLO          # "that's all" ends the conversation
    assert "stopListening" in SOLO             # stops listening soon after the owner stops talking


def test_solo_is_faster():
    assert "async function quick(" in SOLO and "await quick(text) || await think(text)" in SOLO
    assert "thinkingBudget: 0" in SOLO
    assert "function chunks(" in SOLO


def test_gmail_comes_from_notifications():
    java = (ROOT / "android/app/src/main/java/os/jarvis/app").glob("*.java")
    src = "\n".join(p.read_text(encoding="utf-8") for p in java)
    assert "getActiveNotifications" in src and "EXTRA_BIG_TEXT" in src
    assert "soloNotesAccess" in SOLO and "Gmail" in SOLO


def test_laptop_page_hands_over_to_solo():
    home = (ROOT / "web/home.html").read_text(encoding="utf-8")
    assert "function laptopGone(" in home and "N.goSolo(pending)" in home and "visibilitychange" in home
    assert "goSolo" in (ROOT / "web/sw.js").read_text(encoding="utf-8")
    main = (ROOT / "android/app/src/main/java/os/jarvis/app/MainActivity.java").read_text(encoding="utf-8")
    assert "public void goSolo(String pending)" in main and "&ask=" in main
    assert 'get("ask")' in SOLO


def test_retired_gemini_models_are_never_used():
    from jarvis import brains
    from jarvis.config import _live_gemini
    assert _live_gemini("gemini-2.0-flash") == "gemini-flash-latest" and _live_gemini("gemini-2.5-flash") == "gemini-2.5-flash"
    assert not any(m.startswith(("gemini-2.0", "gemini-1.")) for m in brains.GEMINI_SPARES)
    assert "gemini-2.0" not in SOLO.split("const SPARES")[1].split("\n")[0]
    assert "refreshFromGitHub" in (ROOT / "android/app/src/main/java/os/jarvis/app/SoloBrain.java").read_text(encoding="utf-8")


def test_backup_voices_are_the_cast_not_the_default():
    java = (ROOT / "android/app/src/main/java/os/jarvis/app/Voices.java").read_text(encoding="utf-8")
    assert '"JARVIS",   new Part(GB' in java and "isWoman(code) != wantWoman" in java
    assert "N.speakAs(id, say, agent)" in SOLO
    assert "VCACHE.get(vkey(agent, text))" in SOLO   # premium lines are remembered and replayed
