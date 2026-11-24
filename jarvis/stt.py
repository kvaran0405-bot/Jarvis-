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


def load_audio(path: str):
    """Any audio file -> 16 kHz mono float32 samples. JARVIS decodes it itself: the speech engine's own decoder
    breaks with newer versions of the audio library ("unexpected keyword argument 'metadata_errors'")."""
    import numpy as np
    p = str(path)
    if p.lower().endswith(".wav"):
        import wave
        with wave.open(p, "rb") as w:
            if w.getsampwidth() == 2:
                pcm = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768
                if w.getnchannels() > 1:
                    pcm = pcm.reshape(-1, w.getnchannels()).mean(axis=1)
                if w.getframerate() == 16000:
                    return pcm
                n = int(len(pcm) * 16000 / w.getframerate())
                return np.interp(np.linspace(0, len(pcm) - 1, n), np.arange(len(pcm)), pcm).astype(np.float32)
    import av
    chunks = []
    with av.open(p) as container:
        res = av.AudioResampler(format="s16", layout="mono", rate=16000)
        for frame in container.decode(audio=0):
            for f in res.resample(frame) or []:
                chunks.append(f.to_ndarray().reshape(-1))
        for f in res.resample(None) or []:
            chunks.append(f.to_ndarray().reshape(-1))
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(chunks).astype(np.float32) / 32768


def vocabulary(store=None) -> str:
    """Names JARVIS should expect to hear (agents, places, the business), so the recogniser spells them right
    instead of guessing. Used as the recogniser's starting hint."""
    from .agents import AGENTS
    words = [n.title() for n, a in AGENTS.items() if not a.hidden] + [
        "Jarvis", "Shaabaz", "Kaplan", "Tampines", "Bukit Timah", "Jurong", "Punggol", "Changi", "Orchard", "Bugis",
        "Sentosa", "Raffles", "Marina Bay Sands", "MRT", "Grab", "Shopee", "Lazada", "Telegram", "WhatsApp", "lah"]
    if store is not None:
        try:
            import json as _json
            words += list(_json.loads(store.get("places:saved") or "{}"))[:20]
        except Exception:  # noqa: BLE001
            pass
    return "Hey Jarvis. " + ", ".join(dict.fromkeys(words)) + "."


def transcribe(path: str, hint: str = "") -> str:
    segments, _info = _get_model().transcribe(load_audio(path), beam_size=1, vad_filter=True,
                                              initial_prompt=hint or vocabulary(), language="en")
    return " ".join(seg.text.strip() for seg in segments).strip()


def transcribe_scored(path: str, hint: str = "") -> tuple[str, float]:
    """(text, confidence 0-1). Low confidence means: ask the owner to say it again rather than guess."""
    import math
    import os
    model = _model_named(os.environ.get("JARVIS_HEAR_MODEL", "small"))   # more accurate for accents and names
    segments, _info = model.transcribe(load_audio(path), beam_size=3, vad_filter=True,
                                              initial_prompt=hint or vocabulary(), language="en")
    segs = list(segments)
    text = " ".join(s.text.strip() for s in segs).strip()
    if not segs:
        return "", 0.0
    lp = sum(s.avg_logprob for s in segs) / len(segs)
    nosp = max(s.no_speech_prob for s in segs)
    return text, max(0.0, min(1.0, math.exp(lp) * (1 - nosp)))


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
        load_audio(path), beam_size=1, vad_filter=True, language="en", condition_on_previous_text=False)
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
        import os

        def load():
            _get_model()
            _model_named(os.environ.get("JARVIS_HEAR_MODEL", "small"))   # push-to-talk engine, ready before first use
        threading.Thread(target=load, daemon=True).start()
