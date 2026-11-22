"""Real-world channels: e-mail (IMAP + SMTP) and WhatsApp (via the local bridge), plus the outbox policy."""
from __future__ import annotations

import email
import email.utils
import html
import imaplib
import json
import os
import re
import smtplib
import urllib.parse
import urllib.request
from datetime import datetime
from email.header import decode_header, make_header
from email.message import EmailMessage

from .config import settings
from .store import normalize_phone


# ---------------------------------------------------------------- e-mail
def email_ready() -> bool:
    return bool(settings.smtp_host and settings.smtp_user and settings.smtp_password)


def email_read_ready() -> bool:
    return bool(settings.imap_host and settings.smtp_user and settings.smtp_password)


def send_email(to: str, subject: str, body: str, reply_to_message_id: str = "", attachment: str = "") -> None:
    msg = EmailMessage()
    msg["From"] = settings.smtp_user
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = email.utils.formatdate(localtime=True)
    msg["Message-ID"] = email.utils.make_msgid()
    if reply_to_message_id:
        msg["In-Reply-To"] = reply_to_message_id
        msg["References"] = reply_to_message_id
    sig = f"\n\n{settings.email_signature}" if settings.email_signature else ""
    msg.set_content(body + sig)
    if attachment:
        import mimetypes
        from pathlib import Path
        path = Path(attachment)
        ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        maintype, _, subtype = ctype.partition("/")
        msg.add_attachment(path.read_bytes(), maintype=maintype, subtype=subtype, filename=path.name)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as smtp:
        smtp.starttls()
        smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)


def _hdr(value) -> str:
    try:
        return str(make_header(decode_header(value or "")))
    except Exception:  # noqa: BLE001
        return str(value or "")


def _text_of(msg: email.message.Message) -> str:
    parts = msg.walk() if msg.is_multipart() else [msg]
    plain, rich = "", ""
    for part in parts:
        if part.get_content_maintype() == "multipart" or part.get("Content-Disposition", "").startswith("attachment"):
            continue
        payload = part.get_payload(decode=True) or b""
        text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
        if part.get_content_type() == "text/plain" and not plain:
            plain = text
        elif part.get_content_type() == "text/html" and not rich:
            rich = html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(script|style).*?</\1>", "", text)))
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n\n", plain or rich)).strip()


def _imap() -> imaplib.IMAP4_SSL:
    box = imaplib.IMAP4_SSL(settings.imap_host)
    box.login(settings.smtp_user, settings.smtp_password)
    box.select("INBOX", readonly=True)  # read-only: agents never mark mail as read or delete it
    return box


def list_inbox(limit: int = 15, unread_only: bool = True, since_uid: int = 0) -> list[dict]:
    box = _imap()
    try:
        criteria = "UNSEEN" if unread_only else "ALL"
        if since_uid:
            criteria = f"UID {since_uid + 1}:* {criteria}"
        _, data = box.uid("search", None, criteria)
        uids = [int(u) for u in (data[0] or b"").split() if int(u) > since_uid][-limit:]
        out = []
        for uid in reversed(uids):
            _, msg_data = box.uid("fetch", str(uid), "(BODY.PEEK[])")
            raw = next((p[1] for p in msg_data if isinstance(p, tuple)), b"")
            m = email.message_from_bytes(raw)
            body = _text_of(m)
            out.append({"uid": uid, "from": _hdr(m["From"]), "subject": _hdr(m["Subject"]), "date": m["Date"],
                        "message_id": m["Message-ID"] or "", "snippet": body[:300]})
        return out
    finally:
        box.logout()


def recent_mail(days: int = 7, limit: int = 200) -> list[dict]:
    """All mail from the last `days` days (read-only), with a longer text excerpt."""
    from datetime import date, timedelta
    box = _imap()
    try:
        since = (date.today() - timedelta(days=days)).strftime("%d-%b-%Y")
        _, data = box.uid("search", None, f"SINCE {since}")
        uids = [int(u) for u in (data[0] or b"").split()][-limit:]
        out = []
        for uid in reversed(uids):
            _, msg_data = box.uid("fetch", str(uid), "(BODY.PEEK[])")
            raw = next((p[1] for p in msg_data if isinstance(p, tuple)), b"")
            m = email.message_from_bytes(raw)
            out.append({"uid": uid, "from": _hdr(m["From"]), "subject": _hdr(m["Subject"]), "date": m["Date"],
                        "body": _text_of(m)[:2500]})
        return out
    finally:
        box.logout()


def read_email(uid: int) -> dict:
    box = _imap()
    try:
        _, msg_data = box.uid("fetch", str(uid), "(BODY.PEEK[])")
        raw = next((p[1] for p in msg_data if isinstance(p, tuple)), b"")
        if not raw:
            raise ValueError(f"No e-mail with uid {uid}")
        m = email.message_from_bytes(raw)
        return {"uid": uid, "from": _hdr(m["From"]), "to": _hdr(m["To"]), "subject": _hdr(m["Subject"]),
                "date": m["Date"], "message_id": m["Message-ID"] or "", "body": _text_of(m)[:15000]}
    finally:
        box.logout()


