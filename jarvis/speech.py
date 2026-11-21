"""Agents speak up on their own: on the laptop (the JARVIS window says it out loud) and on your phone (a Telegram
voice note). Quiet hours keep the night silent unless something is critical."""
from __future__ import annotations

import threading
from datetime import datetime, time

from .config import settings


def in_quiet_hours(now: datetime | None = None) -> bool:
    now = now or datetime.now(settings.tz)
    try:
        start_s, end_s = settings.quiet_hours.split("-")
        start, end = time.fromisoformat(start_s.strip()), time.fromisoformat(end_s.strip())
    except ValueError:
        return False
    t = now.time()
    return (start <= t or t < end) if start > end else (start <= t < end)


def _voice_note(agent: str, text: str) -> None:
    from . import telegram as tg
    from . import voice
    try:
        tg.send_voice(str(voice.synthesize_for_phone(agent, text)))
    except Exception:  # noqa: BLE001 - the text message was already sent; a missing voice note is fine
        pass


def announce(bus, agent: str, text: str, *, kind: str = "say", critical: bool = False, phone: bool = True) -> bool:
    """Say `text` in `agent`'s voice. kind='ask' makes the laptop listen for a yes/no afterwards.
    Returns False when it stayed silent (turned off, or quiet hours)."""
    if not settings.proactive_voice or not text.strip():
        return False
    if in_quiet_hours() and not critical:
        return False
    bus.publish({"type": kind, "agent": agent, "say": text, "text": text})
    if phone and settings.telegram_voice:
        from . import telegram as tg
        from . import voice
        if tg.ready() and voice.enabled():
            threading.Thread(target=_voice_note, args=(agent, text), daemon=True).start()
    return True
