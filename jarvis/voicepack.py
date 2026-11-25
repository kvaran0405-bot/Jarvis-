"""The phone's voice pack: the lines JARVIS and the team say most, recorded by the laptop in the very voice the owner
hears at home (Gemini or the free neural voices), copied to the phone. In solo mode those lines sound exactly like home,
and cost no free allowance. The rest of solo's speech uses the premium voice while the daily allowance lasts, then
each agent's matched backup voice.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import threading

from .config import ROOT

PACK = ROOT / "data" / "voicepack.json"
PHRASES = [
    ("JARVIS", "Very good, Sir."), ("JARVIS", "Good night, Sir."), ("JARVIS", "Yes Sir?"), ("JARVIS", "Always, Sir."),
    ("JARVIS", "My pleasure, Sir."), ("JARVIS", "Anytime, Sir."), ("JARVIS", "Done, Sir."), ("JARVIS", "On it, Sir."),
    ("JARVIS", "One moment, Sir."), ("JARVIS", "Right away, Sir."), ("JARVIS", "Sorry Sir, I didn't catch that. Once more?"),
    ("JARVIS", "Good morning, Sir. What can I do for you?"), ("JARVIS", "Good afternoon, Sir. What can I do for you?"),
    ("JARVIS", "Good evening, Sir. What can I do for you?"), ("JARVIS", "Good morning, Sir."), ("JARVIS", "Good afternoon, Sir."),
    ("JARVIS", "Good evening, Sir."), ("JARVIS", "That's the briefing. Where shall we start?"),
    ("JARVIS", "All quiet. The team awaits your orders."), ("JARVIS", "Nothing open, Sir. Enjoy it."),
    ("JARVIS", "Nothing coming up in the calendar, Sir."), ("JARVIS", "Added, Sir."), ("JARVIS", "Noted, Sir."),
    ("JARVIS", "I've no internet right now, Sir. Reminders and alarms still work offline."),
    ("JARVIS", "That didn't go through, Sir. Once more?"), ("JARVIS", "Checking for a newer me, Sir. If there is one, it installs itself."),
    ("JARVIS", "Understood, Sir. I'll keep new messages to myself until you say announce messages."),
    ("JARVIS", "Very good, Sir. I'll tell you about new emails and WhatsApp messages the moment they arrive."),
    ("JARVIS", "Point the camera at it, Sir, and tap explain."),
    # the trailer
    ("JARVIS", "Good evening, Sir. Systems coming online."), ("JARVIS", "Just A Rather Very Intelligent System."),
    ("JARVIS", "I listen."), ("JARVIS", "I learn."), ("JARVIS", "I plan."), ("JARVIS", "I protect."),
    ("JARVIS", "And I never work alone."), ("JARVIS", "Wherever you go, I go."), ("JARVIS", "I run the numbers."),
    ("JARVIS", "This is your story."), ("JARVIS", "And when you need me most..."), ("JARVIS", "Starring... you, Sir."),
    ("JARVIS", "I'm always online, Sir."), ("FRIDAY", "Boss, you watched the whole thing? Legend."),
]


def vkey(agent: str, text: str) -> str:
    """Must match the phone's vkey() in solo.html."""
    return agent + "|" + re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", "", text.lower())).strip()


def version() -> str:
    try:
        return json.loads(PACK.read_text(encoding="utf-8")).get("version", "")
    except Exception:  # noqa: BLE001
        return ""


def build(extra: list[tuple[str, str]] | None = None) -> dict:
    """Record every line (the laptop's own cache makes rebuilding cheap) into one file for the phone."""
    from . import voice
    lines, failed = {}, 0
    for agent, text in PHRASES + (extra or []):
        try:
            path = voice.synthesize(agent, text)
            data = path.read_bytes()
            lines[vkey(agent, text)] = {"b64": base64.b64encode(data).decode(), "mime": "audio/wav" if path.suffix == ".wav" else "audio/mpeg"}
        except Exception:  # noqa: BLE001
            failed += 1
    ver = hashlib.sha1("".join(sorted(lines)).encode() + str(sum(len(v["b64"]) for v in lines.values())).encode()).hexdigest()[:12]
    PACK.parent.mkdir(parents=True, exist_ok=True)
    PACK.write_text(json.dumps({"version": ver, "lines": lines}), encoding="utf-8")
    return {"lines": len(lines), "failed": failed, "version": ver}


def build_soon() -> None:
    threading.Thread(target=build, daemon=True).start()