# ---------------------------------------------------------------- WhatsApp bridge
def whatsapp_ready() -> bool:
    return settings.whatsapp_enabled


def _bridge(path: str, payload: dict | None = None, timeout: int = 30):
    url = settings.whatsapp_bridge_url.rstrip("/") + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json",
                                                          "X-Jarvis-Token": settings.bridge_token})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read() or b"{}")


def whatsapp_status() -> dict:
    if not whatsapp_ready():
        return {"ready": False, "reason": "WhatsApp is off (set JARVIS_WHATSAPP=on)"}
    try:
        return _bridge("/status", timeout=5)
    except Exception as exc:  # noqa: BLE001
        return {"ready": False, "reason": f"bridge not reachable ({exc})"}


def send_whatsapp(phone: str, text: str) -> None:
    _bridge("/send", {"to": normalize_phone(phone), "text": text})


def whatsapp_chats(limit: int = 15, unread_only: bool = False) -> list:
    q = urllib.parse.urlencode({"limit": limit, "unread": int(unread_only)})
    return _bridge(f"/chats?{q}")


def whatsapp_messages(chat_id: str, limit: int = 20) -> list:
    q = urllib.parse.urlencode({"chat": chat_id, "limit": limit})
    return _bridge(f"/messages?{q}")


# ---------------------------------------------------------------- outbox policy & dispatch
def is_owner(channel: str, recipient: str) -> bool:
    if channel == "telegram":  # the bot only ever talks to the owner
        return True
    if channel == "email":
        mine = {a.strip().lower() for a in (settings.report_email_to, settings.smtp_user) if a}
        return recipient.strip().lower() in mine
    return bool(settings.owner_whatsapp) and normalize_phone(recipient) == normalize_phone(settings.owner_whatsapp)


def initial_status(store, channel: str, recipient: str) -> str:
    """'approved' if this message may go out without asking the owner, else 'pending'."""
    if channel == "computer":  # shell commands always need the owner's OK unless explicitly allowed
        return "approved" if os.environ.get("JARVIS_SHELL", "").lower() == "auto" else "pending"
    if is_owner(channel, recipient) or settings.autonomy == "full":
        return "approved"
    if settings.autonomy == "trusted":
        contact = store.contact_for(channel, recipient)
        if contact and contact["trusted"]:
            return "approved"
    return "pending"


def deliver(store, bus, msg: dict) -> bool:
    """Send one approved outbox message. Updates its status. Returns True on success."""
    try:
        if msg["channel"] == "email":
            if not email_ready():
                raise RuntimeError("e-mail is not set up (JARVIS_SMTP_* in .env)")
            args = (msg["recipient"], msg["subject"] or "(no subject)", msg["body"], msg["reply_to"])
            send_email(*args, attachment=msg["attachment"]) if msg.get("attachment") else send_email(*args)
        elif msg["channel"] == "computer":
            from . import devices
            output = devices.run_command(msg["body"])
            store.set_message(msg["id"], result=output)
            msg = {**msg, "result": output}
        elif msg["channel"] == "telegram":
            from . import telegram as tg
            if not tg.ready():
                raise RuntimeError("Telegram is not linked")
            tg.send(msg["body"])
            from .speech import announce
            announce(bus, msg["agent"], msg["body"].replace("⏰", "").strip())  # reminders are spoken too
        elif msg["channel"] == "whatsapp":
            if not whatsapp_ready():
                raise RuntimeError("WhatsApp is off (JARVIS_WHATSAPP=on and run the bridge)")
            send_whatsapp(msg["recipient"], msg["body"])
        else:
            raise RuntimeError(f"unknown channel {msg['channel']}")
    except Exception as exc:  # noqa: BLE001
        store.set_message(msg["id"], status="failed", error=str(exc)[:500])
        bus.log(msg["agent"], f"✉ #{msg['id']} to {msg['recipient_name'] or msg['recipient']} failed: {exc}", "error")
        bus.publish({"type": "data", "what": "outbox"})
        return False
    store.set_message(msg["id"], status="sent", sent_at=datetime.now(settings.tz).isoformat(timespec="seconds"))
    if msg["channel"] == "computer":
        bus.log(msg["agent"], f"⌘ Ran #{msg['id']}: {msg['body'][:80]} → {msg.get('result', '')[:200]}", "job")
    else:
        bus.log(msg["agent"], f"✉ Sent {msg['channel']} to {msg['recipient_name'] or msg['recipient']}", "job")
    bus.publish({"type": "data", "what": "outbox"})
    return True


def send_whatsapp_file(phone: str, path: str, caption: str = "") -> None:
    _bridge("/send-file", {"to": normalize_phone(phone), "path": path, "caption": caption}, timeout=60)
