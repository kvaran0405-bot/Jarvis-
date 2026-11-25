"""Gemini voices: Google's expressive speech models act each line (moods, laughs, sighs) in a voice chosen per agent.

Uses the same free GEMINI_API_KEY as the Gemini brain. Google's terms for these voice models change (they're in
preview, and the free tier may not include them); if Google refuses or it's slow, JARVIS quietly falls back to the
free voices and tries Gemini again later. Turn off with JARVIS_GEMINI_VOICES=off.
"""
from __future__ import annotations

import base64
import json
import os
import re
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

from .config import settings

URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
MODELS = [m for m in os.environ.get("JARVIS_GEMINI_TTS_MODEL", "").split(",") if m.strip()] or [
    "gemini-3.1-flash-tts-preview", "gemini-2.5-flash-preview-tts"]

# agent: (Gemini prebuilt voice, how to perform)
VOICES = {   # cinematic cast: every agent has an accent, an attitude and real emotion (like JARVIS's solo voice)
    "JARVIS": ("Charon", "a refined, unhurried British butler AI with a deep, warm voice and bone-dry wit, quietly devoted "
                         "and a little theatrical, like the AI in a blockbuster"),
    "FRIDAY": ("Leda", "a quick, cheeky young Irish woman with a soft lilting brogue, breathy and flirty-playful, always "
                       "smiling through the words, teasing him like a close friend"),
    "PEPPER": ("Kore", "a poised, confident American woman with a low, velvety, sultry voice, warm and fond of him, "
                       "unhurried and a touch seductive, the kind of voice you look forward to every morning"),
    "ATHENA": ("Gacrux", "a wise, elegant British woman with a smooth, soothing, honeyed voice, encouraging and kind, "
                         "like a favourite teacher who believes in you"),
    "ZEUS": ("Alnilam", "a commanding, intense career coach with a deep booming voice, fired up and competitive, like a "
                        "movie-trailer pep talk before the big fight"),
    "HERALD": ("Schedar", "a smooth, charming British diplomat with a gossipy twinkle, amused and a bit conspiratorial"),
    "STEVE": ("Puck", "an upbeat, earnest, old-fashioned American hero coach with a big heart, rallying and sincere"),
    "VERONICA": ("Sulafat", "a glamorous, shrewd woman with a smoky, sultry, slightly husky voice and a raised-eyebrow "
                            "sarcasm, frank about money, purring the punchlines like a film-noir femme fatale"),
    "BANNER": ("Enceladus", "a gentle, soft-spoken, caring man who speaks slowly and kindly, a calm hand on the shoulder"),
    "EDITH": ("Despina", "a cool, sleek young woman with a silky, low, intimate voice, precise and efficient with a wry, "
                         "flirtatious streak, like a spy-movie handler in your ear"),
    "SENTINEL": ("Algenib", "a terse, gravelly, vigilant guard with short heavy sentences, like an action-film soldier"),
    "ORACLE": ("Iapetus", "a calm, precise analyst with a deep, quietly confident voice, like a thriller narrator"),
    "GUEST": ("Charon", "a theatrical British butler AI entertaining a guest with grand, cinematic charm"),
}
_state = {"down_until": 0.0, "model": None, "secs": 0.0, "chars": 0, "why": ""}


def enabled() -> bool:
    return bool(settings.gemini_key) and os.environ.get("JARVIS_GEMINI_VOICES", "on").lower() != "off" \
        and time.time() >= _state["down_until"]


def status() -> dict:
    return {"on": enabled(), "model": _state["model"], "paused_reason": _state["why"] if time.time() < _state["down_until"] else ""}


def seconds_per_char() -> float | None:
    return _state["secs"] / _state["chars"] if _state["chars"] >= 60 else None


def direction(agent: str, text: str) -> str:
    """The acting note plus the line, with moods and sounds turned into stage directions."""
    from .voice import EMOTES, MOODS
    _voice, who = VOICES.get(agent.upper(), VOICES["JARVIS"])

    def tag(m):
        t = m.group(1).lower()
        if t in EMOTES:
            return f"({t}) "
        if t == "whispers" or t == "whisper":
            return "(whispering) "
        return f"({t}) " if t in MOODS else ""
    line = re.sub(r"\[(\w+)\]\s*", tag, text)
    from datetime import datetime
    from .voice import ATTITUDE
    hour = datetime.now(settings.tz).hour
    when = ("It's late at night: keep it soft, close and unhurried." if hour >= 23 or hour < 6 else
            "It's morning: bright and awake, but not loud." if 6 <= hour < 11 else "")
    mood = ATTITUDE.get(agent.upper(), "")
    return f"{acting(who, mood)}{when}\n\n{line}"


def acting(who: str, mood: str = "") -> str:
    """The cinematic acting note (the phone's solo mode gets the same one in its pack)."""
    return (f"You are voicing {who}. Your usual attitude is {mood or 'natural'}; let it colour the whole line.\n"
            "Perform it like a lead actor in a film talking to someone they adore, not like a narrator or an assistant: "
            "keep your accent strong and consistent, natural breaths, small hesitations where someone would think, vary "
            "your pace (quick on easy bits, slower and lower on what matters), let questions lift, lean on the important "
            "word, and let real emotion and attitude show in the voice. "
            "Act the stage directions in brackets (laughs, sighs, moods) as real sounds and tone; never read them aloud. ")


def synthesize(agent: str, text: str, path: Path) -> Path:
    """Write a WAV of the agent saying `text`. Raises (and pauses Gemini voices for a while) on failure."""
    voice, _who = VOICES.get(agent.upper(), VOICES["JARVIS"])
    body = {"contents": [{"parts": [{"text": direction(agent, text)}]}],
            "generationConfig": {"responseModalities": ["AUDIO"],
                                 "speechConfig": {"voiceConfig": {"prebuiltVoiceConfig": {"voiceName": voice}}}}}
    models = [_state["model"]] if _state["model"] else MODELS
    last = None
    for model in models:
        req = urllib.request.Request(URL.format(model=model), data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", "x-goog-api-key": settings.gemini_key})
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                out = json.loads(r.read())
            part = next(p for p in out["candidates"][0]["content"]["parts"] if "inlineData" in p)
            pcm = base64.b64decode(part["inlineData"]["data"])
            rate = int(re.search(r"rate=(\d+)", part["inlineData"].get("mimeType", "")).group(1)) \
                if "rate=" in part["inlineData"].get("mimeType", "") else 24000
            wav = path.with_suffix(".wav")
            with wave.open(str(wav), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(rate)
                w.writeframes(pcm)
            _state.update(model=model, secs=_state["secs"] + time.time() - t0, chars=_state["chars"] + len(text), why="")
            if _state["chars"] > 3000:
                _state.update(secs=_state["secs"] / 2, chars=_state["chars"] // 2)
            return wav
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code == 404:
                continue   # this model name isn't available: try the next
            reason = {429: "Google's free limit for voices is used up for now",
                      403: "this Gemini key isn't allowed to use voices",
                      400: "Google refused the voice request"}.get(exc.code, f"Google voice error {exc.code}")
            _state.update(down_until=time.time() + (3600 if exc.code in (403, 400) else 900), why=reason)
            raise RuntimeError(reason) from None
        except Exception as exc:  # noqa: BLE001 - network blip: pause briefly
            last = exc
            _state.update(down_until=time.time() + 300, why=f"Gemini voices unreachable: {exc}")
            raise RuntimeError(_state["why"]) from None
    _state.update(down_until=time.time() + 6 * 3600, why="no Gemini voice model is available to this key")
    raise RuntimeError(f"{_state['why']} ({last})")
