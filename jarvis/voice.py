"""Agent voices: free neural voices (edge-tts) or ElevenLabs. Audio is cached, so repeated lines cost nothing."""
from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.request
from pathlib import Path

from .config import ROOT, settings

CACHE = ROOT / "data" / "tts"

# Default ElevenLabs voice per agent (premade library voices). Override any of them in .env with
# JARVIS_VOICE_<AGENT>=<voice id>, e.g. JARVIS_VOICE_FRIDAY=EXAVITQu4vr4xnJE9EpY. Find IDs in your ElevenLabs
# Voice Library, or clone your own voice there and use its ID.
DEFAULT_VOICES = {
    "JARVIS": "onwK4e9ZLuTAKqWW03F9",    # Daniel - calm British male
    "FRIDAY": "XB0fDUnXU5powFLqSrS8",    # Charlotte - warm female
    "ORACLE": "JBFqnCBsd6RMkjVDRZzb",    # George - measured male
    "ATHENA": "pFZP5JQG7iQjIQuC4Bku",    # Lily - clear female
    "ZEUS": "VR6AewLTigWG4xSOukaG",      # Arnold - deep male
    "HERALD": "ErXwobaYiN019PkySvjV",    # Antoni - friendly male
    "STEVE": "TxGEqnHWrfWFTfGW9XjX",     # Josh - energetic male
    "VERONICA": "21m00Tcm4TlvDq8ikWAM",  # Rachel - confident female
    "BANNER": "N2lVS1w4EtoT3dr4eOWO",    # Callum - gravelly male
    "EDITH": "MF3mGyEYCl7XYWbV9V3O",     # Elli - crisp female
    "SENTINEL": "yoZ06aMxZJJ28mfd3POQ",  # Sam - low, raspy male
    "PEPPER": "EXAVITQu4vr4xnSDxMaL",    # Sarah - poised female
}


# Free natural voices (Microsoft Edge's online neural voices, via the edge-tts package), cast to feel like the films.
# (voice, speed, pitch). Override any agent with JARVIS_EDGE_VOICE_<AGENT>=<voice name>, e.g. en-GB-ThomasNeural
EDGE_VOICES = {
    "JARVIS": ("en-GB-RyanNeural", "-6%", "-2Hz"),            # smooth, unhurried British butler-AI
    "FRIDAY": ("en-IE-EmilyNeural", "+4%", "+0Hz"),           # brisk Irish
    "EDITH": ("en-US-EmmaMultilingualNeural", "-3%", "-1Hz"),  # calm, clear American (expressive voice)
    "VERONICA": ("en-US-AvaMultilingualNeural", "+2%", "+0Hz"),  # confident, sharp (expressive voice)
    "ATHENA": ("en-GB-SoniaNeural", "-3%", "+0Hz"),           # wise British teacher
    "SENTINEL": ("en-US-ChristopherNeural", "-12%", "-14Hz"),  # low, cold, measured
    "ZEUS": ("en-US-GuyNeural", "-2%", "-6Hz"),               # commanding
    "STEVE": ("en-US-AndrewMultilingualNeural", "+0%", "+0Hz"),  # warm, earnest captain (expressive voice)
    "BANNER": ("en-US-BrianMultilingualNeural", "-8%", "-3Hz"),  # soft-spoken scientist (expressive voice)
    "HERALD": ("en-GB-ThomasNeural", "+0%", "+0Hz"),          # smooth British diplomat
    "ORACLE": ("en-US-SteffanNeural", "-4%", "-2Hz"),         # calm analyst
    "PEPPER": ("en-US-AriaNeural", "+0%", "+0Hz"),            # poised, warm, in charge
}


