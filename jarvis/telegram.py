"""Two-way Telegram: your private remote control for JARVIS.

The bot long-polls Telegram (no public server or port forwarding needed). Only your own chat is obeyed.
Pairing: the first time, send `/start <code>` to your bot; the code is shown in the dashboard (Autopilot tab)
and in the terminal. You can also set JARVIS_TELEGRAM_CHAT_ID directly.
"""
from __future__ import annotations

import json
import mimetypes
import secrets
import tempfile
import threading
import urllib.request
import uuid
from pathlib import Path
from typing import Callable

from .config import settings

_store = None  # attached at startup so the paired chat id can be stored


def attach(store) -> None:
    global _store
    _store = store
    if store.get("telegram:pair_code") is None:
        store.set("telegram:pair_code", f"{secrets.randbelow(900000) + 100000}")


def enabled() -> bool:
    return bool(settings.telegram_token)


def chat_id() -> str:
    if settings.telegram_chat_id:
        return settings.telegram_chat_id
    return str(_store.get("telegram:chat_id", "") or "") if _store else ""


def ready() -> bool:
    return enabled() and bool(chat_id())


def pair_code() -> str:
    return str(_store.get("telegram:pair_code", "")) if _store else ""


# ---------------------------------------------------------------- Telegram Bot API
def api(method: str, http_timeout: int = 30, **params):
    url = f"https://api.telegram.org/bot{settings.telegram_token}/{method}"
    req = urllib.request.Request(url, data=json.dumps(params).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=http_timeout) as resp:
        data = json.loads(resp.read())
    if not data.get("ok"):
        raise RuntimeError(data.get("description", "Telegram error"))
    return data["result"]


def api_file(method: str, field: str, path: str, **params):
    """multipart/form-data upload (photos, documents, audio)."""
    boundary = uuid.uuid4().hex
    body = bytearray()
    for k, v in params.items():
        body += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    p = Path(path)
    ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    body += (f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{p.name}"\r\n'
             f"Content-Type: {ctype}\r\n\r\n").encode() + p.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    url = f"https://api.telegram.org/bot{settings.telegram_token}/{method}"
    req = urllib.request.Request(url, data=bytes(body),
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


def send(text: str, buttons: list[list[tuple[str, str]]] | None = None, to: str | None = None) -> None:
    target = to or chat_id()
    chunks = [text[i:i + 3900] for i in range(0, len(text), 3900)] or [""]
    for i, chunk in enumerate(chunks):
        params = {"chat_id": target, "text": chunk, "disable_web_page_preview": True}
        if buttons and i == len(chunks) - 1:
            params["reply_markup"] = {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row]
                                                          for row in buttons]}
        api("sendMessage", **params)


def send_file(path: str, caption: str = "") -> None:
    is_image = Path(path).suffix.lower() in (".png", ".jpg", ".jpeg", ".webp")
    api_file("sendPhoto" if is_image else "sendDocument", "photo" if is_image else "document", path,
             chat_id=chat_id(), caption=caption[:1000])


def send_voice(mp3_path: str) -> None:
    try:
        api_file("sendVoice", "voice", mp3_path, chat_id=chat_id())
    except Exception:  # noqa: BLE001 - older clients: fall back to a playable audio file
        api_file("sendAudio", "audio", mp3_path, chat_id=chat_id())


def download(file_id: str, dest: Path) -> Path:
    info = api("getFile", file_id=file_id)
    url = f"https://api.telegram.org/file/bot{settings.telegram_token}/{info['file_path']}"
    with urllib.request.urlopen(url, timeout=60) as resp:
        dest.write_bytes(resp.read())
    return dest


def approval_buttons(msg_id: int) -> list[list[tuple[str, str]]]:
    return [[("✅ Send", f"ok:{msg_id}"), ("❌ Cancel", f"no:{msg_id}")]]


