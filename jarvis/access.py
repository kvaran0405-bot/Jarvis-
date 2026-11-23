"""One-tap setup: everything JARVIS can be allowed to do on the laptop, what's on, and a button for what's not.
The phone's half lives in the app itself (web/access.html asks Android directly)."""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from .config import ROOT, settings

KEYS = {   # what the setup page may write to .env (typed on the laptop itself, never sent anywhere else)
    "GEMINI_API_KEY": re.compile(r"^[A-Za-z0-9_.\-]{20,200}$"),   # "AIza..." or the newer "AQ...." style
    "JARVIS_BIRTHDAY": re.compile(r"^\d{2}-\d{2}$"),
}


def startup_file() -> Path:
    return Path(os.environ.get("APPDATA", str(Path.home()))) / "Microsoft/Windows/Start Menu/Programs/Startup/JARVIS.bat"


def _dictate_ready() -> bool:
    from . import dictate
    return bool(dictate.status().get("on"))


def status(store) -> list[dict]:
    from . import brain, channels, gcal, phonelink
    from . import telegram as tg
    b = brain.describe(store)
    items = [
        {"id": "brain", "label": "AI brain", "on": bool(b.get("now")), "detail": (b.get("now") or "none").upper(),
         "how": "Claude plan or a free Gemini key"},
        {"id": "gemini", "label": "Free Gemini key (fast mode, Gemini voices, photo sorter)", "on": bool(settings.gemini_key),
         "action": "key", "key": "GEMINI_API_KEY", "how": "Get one free at aistudio.google.com/apikey, paste it here."},
        {"id": "telegram", "label": "Telegram (text JARVIS from anywhere, one-word updates)", "on": tg.ready(),
         "how": f"Send /start {tg.pair_code()} to your bot" if tg.enabled() and not tg.ready() else "Add your bot token in .env"},
        {"id": "phone", "label": "Phone linked", "on": phonelink.online(store, 30),
         "how": "Open the JARVIS app on your phone"},
        {"id": "dictate", "label": "Voice typing anywhere (hold Right Alt or the Copilot key and talk)", "on": _dictate_ready(),
         "how": "Needs faster-whisper and sounddevice (start.bat installs them)"},
        {"id": "autostart", "label": "Starts with Windows", "on": os.name != "nt" or startup_file().exists(),
         "action": "autostart"},
        {"id": "updates", "label": "Updates itself (nightly + 'update' on Telegram)", "on": (ROOT / ".git").exists(),
         "how": "Text 'update' once or double-click update.bat"},
        {"id": "email", "label": "Reads your email (briefings, smart replies)", "on": channels.email_read_ready(),
         "how": "Gmail app password in .env (see README: Setting up the extras)"},
        {"id": "calendar", "label": "Google Calendar sync", "on": gcal.ready(), "link": "/google-setup.html"},
        {"id": "birthday", "label": "Your birthday (birthday mode)", "on": bool(os.environ.get("JARVIS_BIRTHDAY")),
         "action": "key", "key": "JARVIS_BIRTHDAY", "how": "MM-DD, e.g. 04-05"},
    ]
    return items


def install_autostart() -> str:
    if os.name != "nt":
        return "Only needed on Windows."
    f = startup_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(f'@echo off\r\ncd /d "{ROOT}"\r\nstart "JARVIS" /min cmd /c "{ROOT / "start.bat"}"\r\n')
    return "Done: JARVIS starts by itself when you log in."


def save_key(name: str, value: str) -> str:
    value = value.strip()
    if name not in KEYS or not KEYS[name].match(value):
        raise ValueError("That doesn't look right. Check it and try again.")
    env = ROOT / ".env"
    text = env.read_text(encoding="utf-8") if env.exists() else ""
    if re.search(rf"^{name}=.*$", text, re.M):
        text = re.sub(rf"^{name}=.*$", f"{name}={value}", text, flags=re.M)
    else:
        text = text.rstrip("\n") + f"\n{name}={value}\n"
    env.write_text(text, encoding="utf-8")
    os.environ[name] = value
    if name == "GEMINI_API_KEY":
        settings.gemini_key = value
    return "Saved."


def open_windows_setting(which: str) -> str:
    """Open the exact Windows settings page (microphone, camera, notifications, location, startup apps)."""
    pages = {"microphone": "ms-settings:privacy-microphone", "camera": "ms-settings:privacy-webcam",
             "notifications": "ms-settings:notifications", "location": "ms-settings:privacy-location",
             "startup": "ms-settings:startupapps", "focus": "ms-settings:quiethours"}
    if os.name != "nt" or which not in pages:
        return "Only on Windows."
    subprocess.Popen(["cmd", "/c", "start", "", pages[which]])
    return "Opened."