# Emotion: agents start a sentence with a mood tag, e.g. "[excited] You got the interview!". The free voices can't
# act on their own, so each mood shifts speed and pitch the way an actor's delivery would.
MOODS = {
    "warm": (-4, -1), "gentle": (-10, -2), "calm": (-6, -2), "proud": (+2, +4), "cheerful": (+6, +4),
    "excited": (+12, +6), "playful": (+6, +5), "amused": (+3, +3), "dry": (-6, -4), "sarcastic": (-5, +3),
    "serious": (-8, -5), "stern": (-6, -7), "concerned": (-9, -3), "worried": (-7, -2), "urgent": (+12, +3),
    "whisper": (-12, -4), "tired": (-12, -5), "triumphant": (+8, +7),
}
MOOD_RE = re.compile(r"\[(" + "|".join(MOODS) + r")\]\s*", re.I)


def strip_moods(text: str) -> str:
    """Text for reading: mood tags removed."""
    return re.sub(r"\s{2,}", " ", MOOD_RE.sub("", text or "")).strip()


# Greetings and short replies said in one breath with the owner's name: "Good morning Sir", "Yes Sir", "Done Sir"
GREETINGS = (r"good\s+(?:morning|afternoon|evening|night)|morning|afternoon|evening|night|hello|hi|hey|"
             r"welcome(?:\s+back|\s+home)?|yes|no|right|certainly|of\s+course|indeed|understood|done|okay|ok|"
             r"thanks|thank\s+you|very\s+well|at\s+once|absolutely|sure|noted|on\s+it|right\s+away|"
             r"goodbye|good\s+night|sleep\s+well|congratulations|well\s+done|apologies|sorry")


def speakable(text: str) -> str:
    """Text for speaking: no Markdown, and no pause between a greeting and the owner's name
    ("Good morning, Sir" -> "Good morning Sir")."""
    t = re.sub(r"```.*?```", " ", text or "", flags=re.S)
    t = re.sub(r"\[([^\]]+)\]\((?:https?:)[^)]+\)", r"\1", t)          # links -> their label
    t = re.sub(r"[*_`#>|]+", "", t)
    name = re.escape(settings.owner_name.strip() or "Sir")
    t = re.sub(rf"\b({GREETINGS}),\s*({name})\b", r"\1 \2", t, flags=re.I)   # "Good morning, Sir" -> "Good morning Sir"
    return re.sub(r"[ \t]+", " ", t).strip()


def segments(text: str) -> list[tuple[str, str]]:
    """[(mood, text), ...] - consecutive pieces of speech, each with its mood ('' = neutral)."""
    parts, mood, pos = [], "", 0
    for m in MOOD_RE.finditer(text):
        if text[pos:m.start()].strip():
            parts.append((mood, text[pos:m.start()].strip()))
        mood, pos = m.group(1).lower(), m.end()
    if text[pos:].strip():
        parts.append((mood, text[pos:].strip()))
    return parts or [("", text)]


def _shift(base: str, delta: int, unit: str) -> str:
    n = int(re.sub(r"[^\d-]", "", base.replace("+", "")) or 0) + delta
    return f"{'+' if n >= 0 else ''}{n}{unit}"


def _edge_voice(agent: str) -> tuple[str, str, str]:
    name, rate, pitch = EDGE_VOICES.get(agent.upper(), EDGE_VOICES["JARVIS"])
    custom = os.environ.get(f"JARVIS_EDGE_VOICE_{agent.upper()}", "").strip()
    return (custom, "+0%", "+0Hz") if custom else (name, rate, pitch)


