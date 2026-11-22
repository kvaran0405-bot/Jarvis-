"""Lecture & meeting recorder.

Record on the laptop's microphone ("Jarvis, record this lecture"), or hand JARVIS a recording made on the phone
(upload it in the app, or send the audio file to the Telegram bot). The recording is transcribed on the laptop
for free with faster-whisper, then ATHENA turns it into notes: summary, key points, things to revise, and to-dos
and deadlines (added as tasks and calendar events). Everything lands in Notes and on Telegram.
"""
from __future__ import annotations

import os
import re
import threading
import wave
from datetime import datetime
from pathlib import Path

from .config import ROOT, settings

FOLDER = ROOT / "data" / "lectures"
RATE = 16000                    # speech only needs 16 kHz mono: ~115 MB per hour as WAV
MAX_TRANSCRIPT_FOR_AI = 150_000  # characters (about 3 hours of speech)

_engine = None
_rec: "Recorder | None" = None
_rec_lock = threading.Lock()


def attach(engine) -> None:
    global _engine
    _engine = engine


def can_record() -> tuple[bool, str]:
    try:
        import sounddevice  # noqa: F401
    except Exception:  # noqa: BLE001 - ImportError, or PortAudio missing on Linux
        return False, "the recording part isn't installed - run: pip install sounddevice numpy"
    return True, ""


def _slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-")[:40] or "recording"


class Recorder:
    """Records the default microphone to a WAV file on a background audio thread."""

    def __init__(self, lecture_id: int, path: Path):
        import sounddevice as sd
        self.lecture_id, self.path = lecture_id, path
        self.started = datetime.now(settings.tz)
        self.frames = 0
        self._wav = wave.open(str(path), "wb")
        self._wav.setnchannels(1)
        self._wav.setsampwidth(2)
        self._wav.setframerate(RATE)
        self._stream = sd.RawInputStream(samplerate=RATE, channels=1, dtype="int16", callback=self._on_audio)
        self._stream.start()

    def _on_audio(self, data, frames, _time, _status) -> None:
        self._wav.writeframes(bytes(data))
        self.frames += frames

    def stop(self) -> int:
        self._stream.stop()
        self._stream.close()
        self._wav.close()
        return int(self.frames / RATE)

    @property
    def seconds(self) -> int:
        return int(self.frames / RATE)


# ---------------------------------------------------------------- start / stop
def start(store, bus, title: str = "", course: str = "") -> dict:
    global _rec
    ok, why = can_record()
    if not ok:
        return {"error": f"I can't record on this laptop yet: {why}."}
    with _rec_lock:
        if _rec is not None:
            lec = store.get_lecture(_rec.lecture_id)
            return {"error": f"Already recording '{lec['title'] if lec else '?'}' ({_rec.seconds // 60} min so far). "
                             "Stop it first."}
        now = datetime.now(settings.tz)
        title = title.strip() or f"{course or 'Lecture'} {now:%d %b %H:%M}"
        FOLDER.mkdir(parents=True, exist_ok=True)
        path = FOLDER / f"{now:%Y%m%d-%H%M}-{_slug(title)}.wav"
        lid = store.add_lecture(title, course, str(path), "recording")
        from . import clap
        clap.pause(True)   # the recorder gets the microphone to itself
        try:
            _rec = Recorder(lid, path)
        except Exception as exc:  # noqa: BLE001 - no microphone, permission denied, ...
            store.update_lecture(lid, status="failed", error=str(exc)[:300])
            clap.pause(False)
            return {"error": f"The microphone didn't start: {exc}"}
    bus.log("ATHENA", f"🔴 Recording '{title}'", "job")
    bus.publish({"type": "data", "what": "lectures"})
    return {"recording": True, "lecture_id": lid, "title": title,
            "tip": "Keep the laptop near the speaker and plugged in. Say 'stop recording' when it ends."}


