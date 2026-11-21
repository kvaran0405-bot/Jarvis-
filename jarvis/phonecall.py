"""JARVIS rings your real phone for urgent things (optional, via Twilio).

Twilio is a paid calling service (roughly US$1-2 a month for a number plus a few cents a minute). Without it,
urgent alerts go to Telegram only. The call speaks the alert in a British voice; then call JARVIS back from the
phone app (📞 Call JARVIS) to talk it through.
"""
from __future__ import annotations

import base64
import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from xml.sax.saxutils import escape

from .config import settings


def ready() -> bool:
    return bool(settings.twilio_sid and settings.twilio_token and settings.twilio_from and settings.owner_phone)


def _in_quiet_hours(now: datetime) -> bool:
    from .speech import in_quiet_hours
    return in_quiet_hours(now)


def twiml(message: str) -> str:
    owner = escape(settings.owner_name)
    msg = escape(message[:600])
    voice = escape(settings.call_voice)
    return (f'<Response><Pause length="1"/><Say voice="{voice}">Hello {owner}, this is JARVIS with something urgent.</Say>'
            f'<Pause length="1"/><Say voice="{voice}">{msg}</Say><Pause length="2"/>'
            f'<Say voice="{voice}">Once more: {msg}</Say><Pause length="1"/>'
            f'<Say voice="{voice}">The details are on Telegram. Goodbye.</Say></Response>')


def place_call(message: str) -> str:
    url = f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_sid}/Calls.json"
    data = urllib.parse.urlencode({"To": settings.owner_phone, "From": settings.twilio_from,
                                   "Twiml": twiml(message)}).encode()
    auth = base64.b64encode(f"{settings.twilio_sid}:{settings.twilio_token}".encode()).decode()
    req = urllib.request.Request(url, data=data, headers={"Authorization": f"Basic {auth}"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read()).get("sid", "")


def decide(store, level: str) -> tuple[bool, str]:
    """May JARVIS ring the phone right now? Returns (allowed, reason)."""
    now = datetime.now(settings.tz)
    last = store.get("call:last")
    if last and now - datetime.fromisoformat(last) < timedelta(minutes=settings.call_gap_minutes):
        return False, f"already called in the last {settings.call_gap_minutes} minutes"
    if _in_quiet_hours(now) and level != "critical":
        return False, f"quiet hours ({settings.quiet_hours}); only critical things ring at night"
    return True, ""
