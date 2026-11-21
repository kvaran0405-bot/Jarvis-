"""Deliver reports and alerts to the owner: WhatsApp (to yourself), e-mail and/or Telegram. All optional."""
from __future__ import annotations

from . import channels as ch
from . import telegram as tg
from .config import settings


def channels() -> list[str]:
    out = []
    if ch.whatsapp_ready() and settings.owner_whatsapp:
        out.append("whatsapp")
    if ch.email_ready() and settings.report_email_to:
        out.append("email")
    if tg.ready():
        out.append("telegram")
    return out


def notify_owner(subject: str, body: str, *, short: bool = False, approve_id: int | None = None) -> list[str]:
    """Send to every configured channel. short=True: phone channels only (alerts, approvals).
    approve_id adds Send / Cancel buttons on Telegram."""
    results = []
    active = channels()
    if "telegram" in active:
        try:
            tg.send(f"🤖 {subject}\n\n{body}", tg.approval_buttons(approve_id) if approve_id else None)
            results.append("telegram: sent")
        except Exception as exc:  # noqa: BLE001
            results.append(f"telegram: failed ({exc})")
    if "whatsapp" in active and not ("telegram" in active and short):
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
    return results or ["no channel configured - saved to dashboard only"]
