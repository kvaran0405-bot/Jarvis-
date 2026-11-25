"""The phone app installs its own updates (no hand-installing APKs)."""
from jarvis.config import ROOT

A = ROOT / "android/app/src/main"


def test_app_updates_itself():
    java = (A / "java/os/jarvis/app/AppUpdate.java").read_text(encoding="utf-8")
    assert "releases/latest" in java and "PackageInstaller" in java and "USER_ACTION_NOT_REQUIRED" in java
    man = (A / "AndroidManifest.xml").read_text(encoding="utf-8")
    assert "REQUEST_INSTALL_PACKAGES" in man and "AppUpdate$Result" in man and "MY_PACKAGE_REPLACED" in man
    assert "AppUpdate.check" in (A / "java/os/jarvis/app/SoloBrain.java").read_text(encoding="utf-8")
    assert "canSelfUpdate" in (ROOT / "web/access.html").read_text(encoding="utf-8")


def test_signing_key_is_a_jarvis_pkcs12():
    from cryptography.hazmat.primitives.serialization import pkcs12
    from jarvis.signing import make_keystore
    k = pkcs12.load_pkcs12(make_keystore("pw123456"), b"pw123456")
    assert k.key is not None and k.cert.friendly_name == b"jarvis"


def test_holo_hands_tracks_off_the_main_thread():
    h = (ROOT / "web/hands.html").read_text(encoding="utf-8")
    assert "new Worker(" in h and "importScripts" in h            # hand tracking in its own thread (classic worker)
    assert "minHandDetectionConfidence: .5" in h                   # real hands only (no ghosts); gestures debounced
    assert "requestVideoFrameCallback" in h and "function filt(" in h   # new frames only; smoothed + predicted
    assert "shadowBlur = 10" not in h and "shadowBlur = 16" not in h    # no per-frame blur glows