def stop(store, bus) -> dict:
    global _rec
    with _rec_lock:
        if _rec is None:
            return {"error": "Nothing is being recorded."}
        rec, _rec = _rec, None
    seconds = rec.stop()
    from . import clap
    clap.pause(False)
    store.update_lecture(rec.lecture_id, duration_s=seconds, status="transcribing")
    bus.log("ATHENA", f"⏹ Recording stopped ({seconds // 60} min). Transcribing on the laptop…", "job")
    bus.publish({"type": "data", "what": "lectures"})
    threading.Thread(target=process, args=(store, bus, rec.lecture_id), daemon=True).start()
    lec = store.get_lecture(rec.lecture_id)
    return {"stopped": True, "lecture_id": rec.lecture_id, "title": lec["title"], "minutes": round(seconds / 60, 1),
            "next": "Transcribing now; notes arrive on Telegram and in Notes when ready (roughly a tenth of the "
                    "recording's length)."}


def recording_status(store) -> dict:
    with _rec_lock:
        if _rec is None:
            return {"recording": False}
        lec = store.get_lecture(_rec.lecture_id)
        return {"recording": True, "lecture_id": _rec.lecture_id, "title": lec["title"] if lec else "",
                "seconds": _rec.seconds}


def add_recording(store, bus, path: Path, title: str = "", course: str = "") -> int:
    """A recording made elsewhere (phone upload, Telegram audio): transcribe and summarise it in the background."""
    title = title.strip() or f"Recording {datetime.now(settings.tz):%d %b %H:%M}"
    lid = store.add_lecture(title, course, str(path), "transcribing")
    bus.log("ATHENA", f"📥 Got recording '{title}'. Transcribing on the laptop…", "job")
    bus.publish({"type": "data", "what": "lectures"})
    threading.Thread(target=process, args=(store, bus, lid), daemon=True).start()
    return lid


def receive(path: Path, title: str = "", course: str = "") -> int:
    """add_recording with JARVIS's own store and bus (for callers that don't hold them, like the Telegram bot)."""
    return add_recording(_engine.store, _engine.bus, path, title, course)


def new_upload_path(filename: str) -> Path:
    FOLDER.mkdir(parents=True, exist_ok=True)
    suffix = Path(filename).suffix.lower()
    if suffix not in (".wav", ".mp3", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".webm", ".mp4", ".flac", ".amr", ".3gp"):
        suffix = ".m4a"
    return FOLDER / f"{datetime.now(settings.tz):%Y%m%d-%H%M%S}-{_slug(Path(filename).stem)}{suffix}"


# ---------------------------------------------------------------- transcribe + summarise
def _stamp(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60:02d}:{s % 60:02d}"


def process(store, bus, lecture_id: int) -> None:
    from . import stt
    lec = store.get_lecture(lecture_id)
    if not lec:
        return
    try:
        if not stt.available():
            raise RuntimeError("the speech part (faster-whisper) isn't installed")
        last = [0.0]

        def progress(frac: float) -> None:
            if frac - last[0] >= 0.25:
                last[0] = frac
                bus.log("ATHENA", f"Transcribing '{lec['title']}': {int(frac * 100)}%", "job")

        segs, duration = stt.transcribe_long(lec["audio_path"], os.environ.get("JARVIS_LECTURE_WHISPER", ""), progress)
        if not segs:
            raise RuntimeError("I couldn't hear any speech in the recording")
        transcript = "\n".join(f"[{_stamp(t)}] {text}" for t, text in segs)
        store.update_lecture(lecture_id, transcript=transcript, duration_s=int(duration or lec["duration_s"] or 0),
                             status="summarising")
        bus.publish({"type": "data", "what": "lectures"})
        summarise(store, bus, lecture_id)
    except Exception as exc:  # noqa: BLE001 - tell the owner rather than fail silently
        store.update_lecture(lecture_id, status="failed", error=str(exc)[:300])
        bus.log("ATHENA", f"Lecture '{lec['title']}' failed: {exc}", "error")
        _tell(f"⚠️ I couldn't process the recording '{lec['title']}': {exc}")
        bus.publish({"type": "data", "what": "lectures"})


