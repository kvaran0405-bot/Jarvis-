"""Two-way Telegram: your private remote control for JARVIS.

The bot long-polls Telegram (no public server or port forwarding needed). Only your own chat is obeyed.
Pairing: the first time, send `/start <code>` to your bot; the code is shown in the dashboard (Autopilot tab)
and in the terminal. You can also set JARVIS_TELEGRAM_CHAT_ID directly.
"""
from __future__ import annotations

import json
import mimetypes
import re
import secrets
import tempfile
import threading
import time
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


EMAIL_SETUP_RE = re.compile(r"^\s*(?:jarvis[,\s]+)?(?:set ?up|connect|link|add) (?:my )?(?:e-?mails?|gmail|inbox)\s*[.!]?\s*$", re.I)
EMAIL_STEPS = ("📧 Let's connect your Gmail (2 minutes):\n\n"
               "1. Open https://myaccount.google.com/apppasswords and sign in.\n"
               "   (If it says it's not available: turn on 2-Step Verification first at "
               "https://myaccount.google.com/signinoptions/twosv, then open the link again.)\n"
               "2. Type JARVIS as the name and tap Create. Google shows 16 letters.\n"
               "3. Send me ONE message with your Gmail address and those 16 letters, like:\n"
               "   you@gmail.com abcd efgh ijkl mnop\n\n"
               "I'll delete your message straight away, check it with Gmail, and restart. "
               "(This works for the next 15 minutes.)")


GEMINI_SETUP_RE = re.compile(r"^\s*(?:jarvis[,\s]+)?(?:set ?up|connect|add|link) (?:my |the |a )?(?:free )?gemini(?: key| api key)?\s*[.!]?\s*$", re.I)
GEMINI_STEPS = ("⚡ Free Gemini key (fast mode, Gemini voices, photo sorter), 1 minute:\n\n"
                "1. Open https://aistudio.google.com/apikey and sign in.\n"
                "2. Tap Create API key → pick any project → Create key → copy it.\n"
                "3. Paste the key here as one message.\n\n"
                "I'll delete your message straight away, test the key, and switch fast mode on. "
                "(This works for the next 15 minutes.)")


INSTALL_RE = re.compile(r"^\s*(?:jarvis[,\s]+)?(?:install|update|get|download|send me)(?: the| my)? (?:phone )?(?:app|apk)\s*[.!]?\s*$", re.I)
APK_URL = "https://github.com/kvaran0405-bot/Jarvis-/releases/latest/download/JARVIS.apk"
INSTALL_STEPS = ("📱 Newest JARVIS phone app\n\n"
                 "1. Play Store → your profile → Play Protect → ⚙ → turn OFF “Scan apps with Play Protect”.\n"
                 "2. Tap the app file below (or this link) → Install:\n" + APK_URL + "\n"
                 "   (If it says “App not installed”: uninstall the old JARVIS first, then tap again.)\n"
                 "3. Turn Play Protect scanning back ON. Open JARVIS → say “setup” → ALLOW NEXT.")


def send_app() -> None:
    """Steps + the newest APK. Attaches the file itself when the laptop can download it, else just the link."""
    send(INSTALL_STEPS)
    try:
        path = Path(tempfile.gettempdir()) / "JARVIS.apk"
        with urllib.request.urlopen(APK_URL, timeout=60) as r:
            data = r.read()
        if len(data) < 100_000 or data[:2] != b"PK":
            return   # not an app file (e.g. a sign-in page): the link above still works
        path.write_bytes(data)
        api_file("sendDocument", "document", str(path), chat_id=chat_id(), caption="JARVIS.apk: tap to install")
    except Exception:  # noqa: BLE001 - the link in the steps is enough
        pass


ONEMAP_STEPS = ("🚇 Real bus & MRT journeys (free, official Singapore map), 2 minutes:\n\n"
                "1. Open https://www.onemap.gov.sg/apidocs/register and register with your email (free).\n"
                "2. Confirm the email they send you and set a password.\n"
                "3. Send me ONE message: your OneMap email and password, like:\n"
                "   you@gmail.com yourpassword\n\n"
                "I'll delete your message straight away and check it works. (15 minutes to reply.)")
