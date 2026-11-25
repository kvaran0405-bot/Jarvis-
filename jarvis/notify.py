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


def _held_path():
    from .config import ROOT
    return ROOT / "data" / "held_notifications.json"


def _load_held() -> list:
    import json
    try:
        return json.loads(_held_path().read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return []


def hold(subject: str, body: str, approve_id: int | None = None) -> None:
    import json
    p = _held_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    items = _load_held() + [{"subject": subject, "body": body, "approve_id": approve_id}]
    p.write_text(json.dumps(items[-60:]), encoding="utf-8")


def flush_held() -> int:
    """The owner's up: everything the team held overnight, as one message (approvals keep their own buttons)."""
    items = _load_held()
    if not items:
        return 0
    _held_path().unlink(missing_ok=True)
    plain = [i for i in items if not i.get("approve_id")]
    if plain:
        body = "\n\n".join(f"• {i['subject']}\n{i['body'][:600]}" for i in plain)
        notify_owner("🌅 While you slept", body, short=True, urgent=True)
    for i in items:
        if i.get("approve_id"):
            notify_owner(i["subject"], i["body"], short=True, approve_id=i["approve_id"], urgent=True)
    return len(items)


def notify_owner(subject: str, body: str, *, short: bool = False, approve_id: int | None = None, urgent: bool = False) -> list[str]:
    """Send to every configured channel. short=True: phone channels only (alerts, approvals).
    approve_id adds Send / Cancel buttons on Telegram. While the owner sleeps (quiet hours) it's held and arrives as
    one "while you slept" message when they wake; urgent=True goes through anyway."""
    from .speech import in_quiet_hours
    from .voice import strip_moods
    if not urgent and in_quiet_hours():
        hold(subject, body, approve_id)
        return ["held until you wake up"]
    subject, body = strip_moods(subject), strip_moods(body)
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
