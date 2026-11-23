"""A natural voice that works with no internet: Kokoro (open-source, Apache-2.0), running on the laptop.

Used when the online voices can't be reached, or always with JARVIS_VOICE=local. The model (~330 MB) downloads once
in the background while the laptop is online, into data/voices/. If anything about it fails, JARVIS simply uses
the other voices, so this can never make things worse. Turn off with JARVIS_LOCAL_VOICE=off."""
from __future__ import annotations

import os
import threading
import urllib.request
import wave
from pathlib import Path

from .config import ROOT

FOLDER = ROOT / "data" / "voices"
BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
FILES = {"kokoro-v1.0.onnx": 300_000_000, "voices-v1.0.bin": 25_000_000}   # rough minimum sizes
# agent -> (Kokoro voice, language, base speed). British voices for the British characters.
CAST = {
    "JARVIS": ("bm_george", "en-gb", .95), "HERALD": ("bm_lewis", "en-gb", 1.0), "ATHENA": ("bf_emma", "en-gb", .97),
    "ORACLE": ("bm_daniel", "en-gb", .97), "FRIDAY": ("bf_isabella", "en-gb", 1.06), "PEPPER": ("af_heart", "en-us", 1.0),
    "VERONICA": ("af_nicole", "en-us", 1.0), "EDITH": ("af_sky", "en-us", 1.0), "STEVE": ("am_michael", "en-us", 1.03),
    "ZEUS": ("am_fenrir", "en-us", 1.0), "BANNER": ("am_echo", "en-us", .92), "SENTINEL": ("am_onyx", "en-us", .9),
}
_state = {"engine": None, "busy": False, "why": ""}
_lock = threading.Lock()


def wanted() -> bool:
    return os.environ.get("JARVIS_LOCAL_VOICE", "on").lower() != "off"


def installed() -> bool:
    try:
        import kokoro_onnx  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return all((FOLDER / f).exists() and (FOLDER / f).stat().st_size >= n for f, n in FILES.items())


def ready() -> bool:
    return wanted() and installed()


def fetch_in_background() -> None:
    """Download the model once (resumable: a half file is finished next time). Quietly gives up when offline."""
    if not wanted() or installed() or _state["busy"]:
        return

    def go():
        _state["busy"] = True
        try:
            import kokoro_onnx  # noqa: F401  (the package comes with start.bat; no package, no download)
            FOLDER.mkdir(parents=True, exist_ok=True)
            for name, minimum in FILES.items():
                dest = FOLDER / name
                if dest.exists() and dest.stat().st_size >= minimum:
                    continue
                part = dest.with_suffix(dest.suffix + ".part")
                have = part.stat().st_size if part.exists() else 0
                req = urllib.request.Request(BASE + name, headers={"Range": f"bytes={have}-"} if have else {})
                with urllib.request.urlopen(req, timeout=60) as r, open(part, "ab" if have else "wb") as f:
                    while chunk := r.read(1 << 20):
                        f.write(chunk)
                part.replace(dest)
            _state["why"] = ""
        except Exception as exc:  # noqa: BLE001 - try again next start
            _state["why"] = str(exc)[:200]
        finally:
            _state["busy"] = False
    threading.Thread(target=go, daemon=True, name="jarvis-localvoice").start()


def _engine():
    with _lock:
        if _state["engine"] is None:
            from kokoro_onnx import Kokoro
            _state["engine"] = Kokoro(str(FOLDER / "kokoro-v1.0.onnx"), str(FOLDER / "voices-v1.0.bin"))
        return _state["engine"]


def synthesize(agent: str, pieces: list[tuple[str, int, int, int]], path: Path) -> Path:
    """pieces: [(words, rate %, pitch Hz, pause ms after)] from voice.delivery(). Writes a WAV and returns it."""
    import numpy as np
    voice, lang, speed = CAST.get(agent.upper(), CAST["JARVIS"])
    eng = _engine()
    out, rate = [], 24000
    for words, dr, _dp, pause in pieces:
        if not words.strip():
            continue
        samples, rate = eng.create(words, voice=voice, speed=max(.6, min(1.6, speed * (1 + dr / 100))), lang=lang)
        out.append(np.asarray(samples, dtype=np.float32))
        if pause:
            out.append(np.zeros(int(rate * pause / 1000), dtype=np.float32))
    if not out:
        raise RuntimeError("nothing to say")
    audio = np.concatenate(out)
    pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()
    wav = path.with_suffix(".wav")
    with wave.open(str(wav), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return wav


def status() -> dict:
    return {"wanted": wanted(), "installed": installed(), "downloading": _state["busy"], "problem": _state["why"]}