PROMPT = """A recording has just been transcribed: "{title}"{course} ({minutes} min). Turn it into study notes.

Write Markdown with exactly these sections:
## Summary - 4-6 sentences on what it covered.
## Key points - the important ideas, definitions, formulas and examples (bullets, with [mm:ss] timestamps).
## Exam hints - anything the speaker stressed, repeated, or said would be tested.
## To-dos & deadlines - assignments, readings, dates mentioned (or "None mentioned").
## Questions to review - 3-5 self-test questions with short answers.

Also: create a task with `add_task` (area academic, with a due date if one was said) for every to-do, and a calendar
event with `add_event` for every exam, deadline or class change with a date. Don't publish a report or message
anyone. Your final answer must be only the Markdown notes.

Transcript:
{transcript}"""


def summarise(store, bus, lecture_id: int) -> str:
    from . import brain
    lec = store.get_lecture(lecture_id)
    minutes = round((lec["duration_s"] or 0) / 60)
    if _engine is None or brain.pick(store, background=True) is None:
        store.update_lecture(lecture_id, status="transcribed")
        note_id = _save_note(store, lec, "")
        _tell(f"📝 Transcribed '{lec['title']}' ({minutes} min) - saved to Notes. I'm paused, so the summary "
              f"waits: say 'summarise lecture {lecture_id}' when you resume.", transcript_of=lec)
        store.update_lecture(lecture_id, note_id=note_id)
        bus.publish({"type": "data", "what": "lectures"})
        return "transcribed (summary waiting - AI is paused)"
    transcript = lec["transcript"]
    if len(transcript) > MAX_TRANSCRIPT_FOR_AI:
        transcript = transcript[:MAX_TRANSCRIPT_FOR_AI] + "\n[... transcript cut here for length ...]"
    course = f" for {lec['course']}" if lec["course"] else ""
    notes = _engine.run("ATHENA", PROMPT.format(title=lec["title"], course=course, minutes=minutes,
                                                transcript=transcript), background=True)
    if notes.startswith(("⚠", "⏸")) or "## " not in notes:
        store.update_lecture(lecture_id, status="transcribed", error=notes[:300])
        _save_note(store, lec, "")
        _tell(f"📝 Transcribed '{lec['title']}', but the summary didn't work: {notes[:300]}\n"
              f"Say 'summarise lecture {lecture_id}' to try again.", transcript_of=lec)
        bus.publish({"type": "data", "what": "lectures"})
        return "transcribed (summary failed)"
    note_id = _save_note(store, lec, notes)
    store.update_lecture(lecture_id, summary=notes, status="ready", note_id=note_id, error="")
    bus.log("ATHENA", f"📚 Notes ready: {lec['title']}", "report")
    bus.publish({"type": "data", "what": "lectures"})
    bus.publish({"type": "data", "what": "tasks"})
    _tell(f"📚 Notes ready: {lec['title']} ({minutes} min)\n\n{notes}", transcript_of=lec)
    from .speech import announce
    announce(bus, "ATHENA", f"[cheerful] Your notes for {lec['title']} are ready Sir.", phone=False)
    return "ready"


def _save_note(store, lec: dict, notes: str) -> int:
    body = (notes + "\n\n---\n" if notes else "") + "## Transcript\n" + lec["transcript"]
    title = f"Lecture: {lec['title']}" if notes else f"Lecture transcript: {lec['title']}"
    if lec.get("note_id"):
        store.execute("UPDATE notes SET title = ?, body = ? WHERE id = ?", (title, body, lec["note_id"]))
        return lec["note_id"]
    return store.add_note(title, body, tags=f"lecture,{lec['course']}".strip(","), agent="ATHENA")


def _tell(text: str, transcript_of: dict | None = None) -> None:
    from . import telegram as tg
    if not tg.ready():
        return
    try:
        tg.send(text)
        if transcript_of and transcript_of.get("transcript"):
            FOLDER.mkdir(parents=True, exist_ok=True)
            txt = FOLDER / f"{_slug(transcript_of['title'])}-transcript.txt"
            txt.write_text(transcript_of["transcript"], encoding="utf-8")
            tg.send_file(str(txt), caption="Full transcript")
    except Exception:  # noqa: BLE001 - Telegram hiccup; it's all in Notes anyway
        pass
