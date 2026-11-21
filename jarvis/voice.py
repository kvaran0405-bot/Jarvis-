"""Agent voices: free neural voices (edge-tts) or ElevenLabs. Audio is cached, so repeated lines cost nothing."""
from __future__ import annotations

import hashlib
import json
import os
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
}


# Free natural voices (Microsoft Edge's online neural voices, via the edge-tts package), cast to feel like the films.
# (voice, speed, pitch). Override any agent with JARVIS_EDGE_VOICE_<AGENT>=<voice name>, e.g. en-GB-ThomasNeural
EDGE_VOICES = {
    "JARVIS": ("en-GB-RyanNeural", "-6%", "-2Hz"),            # smooth, unhurried British butler-AI
    "FRIDAY": ("en-IE-EmilyNeural", "+4%", "+0Hz"),           # brisk Irish
    "EDITH": ("en-US-MichelleNeural", "-2%", "-1Hz"),         # calm American
    "VERONICA": ("en-US-AriaNeural", "+2%", "+0Hz"),          # confident, sharp
    "ATHENA": ("en-GB-SoniaNeural", "-3%", "+0Hz"),           # wise British teacher
    "SENTINEL": ("en-US-ChristopherNeural", "-12%", "-14Hz"),  # low, cold, measured
    "ZEUS": ("en-US-GuyNeural", "-2%", "-6Hz"),               # commanding
    "STEVE": ("en-US-AndrewNeural", "+0%", "+0Hz"),           # warm, earnest captain
    "BANNER": ("en-US-BrianNeural", "-8%", "-3Hz"),           # soft-spoken scientist
    "HERALD": ("en-GB-ThomasNeural", "+0%", "+0Hz"),          # smooth British diplomat
    "ORACLE": ("en-US-SteffanNeural", "-4%", "-2Hz"),         # calm analyst
}


def _edge_voice(agent: str) -> tuple[str, str, str]:
    name, rate, pitch = EDGE_VOICES.get(agent.upper(), EDGE_VOICES["JARVIS"])
    custom = os.environ.get(f"JARVIS_EDGE_VOICE_{agent.upper()}", "").strip()
    return (custom, "+0%", "+0Hz") if custom else (name, rate, pitch)


def provider() -> str:
    """elevenlabs (paid, best) | edge (free neural voices) | browser (the computer's own voices)."""
    choice = settings.tts
    if choice in ("elevenlabs", "auto") and settings.elevenlabs_key:
        return "elevenlabs"
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
    if provider() == "edge":
        return _edge_voice(agent)[0]
    return os.environ.get(f"JARVIS_VOICE_{agent}", "").strip() or DEFAULT_VOICES.get(agent, DEFAULT_VOICES["JARVIS"])


def voices() -> dict[str, str]:
    return {name: voice_for(name) for name in DEFAULT_VOICES}


def _edge(text: str, agent: str, path: Path) -> None:
    import asyncio
    import ssl

    import edge_tts
    import edge_tts.communicate

    cafile = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    if cafile and os.path.exists(cafile):   # networks with their own HTTPS proxy certificate
        edge_tts.communicate._SSL_CTX = ssl.create_default_context(cafile=cafile)
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or None
    name, rate, pitch = _edge_voice(agent)

    async def go(v: str, r: str, p: str):
        await edge_tts.Communicate(text, v, rate=r, pitch=p, proxy=proxy).save(str(path))

    try:
        asyncio.run(go(name, rate, pitch))
    except Exception:  # noqa: BLE001 - unknown custom voice name? fall back to JARVIS's voice once
        if name == EDGE_VOICES["JARVIS"][0]:
            raise
        asyncio.run(go(*EDGE_VOICES["JARVIS"]))
    if not path.exists() or path.stat().st_size < 200:
        path.unlink(missing_ok=True)
        raise RuntimeError("voice service returned no audio")


def synthesize(agent: str, text: str) -> Path:
    """Return the path of an MP3 of `agent` saying `text` (cached)."""
    prov = provider()
    voice_id = voice_for(agent)
    text = text.strip()[:2500]
    tune = _edge_voice(agent) if prov == "edge" else voice_id
    key = hashlib.sha256(f"{prov}|{tune}|{settings.elevenlabs_model}|{text}".encode()).hexdigest()[:32]
    path = CACHE / f"{key}.mp3"
    if path.exists():
        return path
    CACHE.mkdir(parents=True, exist_ok=True)
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
