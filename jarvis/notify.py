"""Deliver reports and alerts to the owner: WhatsApp (to yourself), e-mail and/or Telegram. All optional."""
from __future__ import annotations

import json
import urllib.request

from . import channels as ch
from .config import settings


def channels() -> list[str]:
    out = []
    if ch.whatsapp_ready() and settings.owner_whatsapp:
        out.append("whatsapp")
    if ch.email_ready() and settings.report_email_to:
        out.append("email")
    if settings.telegram_token and settings.telegram_chat_id:
        out.append("telegram")
    return out


def send_telegram(text: str) -> None:
    url = f"https://api.telegram.org/bot{settings.telegram_token}/sendMessage"
    for i in range(0, len(text), 3900):  # Telegram message limit is 4096 chars
        data = json.dumps({"chat_id": settings.telegram_chat_id, "text": text[i:i + 3900]}).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=30).read()


def notify_owner(subject: str, body: str, *, short: bool = False) -> list[str]:
    """Send to every configured channel. short=True: WhatsApp/Telegram only (alerts, approvals)."""
    results = []
    active = channels()
    if "whatsapp" in active:
        try:
            ch.send_whatsapp(settings.owner_whatsapp, f"🤖 *{subject}*\n\n{body}"[:60000])
            results.append("whatsapp: sent")
        except Exception as exc:  # noqa: BLE001
            results.append(f"whatsapp: failed ({exc})")
    if "email" in active and not short:
        try:
            ch.send_email(settings.report_email_to, subject, body)
            results.append("email: sent")
        except Exception as exc:  # noqa: BLE001
            results.append(f"email: failed ({exc})")
    if "telegram" in active:
        try:
            send_telegram(f"{subject}\n\n{body}")
            results.append("telegram: sent")
        except Exception as exc:  # noqa: BLE001
            results.append(f"telegram: failed ({exc})")
    return results or ["no channel configured - saved to dashboard only"]
