"""Which AI 'brain' JARVIS thinks with, and the owner's pause switch.

Brains:
  pro    - your Claude Pro/Max plan, through Claude Code on this laptop (no extra cost; shares your plan's limits)
  api    - Anthropic API key (pay as you go)
  gemini - Google Gemini free tier (backup / saver mode)

Modes (the owner's switch, from the dashboard, Telegram or voice):
  on     - normal
  saver  - don't touch Claude at all: everything runs on Gemini (or waits if Gemini isn't set up)
  paused - JARVIS thinks about nothing: no AI calls, no automatic jobs. Approved messages still go out.
"""
from __future__ import annotations

import os
import re
import shutil
from datetime import datetime, timedelta

from .config import settings

MODES = ("on", "saver", "paused")


# ---------------------------------------------------------------- availability
def claude_cli() -> str | None:
    custom = os.environ.get("JARVIS_CLAUDE_PATH", "").strip()
    return custom or shutil.which("claude")


def ready(brain: str) -> bool:
    if brain == "api":
        return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))
    if brain == "pro":
        return claude_cli() is not None
    if brain == "gemini":
        return bool(settings.gemini_key)
    return False


def primary() -> str:
    """The main brain: JARVIS_BRAIN if set, otherwise the best one that is available."""
    if settings.brain in ("pro", "api", "gemini"):
        return settings.brain
    for b in ("api", "pro", "gemini"):
        if ready(b):
            return b
    return "pro"


def automation_brain() -> str:
    """Brain for scheduled jobs. Defaults to Gemini when it's set up, to save your Claude plan for you."""
    if settings.automation_brain in ("pro", "api", "gemini"):
        return settings.automation_brain
    return "gemini" if ready("gemini") else primary()


# ---------------------------------------------------------------- mode switch
def get_mode(store) -> dict:
    state = store.get("brain:mode") or {"mode": "on", "until": None}
    if state.get("until") and datetime.fromisoformat(state["until"]) <= datetime.now(settings.tz):
        state = {"mode": "on", "until": None}
        store.set("brain:mode", state)
    return state


def set_mode(store, mode: str, hours: float | None = None) -> dict:
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    until = (datetime.now(settings.tz) + timedelta(hours=hours)).isoformat(timespec="minutes") if hours else None
    state = {"mode": mode, "until": until if mode != "on" else None}
    store.set("brain:mode", state)
    return state


def mark_pro_limited(store, hours: float = 1.0) -> None:
    store.set("brain:pro_limited_until", (datetime.now(settings.tz) + timedelta(hours=hours)).isoformat())


def pro_limited(store) -> bool:
    until = store.get("brain:pro_limited_until")
    return bool(until) and datetime.fromisoformat(until) > datetime.now(settings.tz)


def pick(store, background: bool = False, preferred: str = "") -> str | None:
    """The brain to use right now, or None if JARVIS must not think (paused / nothing available).
    `preferred` is an agent's own brain (JARVIS_BRAIN_<AGENT>), tried first."""
    mode = get_mode(store)["mode"]
    if mode == "paused":
        return None
    if mode == "saver":
        order = ["gemini"]
    elif background:
        order = [automation_brain(), primary(), "gemini"]
    else:
        order = [primary(), "gemini"]
    if preferred in ("pro", "api", "gemini") and mode != "saver":
        order = [preferred] + order
    for b in order:
        if not ready(b) or (b == "pro" and pro_limited(store)):
            continue
        return b
    return None


def fast_voice(store) -> bool:
    """Spoken commands use Gemini Flash (answers in about a second) instead of the main brain. Say "fast mode on"."""
    import os
    choice = store.get("voice:fast") or os.environ.get("JARVIS_FAST_VOICE", "off")
    return choice.lower() == "on"


def describe(store) -> dict:
    state = get_mode(store)
    return {"mode": state["mode"], "until": state.get("until"), "primary": primary(),
            "automation": automation_brain(), "now": pick(store), "pro_limited": pro_limited(store),
            "ready": {b: ready(b) for b in ("pro", "api", "gemini")}, "fast": fast_voice(store) and ready("gemini")}


