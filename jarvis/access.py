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


def _nav():
    from . import navigate
    return navigate


def _offline_voice() -> bool:
    from . import localvoice
    return localvoice.ready()


def _stt_ready() -> bool:
    from . import stt
    return stt.available()


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
        {"id": "gemini", "label": "Free Gemini key (fast mode, clear hearing, Gemini voices, photo sorter)", "on": bool(settings.gemini_key),
         "action": "key", "key": "GEMINI_API_KEY", "how": "Get one free at aistudio.google.com/apikey, paste it here."},
        {"id": "telegram", "label": "Telegram (text JARVIS from anywhere, one-word updates)", "on": tg.ready(),
         "how": f"Send /start {tg.pair_code()} to your bot" if tg.enabled() and not tg.ready() else "Add your bot token in .env"},
        {"id": "phone", "label": "Phone linked", "on": phonelink.online(store, 30),
         "how": "Open the JARVIS app on your phone"},
        {"id": "hearing", "label": "Accurate hearing (JARVIS understands you on the laptop, with your names and places)",
         "on": _stt_ready(), "how": "start.bat installs it; the first start downloads the speech model once (~500 MB)"},
        {"id": "offline_voice", "label": "Natural offline voice (JARVIS still sounds human with no internet)",
         "on": _offline_voice(), "how": "Sets itself up: start.bat installs it and the voice downloads once (~330 MB)"},
        {"id": "dictate", "label": "Voice typing anywhere (hold Right Alt or the Copilot key and talk)", "on": _dictate_ready(),
         "how": "Needs faster-whisper and sounddevice (start.bat installs them)"},
        {"id": "autostart", "label": "Starts with Windows", "on": os.name != "nt" or startup_file().exists(),
         "action": "autostart"},
        {"id": "updates", "label": "Updates itself (nightly + 'update' on Telegram)", "on": (ROOT / ".git").exists(),
         "how": "Text 'update' once or double-click update.bat"},
        {"id": "email", "label": "Reads your email (briefings, inbox sweep, smart replies)", "on": channels.email_read_ready(),
         "action": "email", "detail": settings.smtp_user,
         "how": "Easiest: send /email to your JARVIS bot on Telegram. Or type it here: Gmail address + a Gmail app password."},
        {"id": "onemap", "label": "Real bus & MRT journeys (OneMap, free)", "on": _nav().onemap_ready(),
         "how": "Send /onemap to your JARVIS bot on Telegram (free account, 2 minutes)."},
        {"id": "lta", "label": "Live bus arrivals (LTA DataMall, free)", "on": _nav().lta_ready(),
         "how": "Send /lta to your JARVIS bot on Telegram (free key by email)."},
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
    _write_env({name: value})
    if name == "GEMINI_API_KEY":
        settings.gemini_key = value
    return "Saved."


def _write_env(values: dict[str, str]) -> None:
    env = ROOT / ".env"
    text = env.read_text(encoding="utf-8") if env.exists() else ""
    for name, value in values.items():
        if re.search(rf"^{name}=.*$", text, re.M):
            text = re.sub(rf"^{name}=.*$", lambda _m: f"{name}={value}", text, flags=re.M)
        else:
            text = text.rstrip("\n") + f"\n{name}={value}\n"
        os.environ[name] = str(value)
    env.write_text(text, encoding="utf-8")


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.I)


