"""Speech-to-text for voice notes, running locally with faster-whisper (free, private, no API key).

Install once:  pip install faster-whisper
The model (JARVIS_WHISPER_MODEL: tiny | base | small | medium) downloads on first use.
'base' is fast on any laptop; 'small' understands accents better but is about 3x slower.
"""
from __future__ import annotations

import threading

from .config import settings

_model = None
_lock = threading.Lock()


def available() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except ImportError:
        return False


def _get_model():
    global _model
    with _lock:
        if _model is None:
            from faster_whisper import WhisperModel
            _model = WhisperModel(settings.whisper_model, device="auto", compute_type="int8")
        return _model


def transcribe(path: str) -> str:
    segments, _info = _get_model().transcribe(path, beam_size=1, vad_filter=True)
    return " ".join(seg.text.strip() for seg in segments).strip()


def warm_up() -> None:
    """Load the model in the background at startup so the first voice note is quick."""
    if available():
        threading.Thread(target=_get_model, daemon=True).start()