LTA_STEPS = ("🚌 Live bus arrivals (free, from LTA), 2 minutes:\n\n"
             "1. Open https://datamall.lta.gov.sg/content/datamall/en/request-for-api.html and request API access "
             "(free, personal use).\n"
             "2. LTA emails you an AccountKey (a long code).\n"
             "3. Paste that key here as one message.\n\n"
             "I'll delete your message straight away and check it works. (15 minutes to reply.)")


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
    from .voice import strip_moods
    text = strip_moods(text)   # mood tags are for the voice only
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
        self.on_update: Callable[[], str] | None = None
        self.on_email: Callable[[str, str], str] | None = None   # (gmail address, app password) -> result
        self._email_until = 0.0
        self.on_gemini: Callable[[str], str] | None = None       # (key) -> result
        self._gemini_until = 0.0
        self.on_transit: Callable[[str, dict], str] | None = None   # ("onemap"|"lta", values) -> result
        self.on_spoken: Callable[[str], None] | None = None   # say a reply out loud on the laptop
        self._transit_until = {"onemap": 0.0, "lta": 0.0}
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
        if sender and sender == chat_id():
            caption = (msg.get("caption") or "").strip()
            doc = msg.get("document") or {}
            audio = msg.get("audio") or msg.get("video_note") or (
                doc if (doc.get("mime_type") or "").startswith(("audio/", "video/")) else None)
            voice_note = msg.get("voice")
            # A long voice note, or one captioned "lecture"/"meeting", is a recording to take notes from.
            if voice_note and (voice_note.get("duration", 0) > 180 or re.search(r"lecture|meeting|class|record", caption, re.I)):
                audio = voice_note
            if audio:
                self.handle_recording(audio, caption)
                return
            if voice_note:
                self.handle_voice(voice_note)
                return
            dname = (doc.get("file_name") or "").lower()
            if doc and dname.endswith((".pdf", ".docx")) and re.search(r"\b(resume|cv|curriculum)\b", f"{caption.lower()} {dname}"):
                self.handle_resume(doc)
                return
            image = (msg.get("photo") or [None])[-1] or (
                doc if (doc.get("mime_type") or "").startswith("image/") else None)
            if image:
                self.handle_photo(image, caption)
                return
        if not text or not sender:
            return
        if not chat_id():  # not paired yet: only accept the pairing code
            if text == f"/start {pair_code()}":
                _store.set("telegram:chat_id", sender)
                send("✅ Linked. I'm JARVIS - text me anything, any time. Try: What's on my plate today?", to=sender)
                self.log("Telegram linked to your account")
            elif text.startswith("/start"):
                send("🔒 Send /start followed by the 6-digit code shown on your laptop "
                     "(JARVIS window → Autopilot tab), e.g.  /start 123456", to=sender)
            return
        if sender != chat_id():
            return  # strangers are ignored
        if text.startswith("/"):   # "/Update@MyJarvisBot " -> "/update"
            text = re.sub(r"@\w+", "", text.split()[0]).lower() + text[len(text.split()[0]):]
        if re.match(r"^\s*(?:jarvis[,\s]+)?(?:update|update now|update please|update yourself|update jarvis|get (?:the )?(?:newest|latest) version)\s*[.!]?\s*$",
                    text, re.I):
            text = "/update"
        if self.on_email and (text in ("/email", "/gmail") or EMAIL_SETUP_RE.match(text)):
            self._email_until = time.time() + 900
            send(EMAIL_STEPS)
            return
        if self._email_until > time.time() and "@" in text and self.on_email:
            # this message holds the app password: take it out of the chat at once, whatever happens next
            try:
                api("deleteMessage", chat_id=sender, message_id=msg.get("message_id"))
            except Exception:  # noqa: BLE001
                pass
            addr = re.search(r"[^\s@]+@[^\s@]+\.[a-z]{2,}", text, re.I)
            pw = re.search(r"(?<![a-z])([a-z]{4})\s?([a-z]{4})\s?([a-z]{4})\s?([a-z]{4})(?![a-z])",
                           text.replace(addr.group(0), " ") if addr else text, re.I)
            if not addr or not pw:
                send("🔒 I deleted that message to keep it private. Please send it again like this:\n"
                     "you@gmail.com abcd efgh ijkl mnop")
                return
            self._email_until = 0
            send("🔒 Got it and deleted your message. Checking with Gmail…")
            send(self.on_email(addr.group(0), "".join(pw.groups())))
            return
        if self.on_gemini and (text in ("/gemini", "/key", "/fast") or GEMINI_SETUP_RE.match(text)):
            self._gemini_until = time.time() + 900
            send(GEMINI_STEPS)
            return
        key = re.search(r"\b(AIza[0-9A-Za-z_\-]{30,}|AQ\.[0-9A-Za-z_.\-]{20,})", text)
        if self._gemini_until > time.time() and key and self.on_gemini:
            try:
                api("deleteMessage", chat_id=sender, message_id=msg.get("message_id"))
            except Exception:  # noqa: BLE001
                pass
            self._gemini_until = 0
            send("🔒 Got it and deleted your message. Testing the key…")
            send(self.on_gemini(key.group(1)))
            return
        if text in ("/installapp", "/apk", "/phoneapp") or INSTALL_RE.match(text):
            threading.Thread(target=send_app, daemon=True).start()
            return
        if self.on_transit and text in ("/onemap", "/lta", "/bus", "/transit"):
            which = "lta" if text in ("/lta", "/bus") else "onemap"
            self._transit_until[which] = time.time() + 900
            send(ONEMAP_STEPS if which == "onemap" else LTA_STEPS)
            return
        if self.on_transit and self._transit_until["onemap"] > time.time() and "@" in text:
            try:
                api("deleteMessage", chat_id=sender, message_id=msg.get("message_id"))
            except Exception:  # noqa: BLE001
                pass
            m = re.match(r"^\s*(\S+@\S+\.\S+)\s+(.+?)\s*$", text)
            if not m:
                send("🔒 Deleted that to keep it private. Send it as: your-email@gmail.com yourpassword")
                return
            self._transit_until["onemap"] = 0
            send("🔒 Got it and deleted your message. Checking with OneMap…")
            send(self.on_transit("onemap", {"email": m.group(1), "password": m.group(2)}))
            return
        if self.on_transit and self._transit_until["lta"] > time.time() and re.fullmatch(r"\s*[A-Za-z0-9+/=_-]{16,64}\s*", text):
            try:
                api("deleteMessage", chat_id=sender, message_id=msg.get("message_id"))
            except Exception:  # noqa: BLE001
                pass
            self._transit_until["lta"] = 0
            send("🔒 Got it and deleted your message. Checking with LTA…")
            send(self.on_transit("lta", {"key": text.strip()}))
            return
        if text == "/voicecheck":
            send(voice_check())
            return
        if text == "/update" and self.on_update:
            send(self.on_update())
            return
        if text in ("/app", "/call"):
            from .config import settings as cfg
            send(f"📱 Your JARVIS app: {cfg.app_url}/command-centre.html\n📞 Call JARVIS: {cfg.app_url}/call.html"
                 if cfg.app_url else "Set JARVIS_APP_URL in .env first (see README: 'JARVIS on your phone').")
            return
        if text.startswith("/start") or text == "/help":
            send("Text me orders like:\n• What's on my plate today?\n• Remind me at 5pm to call the bank\n"
                 "• Send me a screenshot of my laptop\n• ZEUS, find 5 internships tonight\n"
                 "• pending - see what's waiting for your OK\n\n"
                 "Save your Claude plan:\n• /pause  or  pause for 3 hours - I use no AI at all\n"
                 "• /saver - run on free Gemini only\n• /resume - back to normal\n• /status - which brain I'm using\n\n"
                 "📱 /app - open the JARVIS app   📞 /call - talk to me live\n"
                 "📱 /installapp - newest phone app\n📧 /email - connect your Gmail\n🚇 /onemap - real bus/MRT journeys\n🚌 /lta - live bus arrivals\n⚡ /gemini - free Gemini key (fast mode)\n🔎 /voicecheck - test voice notes   ⬆ update - get my newest version (laptop + phone)")
            return
        api("sendChatAction", chat_id=chat_id(), action="typing")
        reply = self.on_text(text, voice=False)
        send(reply)
        if settings.telegram_voice_replies == "always":
            self.voice_reply(reply)

    def handle_recording(self, audio: dict, caption: str = "") -> None:
        """An audio file / long voice note from the phone: transcribe it and write lecture notes."""
        from . import lectures
        from . import stt
        if not stt.available():
            send("🎙 I can't transcribe yet: the speech part isn't installed. Send /voicecheck for details.")
            return
        if audio.get("file_size", 0) > 20_000_000:
            send("📼 That file is over Telegram's 20 MB limit for bots. Upload it in the JARVIS app instead "
                 "(Autopilot tab → Lectures → Upload recording).")
            return
        name = audio.get("file_name") or "telegram-recording.ogg"
        path = lectures.new_upload_path(name)
        try:
            download(audio["file_id"], path)
        except Exception as exc:  # noqa: BLE001
            send(f"📼 I couldn't download that recording: {exc}"[:600])
            return
        title = re.sub(r"(?i)^(lecture|meeting|class|record(ing)?)[:\s-]*", "", caption).strip() or Path(name).stem
        lid = lectures.receive(path, title)
        mins = round(audio.get("duration", 0) / 60)
        send(f"📼 Got it{f' ({mins} min)' if mins else ''}. Transcribing on the laptop now; notes arrive here when "
             f"ready (lecture #{lid}).")

    def handle_resume(self, doc: dict) -> None:
        """ZEUS keeps the owner's CV: it's matched against every job and attached to e-mail applications."""
        from . import jobs
        path = Path(tempfile.gettempdir()) / ("jarvis-resume" + Path(doc.get("file_name") or "cv.pdf").suffix.lower())
        try:
            download(doc["file_id"], path)
            text = jobs.save_resume(path)
        except Exception as exc:  # noqa: BLE001
            send(f"ZEUS couldn't read that file: {exc}")
            return
        if not text.strip():
            send("ZEUS: got your CV file, but I can't read the text in it (is it a scanned image?). "
                 "Send a text PDF or a Word file if you can.")
            return
        send("ZEUS: resume locked in. 💪 I'll match every job against it and write the cover letters.\n"
             "Tell me the roles you want, your minimum salary and anything to avoid, e.g. "
             "'ZEUS, I want marketing or events roles, at least $2,800, no sales'. Hunting now...")
        threading.Thread(target=lambda: send("🎯 " + _hunt_line(jobs.hunt(_store))), daemon=True).start()

    def handle_photo(self, image: dict, caption: str = "") -> None:
        """Photo -> what's in it -> JARVIS acts (dates to the calendar, receipts to the money log, slides to notes)."""
        from . import vision
        api("sendChatAction", chat_id=chat_id(), action="typing")
        path = Path(tempfile.gettempdir()) / f"jarvis-photo-{image['file_unique_id']}.jpg"
        try:
            download(image["file_id"], path)
            seen = vision.describe(path, caption)
        except Exception as exc:  # noqa: BLE001
            send(f"📷 I couldn't look at that photo: {exc}"[:600])
            return
        finally:
            path.unlink(missing_ok=True)
        if "private document" in seen.lower()[:80]:
            send("📷 That looks like a private document (card, ID or password), so I've ignored it.")
            return
        prompt = (f"The owner sent a photo{f' with the message: “{caption}”' if caption else ''}.\n"
                  f"What it shows (read by the vision model):\n{seen}\n\n"
                  "Do what they'd want: if they asked something, answer it. Otherwise act on it - dates/events go on "
                  "the calendar, deadlines become tasks, a receipt is logged as spending, slide or whiteboard content "
                  "is saved as a note, a business card becomes a contact, an event photo gets 2 Instagram caption "
                  "options for the events business. Then confirm in one or two sentences.")
        reply = self.on_text(prompt, voice=False)
        send(f"📷 {reply}")

    def handle_voice(self, voice_note: dict) -> None:
        """Voice note in -> transcribe on this laptop -> agent -> text + spoken reply."""
        from . import stt
        if not stt.available() and not stt.gemini_hearing_on():
            send("🎙 I can't understand voice notes yet: the speech part isn't installed. Send /voicecheck for details.")
            return
        api("sendChatAction", chat_id=chat_id(), action="typing")
        tmp = Path(tempfile.gettempdir()) / f"jarvis-voice-{voice_note['file_unique_id']}.ogg"
        try:
            download(voice_note["file_id"], tmp)
            heard = stt.hear_best(str(tmp), stt.vocabulary(_store))[0]
        except Exception as exc:  # noqa: BLE001 - tell the owner instead of going quiet
            send(f"🎙 I couldn't process that voice note: {exc}"[:600])
            return
        finally:
            tmp.unlink(missing_ok=True)
        if not heard:
            send("🎙 I couldn't make that out - try again?")
            return
        reply = self.on_text(heard, voice=True)
        send(f"🎙 “{heard}”\n\n{reply}")
        from . import speaker
        where = speaker.get(_store) if _store is not None else "phone"
        if where == "phone":
            self.voice_reply(reply)          # the phone talks (voice note back)
        elif where == "laptop" and self.on_spoken:
            self.on_spoken(reply)            # the laptop says it out loud; the phone just shows the text

    def voice_reply(self, reply: str) -> None:
        """Send the reply as a voice note, in the speaking agent's voice."""
        from . import voice as tts
        if not tts.enabled():
            return
        try:
            api("sendChatAction", chat_id=chat_id(), action="record_voice")
            from .agents import AGENTS
            prefix, _, rest = reply.partition(":")
            agent, spoken = (prefix, rest) if prefix in AGENTS and rest else ("JARVIS", reply)
            send_voice(str(tts.synthesize_for_phone(agent, spoken)))
        except Exception as exc:  # noqa: BLE001
            send(f"🔇 I couldn't make the voice note: {exc}"[:600])



