"""JARVIS tells you about new emails / WhatsApp straight away; nothing is hidden except real one-time codes."""
from jarvis.config import ROOT
from jarvis.guard import has_code

A = ROOT / "android/app/src/main"


def test_only_real_codes_are_secret():
    assert has_code("Your OTP is 829101") and has_code("Verification code: 4471")
    for fine in ("Pin this job post", "Reset your password", "Boost your career at a bank", "Otherwise all good, 2026 plans"):
        assert not has_code(fine), fine


def test_phone_announces_email_and_whatsapp():
    ann = (A / "java/os/jarvis/app/Announcer.java").read_text(encoding="utf-8")
    assert '"com.google.android.gm"' in ann and '"com.whatsapp"' in ann and "org.telegram" not in ann
    assert "quietNow" in ann and "RINGER_MODE_NORMAL" in ann and "Stop announcing" in ann
    sr = (A / "java/os/jarvis/app/SmartReplies.java").read_text(encoding="utf-8")
    assert sr.count("Announcer.heard(") == 2
    solo = (A / "assets/solo.html").read_text(encoding="utf-8")
    assert "window.soloAnnounce" in solo and "IMPORTANT" in solo and "N.setAnnounce(false)" in solo


def test_phone_filter_no_longer_drops_normal_words():
    solo = (A / "java/os/jarvis/app/Solo.java").read_text(encoding="utf-8")
    assert "SECRET_WORD.matcher(all).find() && CODE.matcher(all).find()" in solo
    assert "Net.isFinance(title) || Net.isFinance(text)" not in solo


def test_google_recogniser_and_alternatives():
    main = (A / "java/os/jarvis/app/MainActivity.java").read_text(encoding="utf-8")
    assert "com.google.android.googlequicksearchbox" in main and "EXTRA_BIASING_STRINGS" in main
    assert "Other possible hearings" in (A / "assets/solo.html").read_text(encoding="utf-8")
