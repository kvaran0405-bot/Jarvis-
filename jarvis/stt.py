"""Speech-to-text for voice notes, running locally with faster-whisper (free, private, no API key).

Install once:  pip install faster-whisper
The model (JARVIS_WHISPER_MODEL: tiny | base | small | medium) downloads on first use.
'base' is fast on any laptop; 'small' understands accents better but is about 3x slower.
"""
from __future__ import annotations

import threading

from .config import settings

_model = None
_models: dict = {}
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


def _model_named(name: str):
    if name == settings.whisper_model:
        return _get_model()
    with _lock:
        if name not in _models:
            from faster_whisper import WhisperModel
            _models[name] = WhisperModel(name, device="auto", compute_type="int8")
        return _models[name]


def transcribe_long(path: str, model: str = "", on_progress=None) -> tuple[list[tuple[float, str]], float]:
    """Transcribe a long recording (lecture / meeting). Returns ([(seconds, text), ...], duration_seconds).
    `on_progress(fraction)` is called as it goes."""
    segments, info = _model_named(model or settings.whisper_model).transcribe(
        path, beam_size=1, vad_filter=True, language="en", condition_on_previous_text=False)
    out = []
    duration = float(getattr(info, "duration", 0) or 0)
    for seg in segments:
        text = seg.text.strip()
        if text:
            out.append((float(seg.start), text))
        if on_progress and duration:
            on_progress(min(1.0, float(seg.end) / duration))
    return out, duration


def warm_up() -> None:
    """Load the model in the background at startup so the first voice note is quick."""
    if available():
        threading.Thread(target=_get_model, daemon=True).start()