# VoiceStudio: each agent's voice is designed from a description (OmniVoice's voice-design vocabulary) and pinned
# with a seed, so it sounds the same every time. Override with JARVIS_VS_VOICE_<AGENT>=<a saved VoiceStudio voice name>.
VS_VOICES = {
    "JARVIS": ("male, middle-aged, moderate pitch, british accent", 1101),
    "FRIDAY": ("female, young adult, moderate pitch, irish accent", 1202),
    "EDITH": ("female, young adult, moderate pitch, american accent", 1303),
    "VERONICA": ("female, middle-aged, moderate pitch, american accent", 1404),
    "ATHENA": ("female, middle-aged, moderate pitch, british accent", 1505),
    "SENTINEL": ("male, middle-aged, very low pitch, american accent", 1606),
    "ZEUS": ("male, middle-aged, low pitch, american accent", 1707),
    "STEVE": ("male, young adult, moderate pitch, american accent", 1808),
    "BANNER": ("male, middle-aged, low pitch, american accent", 1909),
    "HERALD": ("male, middle-aged, moderate pitch, british accent", 2010),
    "ORACLE": ("male, young adult, low pitch, american accent", 2111),
    "PEPPER": ("female, young adult, moderate pitch, american accent", 2212),
}
# Moods -> VoiceStudio's real non-verbal sounds (default OmniVoice engine) and a speed change.
VS_MOODS = {
    "amused": ("[laughter] ", 1.03), "playful": ("[laughter] ", 1.06), "sarcastic": ("[dissatisfaction-hnn] ", 0.96),
    "dry": ("", 0.95), "tired": ("[sigh] ", 0.88), "concerned": ("[sigh] ", 0.92), "worried": ("[sigh] ", 0.93),
    "excited": ("[surprise-oh] ", 1.12), "triumphant": ("", 1.08), "cheerful": ("", 1.06), "urgent": ("", 1.12),
    "gentle": ("", 0.9), "calm": ("", 0.94), "serious": ("", 0.93), "stern": ("", 0.94), "warm": ("", 0.97),
    "proud": ("", 1.02), "whisper": ("", 0.9),
}
_vs_seen = {"at": 0.0, "up": False}


def _vs_headers() -> dict:
    key = os.environ.get("JARVIS_VOICESTUDIO_KEY", "").strip()
    return {"Content-Type": "application/json", **({"Authorization": f"Bearer {key}"} if key else {})}


# How fast VoiceStudio speaks on this laptop (seconds of work per character). Without a graphics card it can be
# too slow for live chat; then live replies use the quick voices and VoiceStudio does briefings and voice notes.
_vs_speed = {"chars": 0, "secs": 0.0}
LIVE_BUDGET_S = float(os.environ.get("JARVIS_VOICESTUDIO_LIVE_BUDGET", "3.5"))


def vs_seconds_per_char() -> float | None:
    return _vs_speed["secs"] / _vs_speed["chars"] if _vs_speed["chars"] >= 40 else None


def vs_too_slow_for(text: str) -> bool:
    spc = vs_seconds_per_char()
    return spc is not None and spc * len(text) > LIVE_BUDGET_S


def voicestudio_up() -> bool:
    """Is VoiceStudio running on this laptop? (checked at most every 30 s)"""
    import time
    if time.time() - _vs_seen["at"] < 30:
        return _vs_seen["up"]
    try:
        req = urllib.request.Request(settings.voicestudio_url.rstrip("/") + "/v1/models", headers=_vs_headers())
        with urllib.request.urlopen(req, timeout=2) as r:
            up = r.status == 200
    except Exception:  # noqa: BLE001
        up = False
    _vs_seen.update(at=time.time(), up=up)
    return up


def provider() -> str:
    """elevenlabs (paid) | voicestudio (free, local, most expressive) | edge (free online) | browser."""
    choice = settings.tts
    if choice in ("elevenlabs", "auto") and settings.elevenlabs_key:
        return "elevenlabs"
    if choice in ("voicestudio", "auto") and voicestudio_up():
        return "voicestudio"
    if choice in ("edge", "auto"):
        try:
            import edge_tts  # noqa: F401
            return "edge"
        except ImportError:
            pass
    return "browser"


def enabled() -> bool:
    return provider() != "browser"


