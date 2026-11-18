"""Deliver reports to the owner: e-mail (SMTP) and/or Telegram. Both optional."""
from __future__ import annotations

import json
import smtplib
import urllib.request
from email.message import EmailMessage

from .config import settings


def channels() -> list[str]:
    out = []
    if settings.smtp_host and settings.report_email_to:
        out.append("email")
    if settings.telegram_token and settings.telegram_chat_id:
        out.append("telegram")
    return out


def send_email(subject: str, body: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.smtp_user or settings.report_email_to
    msg["To"] = settings.report_email_to
    msg.set_content(body)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
        smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)


def send_telegram(text: str) -> None:
    url = f"https://api.telegram.org/bot{settings.telegram_token}/sendMessage"
    for i in range(0, len(text), 3900):  # Telegram message limit is 4096 chars
        data = json.dumps({"chat_id": settings.telegram_chat_id, "text": text[i:i + 3900]}).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=30).read()


def notify_owner(subject: str, body: str) -> list[str]:
    """Send to every configured channel. Returns the channels that succeeded (or errors)."""
    results = []
    if "email" in channels():
        try:
            send_email(subject, body)
            results.append("email: sent")
        except Exception as exc:  # noqa: BLE001 - report, don't crash the agent
            results.append(f"email: failed ({exc})")
    if "telegram" in channels():
        try:
            send_telegram(f"{subject}\n\n{body}")
            results.append("telegram: sent")
        except Exception as exc:  # noqa: BLE001
            results.append(f"telegram: failed ({exc})")
    return results or ["no channel configured - report saved to dashboard only"]