def voice_check() -> str:
    """/voicecheck: what works for voice notes, in plain words."""
    from . import stt
    from . import voice as tts
    lines = ["🔎 Voice check"]
    try:
        import faster_whisper  # noqa: F401
        lines.append("🎙 Understanding your voice notes: installed ✅ (the first one downloads a speech model, ~1 min)")
    except Exception as exc:  # noqa: BLE001
        lines.append(f"🎙 Understanding your voice notes: NOT installed ❌ ({type(exc).__name__}: {exc})"[:300])
    prov = tts.provider()
    lines.append(f"🔊 Voice for replies: {prov}" + (" ✅" if prov != "browser" else
                 " ❌ (no voice service, so I can't make voice notes)"))
    if prov != "browser":
        try:
            path = tts.synthesize_for_phone("JARVIS", "Voice check complete, Sir.")
            send_voice(str(path))
            lines.append("📨 Test voice note: sent above ✅")
        except Exception as exc:  # noqa: BLE001
            lines.append(f"📨 Test voice note failed ❌: {exc}"[:300])
    from .config import settings as cfg
    lines.append(f"Voice replies: {cfg.telegram_voice_replies} (always = every reply, voice = only when you send a "
                 "voice note). Change with JARVIS_TELEGRAM_VOICE_REPLIES in .env.")
    return "\n".join(lines)


def _hunt_line(out: dict) -> str:
    return (f"{out.get('ready', 0)} jobs lined up on your JOB HUNT screen."
            + (f" (Couldn't reach: {'; '.join(out['errors'])})" if out.get("errors") else ""))
