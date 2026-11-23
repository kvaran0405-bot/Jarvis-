"""One-word updates: say "update" on Telegram and JARVIS pulls the newest version, restarts, and tells you when it's
back. Open pages on the laptop and phone reload themselves onto the new version. If the phone app itself changed
(rare: almost everything lives on the laptop), you get a link to the new app."""
from __future__ import annotations

import hashlib
import subprocess

from .config import ROOT

RELEASES = "https://github.com/kvaran0405-bot/Jarvis-/releases/latest"
_cache: dict[str, str] = {}


def _tree_hash(*folders: str, exts: tuple[str, ...] = ()) -> str:
    h = hashlib.sha1()
    for folder in folders:
        base = ROOT / folder
        if not base.exists():
            continue
        for p in sorted(base.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts and "build" not in p.parts and (not exts or p.suffix in exts):
                h.update(str(p.relative_to(ROOT)).encode())
                h.update(p.read_bytes())
    return h.hexdigest()[:12]


def version() -> str:
    """Changes whenever the code or the pages change (no Git needed)."""
    if "v" not in _cache:
        _cache["v"] = _tree_hash("jarvis", "web", exts=(".py", ".js", ".html", ".css", ".json"))
    return _cache["v"]


def app_version() -> str:
    return _tree_hash("android/app/src")


def latest_change() -> str:
    try:
        out = subprocess.run(["git", "log", "-1", "--format=%s"], cwd=ROOT, capture_output=True, text=True, timeout=10)
        return out.stdout.strip()
    except Exception:  # noqa: BLE001 - Git is optional
        return ""


def mark_started(store) -> None:
    store.set("update:pending", version())


def after_boot(store, send) -> list[str]:
    """Called when JARVIS starts: report how an update went, and flag a new phone app. Returns the messages sent."""
    sent = []
    before = store.get("update:pending")
    app_now, app_before = app_version(), store.get("update:app")
    if before:
        store.set("update:pending", "")
        if before == version():
            sent.append("✅ Back online, Sir. You were already on the newest version.")
        else:
            what = latest_change()
            sent.append("✅ Updated and back online, Sir. The laptop and your phone pages are on the newest version"
                        + (f".\nLatest change: {what}" if what else "."))
    if app_before and app_now != app_before:
        sent.append("📱 The phone app has a new version too. Open this on your phone, download JARVIS.apk and tap "
                    f"Install (it keeps your settings):\n{RELEASES}")
    store.set("update:app", app_now)
    for m in sent:
        try:
            send(m)
        except Exception:  # noqa: BLE001 - Telegram may be off
            pass
    return sent
