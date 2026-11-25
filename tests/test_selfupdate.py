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