def save_transit(which: str, values: dict, check: bool = True) -> str:
    """OneMap (journeys) or LTA DataMall (live buses): check it really works, then save it on the laptop."""
    from . import navigate
    if which == "onemap":
        email, pw = values.get("email", "").strip(), values.get("password", "").strip()
        if not EMAIL_RE.match(email) or len(pw) < 4:
            raise ValueError("Send it as: your-email@gmail.com yourpassword")
        old = {k: os.environ.get(k, "") for k in ("JARVIS_ONEMAP_EMAIL", "JARVIS_ONEMAP_PASSWORD")}
        os.environ.update(JARVIS_ONEMAP_EMAIL=email, JARVIS_ONEMAP_PASSWORD=pw)
        navigate._token.update(value="", until=0.0)
        if check:
            try:
                navigate._onemap_token()
            except Exception:  # noqa: BLE001
                os.environ.update(old)
                raise ValueError("OneMap said no. Check the email and password (and that you confirmed the email).") from None
        _write_env({"JARVIS_ONEMAP_EMAIL": email, "JARVIS_ONEMAP_PASSWORD": pw})
        return "Bus & MRT journeys connected: real routes, bus numbers and leave-by times."
    key = values.get("key", "").strip()
    if not re.fullmatch(r"[A-Za-z0-9+/=_-]{16,64}", key):
        raise ValueError("That doesn't look like an LTA AccountKey. Copy the whole key from LTA's email.")
    old = os.environ.get("JARVIS_LTA_KEY", "")
    os.environ["JARVIS_LTA_KEY"] = key
    if check:
        import urllib.error
        import urllib.request
        try:
            req = urllib.request.Request(navigate.LTA_ARRIVAL_URL + "83139", headers={"AccountKey": key, "accept": "application/json"})
            urllib.request.urlopen(req, timeout=10).read()
        except urllib.error.HTTPError as exc:
            os.environ["JARVIS_LTA_KEY"] = old
            raise ValueError(f"LTA refused the key ({exc.code}). Copy it again from the email.") from None
        except Exception:  # noqa: BLE001
            os.environ["JARVIS_LTA_KEY"] = old
            raise ValueError("Couldn't reach LTA to check it. Is the laptop online?") from None
    _write_env({"JARVIS_LTA_KEY": key})
    return "Live bus arrivals connected."


def save_email(address: str, app_password: str, check: bool = True) -> str:
    """Gmail (or Google Workspace) via an app password: checks it really logs in, then saves it."""
    address, pw = address.strip(), re.sub(r"\s+", "", app_password)
    if not EMAIL_RE.match(address):
        raise ValueError("That email address doesn't look right.")
    if not re.fullmatch(r"[a-zA-Z]{16}", pw):
        raise ValueError("A Gmail app password is 16 letters (Google shows it in 4 groups of 4). Your normal password won't work.")
    if check:
        import imaplib
        try:
            box = imaplib.IMAP4_SSL("imap.gmail.com", 993, timeout=20)
            box.login(address, pw)
            box.logout()
        except imaplib.IMAP4.error:
            raise ValueError("Google said no. Check the address, and make a fresh app password.") from None
        except OSError as exc:
            raise ValueError(f"Couldn't reach Gmail to check it ({exc}). Is the laptop online?") from None
    _write_env({"JARVIS_SMTP_HOST": "smtp.gmail.com", "JARVIS_SMTP_PORT": "587", "JARVIS_IMAP_HOST": "imap.gmail.com",
                "JARVIS_SMTP_USER": address, "JARVIS_SMTP_PASSWORD": pw})
    settings.smtp_host, settings.smtp_port, settings.imap_host = "smtp.gmail.com", 587, "imap.gmail.com"
    settings.smtp_user, settings.smtp_password = address, pw
    return "Email connected. JARVIS restarts in a moment to start the inbox sweep."


def open_windows_setting(which: str) -> str:
    """Open the exact Windows settings page (microphone, camera, notifications, location, startup apps)."""
    pages = {"microphone": "ms-settings:privacy-microphone", "camera": "ms-settings:privacy-webcam",
             "notifications": "ms-settings:notifications", "location": "ms-settings:privacy-location",
             "startup": "ms-settings:startupapps", "focus": "ms-settings:quiethours"}
    if os.name != "nt" or which not in pages:
        return "Only on Windows."
    subprocess.Popen(["cmd", "/c", "start", "", pages[which]])
    return "Opened."