def gemini_check() -> tuple[bool, float, str]:
    """Ask Gemini for one word, to prove the key works. (ok, seconds, problem in plain words)."""
    import time
    from . import brains
    if not settings.gemini_key:
        return False, 0.0, "there's no Gemini key yet"
    # Each Gemini model has its own free allowance, and some have none on some accounts. Try the usual free ones and
    # keep the first that answers, so one model being "used up" doesn't make a good key look broken.
    models = list(dict.fromkeys([settings.gemini_model, *brains.GEMINI_SPARES]))
    limited, last = False, ""
    for model in models:
        t0 = time.time()
        try:
            brains._gemini_call({"contents": [{"role": "user", "parts": [{"text": "Reply with just: OK"}]}],
                                 "generationConfig": {"maxOutputTokens": 5}}, model)
            if model != settings.gemini_model:   # remember the model that works for this key
                from . import access
                access._write_env({"JARVIS_GEMINI_MODEL": model})
                settings.gemini_model = model
            return True, time.time() - t0, ""
        except brains.LimitReached:
            limited = True
            continue
        except Exception as exc:  # noqa: BLE001
            msg = last = str(exc)
            if "API_KEY_INVALID" in msg or "API key not valid" in msg or " 403" in msg:
                return False, 0.0, "Google says the key isn't valid (copy it again, all of it)"
            if " 404" in msg or " 400" in msg:   # this model isn't offered to the key: try the next
                continue
            return False, 0.0, f"Gemini didn't answer ({msg[:120]})"
    if limited:
        return False, 0.0, LIMITED
    return False, 0.0, f"Gemini didn't answer ({last[:120]})"


LIMITED = "Google's free limit is used up on every Gemini model for now (it resets daily)"


# ---------------------------------------------------------------- spoken / typed control phrases
_HOURS = r"(?:\s+(?:for\s+)?(\d+(?:\.\d+)?)\s*(h|hr|hrs|hours?|m|min|mins|minutes?)?)?"  # bare number = hours
PAUSE_RE = re.compile(r"^\s*/?(?:(?:hey|ok)\s+)?(?:jarvis[,\s]+)?(?:pause|sleep|stand\s*down|go to sleep)"
                      r"(?:\s+jarvis)?" + _HOURS + r"\s*[.!]?\s*$", re.I)
SAVER_RE = re.compile(r"^\s*/?(?:jarvis[,\s]+)?(?:saver|saver mode|save my claude|use gemini|gemini mode)"
                      + _HOURS + r"\s*[.!]?\s*$", re.I)
RESUME_RE = re.compile(r"^\s*/?(?:jarvis[,\s]+)?(?:resume|unpause|wake up|come back|back online|normal mode)"
                       r"(?:\s+jarvis)?\s*[.!]?\s*$", re.I)
STATUS_RE = re.compile(r"^\s*/?(?:jarvis[,\s]+)?(?:brain|brain status|status)\s*[?.!]?\s*$", re.I)


def _hours(m: re.Match) -> float | None:
    if not m.group(1):
        return None
    n = float(m.group(1))
    return n / 60 if (m.group(2) or "h").lower().startswith("m") else n


def _until_text(state: dict) -> str:
    return f" until {state['until'][11:16]}" if state.get("until") else " until you say resume"


def handle_control(store, text: str) -> str | None:
    """If `text` is a pause/saver/resume/status command, apply it and return the reply. Uses no AI."""
    if m := PAUSE_RE.match(text):
        st = set_mode(store, "paused", _hours(m))
        return f"⏸ Paused{_until_text(st)}. I won't use any AI or run routines. Say 'resume' to wake me."
    if m := SAVER_RE.match(text):
        if not ready("gemini"):
            return "Saver mode needs a free Gemini key (GEMINI_API_KEY in .env). Say 'pause' to stop me instead."
        st = set_mode(store, "saver", _hours(m))
        return f"🔋 Saver mode{_until_text(st)}: I'll leave your Claude plan alone and run on Gemini."
    if RESUME_RE.match(text):
        set_mode(store, "on")
        return f"▶ Back online, {settings.owner_name}. Thinking with {_label(pick(store))}."
    if STATUS_RE.match(text):
        d = describe(store)
        mode = {"on": "▶ On", "saver": "🔋 Saver", "paused": "⏸ Paused"}[d["mode"]]
        extra = f" until {d['until'][11:16]}" if d.get("until") else ""
        limit = " Your Claude plan hit its limit, so I'm on the backup for now." if d["pro_limited"] else ""
        return (f"{mode}{extra}. Main brain: {_label(d['primary'])}; routines: {_label(d['automation'])}; "
                f"right now: {_label(d['now'])}.{limit}")
    return None


def _label(brain: str | None) -> str:
    return {"pro": "your Claude plan", "api": "Claude API", "gemini": "Gemini (free)", None: "nothing (paused)"}[brain]