def voice_for(agent: str) -> str:
    agent = agent.upper()
    prov = provider()
    if prov == "edge":
        return _edge_voice(agent)[0]
    if prov == "voicestudio":
        return (os.environ.get(f"JARVIS_VS_VOICE_{agent}", "").strip()
                or VS_VOICES.get(agent, VS_VOICES["JARVIS"])[0])
    return os.environ.get(f"JARVIS_VOICE_{agent}", "").strip() or DEFAULT_VOICES.get(agent, DEFAULT_VOICES["JARVIS"])


def voices() -> dict[str, str]:
    return {name: voice_for(name) for name in DEFAULT_VOICES}


def _edge(text: str, agent: str, path: Path) -> None:
    """Speak each mood segment with its own delivery and join them into one MP3."""
    import asyncio
    import ssl

    import edge_tts
    import edge_tts.communicate

    cafile = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    if cafile and os.path.exists(cafile):   # networks with their own HTTPS proxy certificate
        edge_tts.communicate._SSL_CTX = ssl.create_default_context(cafile=cafile)
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or None
    name, rate, pitch = _edge_voice(agent)

    async def say(v: str, words: str, r: str, p: str) -> bytes:
        audio = bytearray()
        async for chunk in edge_tts.Communicate(words, v, rate=r, pitch=p, proxy=proxy).stream():
            if chunk["type"] == "audio":
                audio += chunk["data"]
        return bytes(audio)

    async def go(v: str, base_rate: str, base_pitch: str) -> bytes:
        out = bytearray()
        for mood, words in segments(text):
            dr, dp = MOODS.get(mood, (0, 0))
            out += await say(v, words, _shift(base_rate, dr, "%"), _shift(base_pitch, dp, "Hz"))
        return bytes(out)

    try:
        data = asyncio.run(go(name, rate, pitch))
    except Exception:  # noqa: BLE001 - unknown custom voice name? fall back to JARVIS's voice once
        if name == EDGE_VOICES["JARVIS"][0]:
            raise
        data = asyncio.run(go(*EDGE_VOICES["JARVIS"]))
    if len(data) < 200:
        raise RuntimeError("voice service returned no audio")
    path.write_bytes(data)