# ---------------------------------------------------------------- the bot loop
class Bot:
    """Receives your messages, voice notes and button taps.
    `on_text(text, voice) -> reply`, `on_decision(id, yes) -> reply`."""

    def __init__(self, on_text: Callable[..., str], on_decision: Callable[[int, bool], str], log: Callable,
                 on_reply: Callable[[int, int | None], str] | None = None,
                 on_proposal: Callable[[int, bool], str] | None = None):
        self.on_text, self.on_decision, self.log, self.on_reply = on_text, on_decision, log, on_reply
        self.on_proposal = on_proposal
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if not enabled() or self._thread:
            return
        self._thread = threading.Thread(target=self._run, daemon=True, name="jarvis-telegram")
        self._thread.start()
        if not chat_id():
            print(f"Telegram: send  /start {pair_code()}  to your bot to link it.")

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        offset = _store.get("telegram:offset", 0) if _store else 0
        while not self._stop.is_set():
            try:
                updates = api("getUpdates", http_timeout=70, offset=offset, timeout=50)
            except Exception as exc:  # noqa: BLE001 - network hiccup, bad token...
                self.log(f"Telegram connection problem: {exc}")
                self._stop.wait(15)
                continue
            for upd in updates:
                offset = upd["update_id"] + 1
                if _store:
                    _store.set("telegram:offset", offset)
                try:
                    self.handle(upd)
                except Exception as exc:  # noqa: BLE001
                    self.log(f"Telegram update failed: {exc}")

    def handle(self, upd: dict) -> None:
        if "callback_query" in upd:
            cq = upd["callback_query"]
            if str(cq["message"]["chat"]["id"]) != chat_id():
                return
            action, _, rest = cq.get("data", "").partition(":")
            api("answerCallbackQuery", callback_query_id=cq["id"])
            api("editMessageReplyMarkup", chat_id=chat_id(), message_id=cq["message"]["message_id"],
                reply_markup={"inline_keyboard": []})
            if rest.isdigit() and action in ("ok", "no"):
                send(self.on_decision(int(rest), action == "ok"))
            elif action in ("pa", "pn") and rest.isdigit() and self.on_proposal:   # proposal yes / no
                send(self.on_proposal(int(rest), action == "pa"))
            elif action in ("rp", "ri") and self.on_reply:   # suggested reply chosen / ignored
                sid, _, opt = rest.partition(":")
                if sid.isdigit():
                    send(self.on_reply(int(sid), int(opt) if action == "rp" and opt.isdigit() else None))
            return

        msg = upd.get("message") or {}
        text = (msg.get("text") or "").strip()
        sender = str(msg.get("chat", {}).get("id", ""))
        if msg.get("voice") and sender and sender == chat_id():
            self.handle_voice(msg["voice"])
            return
        if not text or not sender:
            return
        if not chat_id():  # not paired yet: only accept the pairing code
            if text == f"/start {pair_code()}":
                _store.set("telegram:chat_id", sender)
                send("✅ Linked. I'm JARVIS - text me anything, any time. Try: What's on my plate today?", to=sender)
                self.log("Telegram linked to your account")
            return
        if sender != chat_id():
            return  # strangers are ignored
        if text.startswith("/start") or text == "/help":
            send("Text me orders like:\n• What's on my plate today?\n• Remind me at 5pm to call the bank\n"
                 "• Send me a screenshot of my laptop\n• ZEUS, find 5 internships tonight\n"
                 "• pending - see what's waiting for your OK\n\n"
                 "Save your Claude plan:\n• /pause  or  pause for 3 hours - I use no AI at all\n"
                 "• /saver - run on free Gemini only\n• /resume - back to normal\n• /status - which brain I'm using")
            return
        api("sendChatAction", chat_id=chat_id(), action="typing")
        send(self.on_text(text, voice=False))

    def handle_voice(self, voice_note: dict) -> None:
        """Voice note in -> transcribe on this laptop -> agent -> text + spoken reply."""
        from . import stt
        from . import voice as tts
        if not stt.available():
            send("🎙 To understand voice notes, run this once on the laptop:  pip install faster-whisper")
            return
        api("sendChatAction", chat_id=chat_id(), action="typing")
        tmp = Path(tempfile.gettempdir()) / f"jarvis-voice-{voice_note['file_unique_id']}.ogg"
        try:
            download(voice_note["file_id"], tmp)
            heard = stt.transcribe(str(tmp))
        finally:
            tmp.unlink(missing_ok=True)
        if not heard:
            send("🎙 I couldn't make that out - try again?")
            return
        reply = self.on_text(heard, voice=True)
        send(f"🎙 “{heard}”\n\n{reply}")
        if tts.enabled():
            api("sendChatAction", chat_id=chat_id(), action="record_voice")
            from .agents import AGENTS
            prefix, _, rest = reply.partition(":")
            agent, spoken = (prefix, rest) if prefix in AGENTS and rest else ("JARVIS", reply)
            send_voice(str(tts.synthesize(agent, spoken)))

