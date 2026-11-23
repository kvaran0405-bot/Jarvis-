"""Voice typing anywhere (laptop): hold Right Ctrl, talk, let go, and JARVIS types what you said into whatever app has
the cursor (Word, WhatsApp Web, email, a form...). Start with "Jarvis, ..." and it's a command to JARVIS instead.

Speech is understood on the laptop itself (faster-whisper), so nothing you dictate leaves the laptop. It never types
into banking windows. Change the key with JARVIS_DICTATE_KEY (rctrl, ralt, f8, f9, capslock) or turn it off with
JARVIS_DICTATE=off. A quick tap of Right Ctrl, or Right Ctrl with another key (Ctrl+C...), is ignored.
"""
from __future__ import annotations

import os
import re
import tempfile
import threading
import time
import wave
from typing import Callable

KEYS = {"rctrl": 0xA3, "ralt": 0xA5, "f8": 0x77, "f9": 0x78, "capslock": 0x14}
RATE = 16000
MIN_HOLD = 0.45          # shorter than this is a normal key press, not dictation
COMMAND_RE = re.compile(r"^\s*(?:hey |ok )?jarvis[\s,.!:-]+(.+)$", re.I | re.S)
_stop = threading.Event()
_state = {"on": False, "why": ""}


def enabled() -> bool:
    return os.environ.get("JARVIS_DICTATE", "on").strip().lower() != "off"


def status() -> dict:
    return dict(_state)


def clean(text: str) -> str:
    """Tidy what speech recognition heard before typing it."""
    text = re.sub(r"\s+", " ", text or "").strip()
    if text.lower() in ("", "you", "thank you.", "thanks for watching!", "."):   # Whisper's sounds-of-silence guesses
        return ""
    return text


def split_command(text: str) -> str | None:
    """'Jarvis, open Spotify' -> 'open Spotify' (a command), else None (text to type)."""
    m = COMMAND_RE.match(text or "")
    return m.group(1).strip() if m else None


# ------------------------------------------------------------------ typing (Windows SendInput, any language)
def type_text(text: str) -> bool:
    import ctypes
    from ctypes import wintypes
    if os.name != "nt" or not text:
        return False
    ULONG_PTR = ctypes.c_size_t

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", _U)]

    KEYEVENTF_UNICODE, KEYEVENTF_KEYUP = 0x0004, 0x0002
    send = ctypes.windll.user32.SendInput
    units = text.encode("utf-16-le")
    for i in range(0, len(units), 2):
        code = int.from_bytes(units[i:i + 2], "little")
        down = INPUT(type=1, u=_U(ki=KEYBDINPUT(0, code, KEYEVENTF_UNICODE, 0, 0)))
        up = INPUT(type=1, u=_U(ki=KEYBDINPUT(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, 0)))
        arr = (INPUT * 2)(down, up)
        send(2, arr, ctypes.sizeof(INPUT))
    return True


def _beep(freq: int) -> None:
    try:
        import winsound
        winsound.Beep(freq, 70)
    except Exception:  # noqa: BLE001 - beeps are a nicety
        pass


# ------------------------------------------------------------------ the hold-to-talk loop
def start(bus, on_command: Callable[[str], None]) -> str:
    if not enabled():
        return "voice typing: off"
    if os.name != "nt":
        return "voice typing: Windows only"
    from . import stt
    if not stt.available():
        _state.update(on=False, why="needs faster-whisper")
        return "voice typing: needs faster-whisper (pip install faster-whisper)"
    try:
        import numpy as np
        import sounddevice as sd
    except Exception:  # noqa: BLE001
        _state.update(on=False, why="needs sounddevice + numpy")
        return "voice typing: needs sounddevice + numpy"
    import ctypes
    user32 = ctypes.windll.user32
    vk = KEYS.get(os.environ.get("JARVIS_DICTATE_KEY", "rctrl").strip().lower(), KEYS["rctrl"])
    other = [k for k in range(0x30, 0x5B)] + [0x20, 0x0D, 0x09]   # letters, digits, space, enter, tab

    def held(k: int) -> bool:
        return bool(user32.GetAsyncKeyState(k) & 0x8000)

    def handle(blocks: list) -> None:
        from . import clap, stt
        from .desktop import foreground_title
        from .guard import blocked
        audio = np.concatenate(blocks)[:, 0] if blocks else None
        clap.pause(False)
        if audio is None or float(np.sqrt((audio ** 2).mean())) < 0.004:
            return   # silence
        path = os.path.join(tempfile.gettempdir(), "jarvis-dictate.wav")
        with wave.open(path, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes((np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes())
        text = clean(stt.transcribe(path))
        if not text:
            return
        cmd = split_command(text)
        if cmd:
            bus.log("YOU", f"⌨🎙 {cmd}", "command")
            threading.Thread(target=on_command, args=(cmd,), daemon=True).start()
        elif blocked(foreground_title()):
            bus.log("JARVIS", "Voice typing skipped: that's a banking window.", "system")
            return
        else:
            type_text(text + " ")
        bus.publish({"type": "dictated", "chars": len(text), "command": bool(cmd)})

    def run() -> None:
        _state.update(on=True, why="")
        while not _stop.is_set():
            if not held(vk):
                time.sleep(0.03)
                continue
            t0, blocks, spoiled = time.monotonic(), [], False
            try:
                from . import clap
                with sd.InputStream(samplerate=RATE, channels=1, dtype="float32", blocksize=800) as stream:
                    started = False
                    while held(vk) and not _stop.is_set():
                        data, _ = stream.read(800)
                        blocks.append(data.copy())
                        if any(held(k) for k in other):
                            spoiled = True   # Ctrl+C, Ctrl+V...: a shortcut, not dictation
                        if not started and time.monotonic() - t0 >= MIN_HOLD and not spoiled:
                            started = True
                            clap.pause(True)
                            _beep(880)
                            bus.publish({"type": "dictate", "state": "listening"})
                        if time.monotonic() - t0 > 120:
                            break
            except Exception as exc:  # noqa: BLE001 - mic busy: tell the dashboard, try again next time
                _state.update(why=str(exc)[:120])
                time.sleep(1)
                continue
            if spoiled or time.monotonic() - t0 < MIN_HOLD:
                continue
            _beep(660)
            bus.publish({"type": "dictate", "state": "thinking"})
            try:
                handle(blocks)
            except Exception as exc:  # noqa: BLE001
                bus.log("JARVIS", f"Voice typing hit a snag: {exc}"[:200], "error")
            finally:
                from . import clap
                clap.pause(False)
                bus.publish({"type": "dictate", "state": "idle"})

    threading.Thread(target=run, daemon=True, name="jarvis-dictate").start()
    return "voice typing: hold Right Ctrl and talk"


def stop() -> None:
    _stop.set()