def _vs_request(agent: str, words: str, speed: float, fmt: str) -> bytes:
    custom = os.environ.get(f"JARVIS_VS_VOICE_{agent.upper()}", "").strip()
    design, seed = VS_VOICES.get(agent.upper(), VS_VOICES["JARVIS"])
    body = {"model": "omnivoice", "input": words, "voice": custom or "default", "response_format": fmt,
            "speed": round(max(0.5, min(2.0, speed)), 2)}
    if not custom:
        body.update(instructions=design, seed=seed)
    req = urllib.request.Request(settings.voicestudio_url.rstrip("/") + "/v1/audio/speech",
                                 data=json.dumps(body).encode(), headers=_vs_headers())
    import time
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=max(settings.voicestudio_timeout, 90)) as resp:
        audio = resp.read()
    _vs_speed["chars"] += len(words)
    _vs_speed["secs"] += time.monotonic() - t0
    if _vs_speed["chars"] > 4000:   # keep it a recent average
        _vs_speed.update(chars=_vs_speed["chars"] // 2, secs=_vs_speed["secs"] / 2)
    return audio


def _voicestudio(text: str, agent: str, path: Path) -> Path:
    """One request per mood segment, with real laughs and sighs; joined into one file.
    MP3 when VoiceStudio has ffmpeg, otherwise raw PCM wrapped into a WAV."""
    import urllib.error
    import wave
    pieces = []
    for mood, words in segments(text):
        sound, speed = VS_MOODS.get(mood, ("", 1.0))
        pieces.append((sound + words, speed))
    try:
        audio = b"".join(_vs_request(agent, w, sp, "mp3") for w, sp in pieces)
        path.write_bytes(audio)
        return path
    except urllib.error.HTTPError as exc:
        if exc.code != 400:          # 400 = this VoiceStudio has no ffmpeg for mp3: use raw audio instead
            raise
    pcm = b"".join(_vs_request(agent, w, sp, "pcm") for w, sp in pieces)
    wav_path = path.with_suffix(".wav")
    with wave.open(str(wav_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(pcm)
    return wav_path


def synthesize(agent: str, text: str, live: bool = False) -> Path:
    """Return the path of an MP3 of `agent` saying `text` (cached).
    live=True: someone is waiting for this reply right now, so a slow VoiceStudio hands over to the quick voices."""
    prov = provider()
    if prov == "voicestudio" and live and vs_too_slow_for(speakable(text)):
        try:
            import edge_tts  # noqa: F401
            prov = "edge"
        except ImportError:
            pass
    voice_id = voice_for(agent)
    text = speakable(text)[:2500]
    if prov not in ("edge", "voicestudio"):
        text = strip_moods(text)
    tune = (_edge_voice(agent) if prov == "edge" else
            VS_VOICES.get(agent.upper()) if prov == "voicestudio" else voice_id)
    key = hashlib.sha256(f"{prov}|{tune}|{settings.elevenlabs_model}|{text}".encode()).hexdigest()[:32]
    path = CACHE / f"{key}.mp3"
    if path.exists():
        return path
    if path.with_suffix(".wav").exists():
        return path.with_suffix(".wav")
    CACHE.mkdir(parents=True, exist_ok=True)
    if prov == "voicestudio":
        try:
            return _voicestudio(text, agent, path)
        except Exception:  # noqa: BLE001 - VoiceStudio slow or stopped: fall back to the free online voices
            _vs_seen.update(at=0.0)
            prov = "edge"
            path = CACHE / f"{hashlib.sha256(f'edge|{_edge_voice(agent)}|{text}'.encode()).hexdigest()[:32]}.mp3"
            if path.exists():
                return path
    if prov == "edge":
        try:
            _edge(text, agent, path)
        except Exception:
            path.unlink(missing_ok=True)
            raise
        return path
    if prov != "elevenlabs":
        raise RuntimeError("No voice service configured - the browser's own voice is used")
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        data=json.dumps({"text": text, "model_id": settings.elevenlabs_model}).encode(),
        headers={"xi-api-key": settings.elevenlabs_key, "Content-Type": "application/json", "Accept": "audio/mpeg"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        audio = resp.read()
    CACHE.mkdir(parents=True, exist_ok=True)
    path.write_bytes(audio)
    return path


def synthesize_for_phone(agent: str, text: str) -> Path:
    """Telegram voice notes need MP3/OGG; if VoiceStudio could only give WAV, use the free online voice instead."""
    path = synthesize(agent, text)
    if path.suffix == ".mp3":
        return path
    edge_path = CACHE / f"{hashlib.sha256(f'edge|{_edge_voice(agent)}|{speakable(text)}'.encode()).hexdigest()[:32]}.mp3"
    if not edge_path.exists():
        _edge(speakable(text)[:2500], agent, edge_path)
    return edge_path


def long_audio(agent: str, text: str) -> Path:
    """A long read-aloud (an article, notes) as one MP3, made in pieces with the quick free voices."""
    import re as _re
    text = strip_moods(text)
    parts, cur = [], ""
    for sentence in _re.split(r"(?<=[.!?])\s+", text):
        if len(cur) + len(sentence) > 1800 and cur:
            parts.append(cur)
            cur = ""
        cur += sentence + " "
    if cur.strip():
        parts.append(cur)
    key = hashlib.sha256(f"long|{agent}|{text}".encode()).hexdigest()[:32]
    out = CACHE / f"long-{key}.mp3"
    if out.exists():
        return out
    CACHE.mkdir(parents=True, exist_ok=True)
    audio = bytearray()
    for i, part in enumerate(parts):
        piece = CACHE / f"long-{key}-{i}.mp3"
        _edge(part, agent, piece)
        audio += piece.read_bytes()
        piece.unlink(missing_ok=True)
    out.write_bytes(bytes(audio))
    return out
