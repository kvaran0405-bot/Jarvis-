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


# ---------------------------------------------------------------- Google-quality hearing (free Gemini key)
GEMINI_MIME = {".ogg": "audio/ogg", ".oga": "audio/ogg", ".wav": "audio/wav", ".mp3": "audio/mp3", ".flac": "audio/flac",
               ".aac": "audio/aac"}


def gemini_hearing_on() -> bool:
    import os
    return bool(settings.gemini_key) and os.environ.get("JARVIS_GEMINI_HEARING", "on").lower() != "off"


def _wav_bytes(samples) -> bytes:
    import io
    import wave
    import numpy as np
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())
    return buf.getvalue()


def gemini_transcribe(path: str, hint: str = "") -> str:
    """Writes down exactly what the owner said, the way Google's phone keyboard would: Singapore English, names
    spelled right. Raises on any failure so the caller falls back to the laptop's own engine."""
    import base64
    import json
    import urllib.request
    from pathlib import Path
    ext = Path(path).suffix.lower()
    if ext in GEMINI_MIME:
        mime, data = GEMINI_MIME[ext], Path(path).read_bytes()
    else:   # webm / m4a from a browser: decode and send as a small WAV
        mime, data = "audio/wav", _wav_bytes(load_audio(path))
    prompt = ("Transcribe this voice message word for word. The speaker is from Singapore, talking to their "
              "assistant JARVIS; they speak Singapore English (words like lah, leh, aite, can or not are normal). "
              f"Names you may hear: {hint or vocabulary()}. Output only the words he said, no quotes, no notes. "
              "If there is no speech, output nothing.")
    body = {"contents": [{"parts": [{"text": prompt}, {"inlineData": {"mimeType": mime, "data": base64.b64encode(data).decode()}}]}],
            "generationConfig": {"temperature": 0}}
    from .brains import GEMINI_URL
    req = urllib.request.Request(GEMINI_URL.format(model=settings.gemini_model), data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "x-goog-api-key": settings.gemini_key})
    with urllib.request.urlopen(req, timeout=30) as r:
        out = json.loads(r.read())
    parts = out.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    return " ".join(p.get("text", "") for p in parts).strip().strip('"“”')


def hear_best(path: str, hint: str = "") -> tuple[str, float, str]:
    """(text, confidence, engine). Gemini first when the free key is set (far better with accents), the laptop's
    own engine otherwise or if Google is unreachable."""
    if gemini_hearing_on():
        try:
            text = gemini_transcribe(path, hint)
            return text, (0.95 if text else 0.0), "gemini"
        except Exception:  # noqa: BLE001 - fall back to the local engine, never go silent
            pass
    if not available():
        raise RuntimeError("the speech part isn't installed")
    text, conf = transcribe_scored(path, hint)
    return text, conf, "local"
