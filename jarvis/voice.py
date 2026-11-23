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
# Emotes: sounds an agent makes, written as [laughs], [sighs]... (spoken text, speed change %, pitch change Hz,
# VoiceStudio's real sound). Free voices say the sound in the agent's own voice; expressive voices act it out.
EMOTES = {
    "laughs": ("Ha ha ha!", +12, +7, "[laughter] "), "chuckles": ("Heh heh.", +2, +3, "[laughter] "),
    "sighs": ("Haahh...", -28, -7, "[sigh] "), "groans": ("Ughhh.", -22, -9, "[dissatisfaction-hnn] "),
    "gasps": ("Oh!", +18, +10, "[surprise-oh] "), "scoffs": ("Pfft.", +0, -3, "[dissatisfaction-hnn] "),
    "hums": ("Hmm.", -12, -4, ""), "giggles": ("Hee hee!", +14, +9, "[laughter] "),
}
# Everyone laughs differently: how each agent's sounds come out with the free voices (default: EMOTES above).
EMOTE_STYLE = {
    "JARVIS": {"laughs": "Heh. Heh heh.", "chuckles": "Hm-hm.", "sighs": "Hmm... ahh.", "scoffs": "Hm."},
    "FRIDAY": {"laughs": "Ha! Ah, ha ha!", "giggles": "Hehe!", "gasps": "Oh my gosh!", "sighs": "Ugh, fine..."},
    "ZEUS": {"laughs": "HA! Ha ha ha!", "chuckles": "Heh! Ha!", "groans": "Argh!"},
    "STEVE": {"laughs": "Ha ha! Yeah!", "chuckles": "Heh heh!", "sighs": "Phew..."},
    "VERONICA": {"laughs": "Ha! Oh, please.", "scoffs": "Psh.", "sighs": "Mm. Of course.", "chuckles": "Mm-hm-hm."},
    "PEPPER": {"laughs": "Ha! Oh, you.", "sighs": "Okay... deep breath.", "chuckles": "Mm-hm."},
    "BANNER": {"laughs": "Heh... ha ha.", "sighs": "Haaahh...", "chuckles": "Heh."},
    "SENTINEL": {"laughs": "Hah.", "chuckles": "Hm.", "sighs": "Hmph.", "scoffs": "Tch."},
    "HERALD": {"laughs": "Oh-ho-ho!", "gasps": "Darling, no!", "chuckles": "Ho ho."},
    "ATHENA": {"laughs": "Ha, ha.", "sighs": "Hmm... alright.", "hums": "Mmm, let's see."},
    "EDITH": {"laughs": "Ha. Okay.", "sighs": "Noted.", "scoffs": "Mm."},
    "ORACLE": {"laughs": "Ha, interesting.", "hums": "Hmm. Running it."},
}


def emote_words(agent: str, emote: str) -> str:
    return EMOTE_STYLE.get(agent.upper(), {}).get(emote) or EMOTES[emote][0]


# Auditions: a short scene per agent that shows their range (attitude, a sound, a change of feeling).
AUDITIONS = {
    "JARVIS": "[dry] Good evening Sir. I see the gym bag is still by the door. [chuckles] Bold strategy. [warm] Still, today was good work.",
    "FRIDAY": "[excited] Boss! You're back! [laughs] Okay okay, I'll calm down. [playful] No I won't.",
    "PEPPER": "[warm] Morning. The Tan wedding is sorted, the crew's confirmed. [sighs] And yes, I chased the deposit. Again.",
    "ZEUS": "[excited] Champion! Three interviews this week! [laughs] We are unstoppable! [serious] Now. Practise the answers.",
    "STEVE": "[cheerful] Soldier! Leg day. No excuses. [laughs] I'm kidding. [proud] Okay, I'm not. Let's go.",
    "VERONICA": "[sarcastic] Another bubble tea? Bold. [scoffs] Darling, that's eleven dollars a week. [dry] I'm just saying.",
    "BANNER": "[gentle] Hey. It's late. [sighs] You did enough today. [warm] Breathe with me for a second.",
    "SENTINEL": "[stern] Three deadlines. Two days. [scoffs] Zero excuses. [serious] Start with the report.",
    "HERALD": "[amused] Darling, the gossip today is delicious. [gasps] You won't believe who emailed. [playful] Later.",
    "ATHENA": "[calm] Twenty minutes now saves two hours of panic later. [hums] Topic three first. [warm] You've got this.",
    "EDITH": "[dry] Downloads sorted. Four hundred and twelve files. [laughs] You're welcome. [calm] Backups done.",
    "ORACLE": "[calm] I ran the numbers. [hums] Interesting. [serious] You'll want to sit down for this one.",
}


TAG_RE = re.compile(r"\[(" + "|".join(list(MOODS) + list(EMOTES) + ["whispers"]) + r")\]\s*", re.I)
MOOD_RE = TAG_RE
EMOTE_RE = re.compile(r"\[(" + "|".join(list(EMOTES) + ["whispers"]) + r")\]\s*", re.I)


def strip_moods(text: str) -> str:
    """Text for reading: mood tags removed, sounds shown like film subtitles: (laughs)."""
    t = EMOTE_RE.sub(lambda m: f"({m.group(1).lower()}) " if m.group(1).lower() != "whispers" else "", text or "")
    t = TAG_RE.sub("", t)
    return re.sub(r"\s{2,}", " ", t).strip()


# Greetings and short replies said in one breath with the owner's name: "Good morning Sir", "Yes Sir", "Done Sir"
GREETINGS = (r"good\s+(?:morning|afternoon|evening|night)|morning|afternoon|evening|night|hello|hi|hey|"
             r"welcome(?:\s+back|\s+home)?|yes|no|right|certainly|of\s+course|indeed|understood|done|okay|ok|"
             r"thanks|thank\s+you|very\s+well|at\s+once|absolutely|sure|noted|on\s+it|right\s+away|"
             r"goodbye|good\s+night|sleep\s+well|congratulations|well\s+done|apologies|sorry")


# How to SAY Singapore names (spoken only; the screen still shows the real spelling). Teach more by saying
# "Jarvis, pronounce Tampines as Tam-pih-neez" (saved in data/pronounce.json).
PRONOUNCE = {
    "Shaabaz": "Shah-bahz", "Tampines": "Tam-pih-neez", "Bukit Timah": "Boo-kit Tee-mah", "Bukit Batok": "Boo-kit Bah-tok",
    "Bukit Panjang": "Boo-kit Pahn-jahng", "Punggol": "Poong-goal", "Jurong": "Joo-rong", "Pasir Ris": "Pah-seer Riss",
    "Yishun": "Yee-shoon", "Ang Mo Kio": "Ahng Mo Kee-oh", "Toa Payoh": "Twa Pah-yoh", "Hougang": "Ho-gahng",
    "Sengkang": "Seng-kahng", "Serangoon": "Seh-rahng-goon", "Geylang": "Gay-lahng", "Kallang": "Kah-lahng",
    "Changi": "Chahng-ee", "Bugis": "Boo-giss", "Tiong Bahru": "Tee-ong Bah-roo", "Lau Pa Sat": "Lao Pah Saht",
    "Sembawang": "Sem-bah-wahng", "Woodlands": "Woodlands", "Choa Chu Kang": "Chwa Choo Kahng", "Bedok": "Beh-dock",
    "Kampong Glam": "Kahm-pong Glahm", "Joo Chiat": "Joo Chee-at", "Katong": "Kah-tong", "Paya Lebar": "Pah-yah Leh-bar",
    "Kranji": "Krahn-jee", "Simei": "See-may", "Tanjong Pagar": "Tahn-jong Pah-gar", "Hari Raya": "Hah-ree Rah-yah",
    "Deepavali": "Dee-pah-vah-lee", "kopitiam": "koh-pee-tee-ahm", "MRT": "M R T", "HDB": "H D B", "lah": "lah",
}
_custom = {"mtime": 0.0, "map": {}}


def pronunciations() -> dict[str, str]:
    """Built-in + the owner's own (data/pronounce.json)."""
    f = CACHE.parent / "pronounce.json"
    try:
        m = f.stat().st_mtime
        if m != _custom["mtime"]:
            import json as _json
            _custom.update(mtime=m, map=_json.loads(f.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        _custom.update(mtime=0.0, map={})
    return {**PRONOUNCE, **_custom["map"]}


def teach(word: str, sounds_like: str) -> None:
    import json as _json
    f = CACHE.parent / "pronounce.json"
    cur = dict(pronunciations())
    mine = {k: v for k, v in cur.items() if PRONOUNCE.get(k) != v}
    mine[word.strip()] = sounds_like.strip()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(_json.dumps(mine, ensure_ascii=False, indent=1), encoding="utf-8")


def say_names(text: str) -> str:
    for word, sound in sorted(pronunciations().items(), key=lambda x: -len(x[0])):
        if word != sound:
            text = re.sub(rf"(?<![\w-]){re.escape(word)}(?![\w-])", sound, text, flags=re.I)
    return text


def speakable(text: str) -> str:
    """Text for speaking: no Markdown, and no pause between a greeting and the owner's name
    ("Good morning, Sir" -> "Good morning Sir")."""
    t = re.sub(r"```.*?```", " ", text or "", flags=re.S)
    t = re.sub(r"\[([^\]]+)\]\((?:https?:)[^)]+\)", r"\1", t)          # links -> their label
    t = re.sub(r"[*_`#>|]+", "", t)
    name = re.escape(settings.owner_name.strip() or "Sir")
    t = re.sub(rf"\b({GREETINGS}),\s*({name})\b", r"\1 \2", t, flags=re.I)   # "Good morning, Sir" -> "Good morning Sir"
    t = say_names(t)   # Singapore names said properly
    return re.sub(r"[ \t]+", " ", t).strip()


def segments(text: str) -> list[tuple[str, str]]:
    """[(mood, text), ...] - consecutive pieces of speech, each with its mood ('' = neutral). A sound like [laughs]
    becomes its own piece ("!laughs", "") and the mood carries on after it; [whispers] switches to a whisper."""
    parts, mood, pos = [], "", 0
    for m in TAG_RE.finditer(text):
        if text[pos:m.start()].strip():
            parts.append((mood, text[pos:m.start()].strip()))
        tag, pos = m.group(1).lower(), m.end()
        if tag in EMOTES:
            parts.append(("!" + tag, ""))
        else:
            mood = "whisper" if tag == "whispers" else tag
    if text[pos:].strip():
        parts.append((mood, text[pos:].strip()))
    return parts or [("", text)]


# ------------------------------------------------------------------ human delivery (free voices)
# Each agent's attitude when a line has no mood tag, so nobody sounds flat.
ATTITUDE = {"JARVIS": "dry", "FRIDAY": "playful", "PEPPER": "warm", "ATHENA": "calm", "ZEUS": "excited",
            "HERALD": "amused", "STEVE": "cheerful", "VERONICA": "sarcastic", "BANNER": "gentle", "EDITH": "dry",
            "SENTINEL": "stern", "ORACLE": "calm"}
_CUES = [   # words that carry a feeling -> the mood a person would use
    (re.compile(r"\b(sorry|unfortunately|afraid|bad news|missed|failed|overdue|late again)\b", re.I), "concerned"),
    (re.compile(r"\b(congrat|well done|brilliant|amazing|nailed|you did it|proud of you|great news)\w*", re.I), "proud"),
    (re.compile(r"\b(urgent|right now|immediately|asap|leave now|hurry)\b", re.I), "urgent"),
    (re.compile(r"\b(relax|breathe|it's okay|it's alright|take it easy|no rush|rest)\b", re.I), "gentle"),
    (re.compile(r"\b(ha|haha|lol|funny|joke|cheeky)\b", re.I), "amused"),
]


# The agent's mood of the day (from the friendship system) becomes the colour of their voice today.
DAY_MOOD_VOICE = {
    "grumpy": "stern", "stern": "stern", "suspicious": "dry", "vigilant": "serious", "on patrol": "serious",
    "pumped": "excited", "fired up": "excited", "hyped": "excited", "buzzing": "excited", "energetic": "cheerful",
    "motivated": "cheerful", "competitive": "excited", "restless": "urgent", "intense": "serious",
    "cheeky": "playful", "mischievous": "playful", "chatty": "cheerful", "sassy": "sarcastic", "judgmental": "sarcastic",
    "smug": "amused", "quietly amused": "amused", "dry as a bone": "dry", "gossipy": "amused", "charming": "warm",
    "proud": "proud", "encouraging": "warm", "fond": "warm", "cosy": "gentle", "gentle": "gentle", "calm": "calm",
    "worried": "worried", "tired": "tired", "busy": "urgent", "unflappable": "calm", "philosophical": "calm",
    "hyper": "excited", "glowing": "triumphant", "disappointed": "concerned", "focused": "serious",
}
_day = {"key": "", "map": {}}


def day_mood(agent: str) -> str:
    """Today's mood for the agent's voice (cached per day; quietly nothing if the store isn't available)."""
    from datetime import date
    key = date.today().isoformat()
    if _day["key"] != key:
        _day.update(key=key, map={})
    a = agent.upper()
    if a not in _day["map"]:
        try:
            from . import bonds
            from .server import store
            m, _why = bonds.mood(store, a)
            _day["map"][a] = DAY_MOOD_VOICE.get((m or "").lower(), "")
        except Exception:  # noqa: BLE001
            _day["map"][a] = ""
    return _day["map"][a]


def infer_mood(sentence: str, agent: str = "JARVIS", hour: int | None = None) -> str:
    """The feeling of an untagged sentence: from its words, then the agent's attitude. Late at night: softer."""
    for rx, mood in _CUES:
        if rx.search(sentence):
            return mood
    if hour is not None and (hour >= 23 or hour < 6):
        return "gentle"
    if sentence.rstrip().endswith("!"):
        return "cheerful"
    return day_mood(agent) or ATTITUDE.get(agent.upper(), "")


def delivery(text: str, mood: str, agent: str = "JARVIS", hour: int | None = None) -> list[tuple[str, int, int, int]]:
    """Split a mood segment into sentences, each with its own (words, rate %, pitch Hz, pause ms after), so the line
    breathes like a person instead of one flat read: questions lift, exclamations brighten, "..." trails off slowly,
    and small natural variations keep it from sounding robotic. Untagged lines take the agent's attitude, gently."""
    import zlib
    parts = [p for p in re.split(r"(?<=[.!?…])\s+", text.strip()) if p.strip()] or [text]
    out = []
    for i, sent in enumerate(parts):
        m = mood or infer_mood(sent, agent, hour)
        dr, dp = MOODS.get(m, (0, 0))
        if not mood:   # an inferred feeling is played lighter than one the agent chose
            dr, dp = round(dr * .6), round(dp * .6)
        seed = zlib.crc32(sent.encode()) % 7 - 3   # stable small variation, so the same line always sounds the same
        dr += seed
        dp += (seed // 2)
        end = sent.rstrip()[-1:] if sent.strip() else ""
        if sent.rstrip().endswith(("...", "…")):
            dr -= 8
            pause = 420
        elif end == "?":
            dp += 3
            pause = 260
        elif end == "!":
            dr += 3
            dp += 2
            pause = 220
        elif end in ",;:":
            pause = 150
        else:
            pause = 300
        if len(sent) < 18:   # short reactions ("Right." "Oh!") land quicker
            pause -= 80
        if i == len(parts) - 1:
            pause = 0
        out.append((sent, dr, dp, max(0, pause)))
    return out


def silence_mp3(ms: int) -> bytes:
    """Silent MP3 frames matching the free voices' format (24 kHz, 48 kbps, mono): a real pause between sentences."""
    frame = bytes([0xFF, 0xF3, 0x64, 0xC0]) + bytes(140)   # MPEG-2 Layer III, 24 kHz, 48 kbps, mono, silent
    return frame * max(0, round(ms / 24))


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
    from . import gemtts
    if choice == "local":
        from . import localvoice
        if localvoice.ready():
            return "local"
    if choice in ("gemini", "auto") and gemtts.enabled():
        return "gemini"
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
    if prov == "gemini":
        from .gemtts import VOICES
        return "Gemini · " + VOICES.get(agent, VOICES["JARVIS"])[0]
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
    from datetime import datetime as _dt
    hour = _dt.now(settings.tz).hour

    async def say(v: str, words: str, r: str, p: str) -> bytes:
        audio = bytearray()
        async for chunk in edge_tts.Communicate(words, v, rate=r, pitch=p, proxy=proxy).stream():
            if chunk["type"] == "audio":
                audio += chunk["data"]
        return bytes(audio)

    async def go(v: str, base_rate: str, base_pitch: str) -> bytes:
        out = bytearray()
        for mood, words in segments(text):
            if mood.startswith("!"):   # a sound: the agent says it in their own voice
                _said, dr, dp, _vs = EMOTES[mood[1:]]
                out += await say(v, emote_words(agent, mood[1:]), _shift(base_rate, dr, "%"), _shift(base_pitch, dp, "Hz"))
                out += silence_mp3(140)
                continue
            for sent, dr, dp, pause in delivery(words, mood, agent, hour):
                out += await say(v, sent, _shift(base_rate, dr, "%"), _shift(base_pitch, dp, "Hz"))
                out += silence_mp3(pause)
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
    pieces, pending = [], ""
    for mood, words in segments(text):
        if mood.startswith("!"):   # real laughs and sighs from VoiceStudio, attached to the next words
            pending += EMOTES[mood[1:]][3] or (EMOTES[mood[1:]][0] + " ")
            continue
        sound, speed = VS_MOODS.get(mood, ("", 1.0))
        pieces.append((pending + sound + words, speed))
        pending = ""
    if pending:
        pieces.append((pending.strip(), 1.0))
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


def _gemini_tune(agent: str) -> tuple:
    from .gemtts import VOICES
    return ("gemini",) + VOICES.get(agent.upper(), VOICES["JARVIS"])


def synthesize(agent: str, text: str, live: bool = False) -> Path:
    """Return the path of an MP3 of `agent` saying `text` (cached).
    live=True: someone is waiting for this reply right now, so a slow VoiceStudio hands over to the quick voices."""
    prov = provider()
    if prov == "gemini" and live:   # someone is waiting: only use Gemini if it's been quick enough
        from . import gemtts
        spc = gemtts.seconds_per_char()
        if spc is not None and spc * len(speakable(text)) > LIVE_BUDGET_S:
            prov = "edge"
    if prov == "voicestudio" and live and vs_too_slow_for(speakable(text)):
        try:
            import edge_tts  # noqa: F401
            prov = "edge"
        except ImportError:
            pass
    voice_id = voice_for(agent)
    text = speakable(text)[:2500]
    if prov not in ("edge", "voicestudio", "gemini"):
        text = strip_moods(text)
    tune = (_local_tune(agent) if prov == "local" else
            _edge_voice(agent) if prov == "edge" else
            VS_VOICES.get(agent.upper()) if prov == "voicestudio" else
            _gemini_tune(agent) if prov == "gemini" else voice_id)
    key = hashlib.sha256(f"{prov}|{tune}|{settings.elevenlabs_model}|{text}".encode()).hexdigest()[:32]
    path = CACHE / f"{key}.mp3"
    if path.exists():
        return path
    if path.with_suffix(".wav").exists():
        return path.with_suffix(".wav")
    CACHE.mkdir(parents=True, exist_ok=True)
    if prov == "gemini":
        from . import gemtts
        try:
            return gemtts.synthesize(agent, text, path)
        except Exception:  # noqa: BLE001 - Gemini refused or is slow: the free voices take over
            prov = "edge"
            path = CACHE / f"{hashlib.sha256(f'edge|{_edge_voice(agent)}|{text}'.encode()).hexdigest()[:32]}.mp3"
            if path.exists():
                return path
    if prov == "voicestudio":
        try:
            return _voicestudio(text, agent, path)
        except Exception:  # noqa: BLE001 - VoiceStudio slow or stopped: fall back to the free online voices
            _vs_seen.update(at=0.0)
            prov = "edge"
            path = CACHE / f"{hashlib.sha256(f'edge|{_edge_voice(agent)}|{text}'.encode()).hexdigest()[:32]}.mp3"
            if path.exists():
                return path
    if prov == "local":
        return _local(text, agent, path)
    if prov == "edge":
        try:
            _edge(text, agent, path)
        except Exception:
            path.unlink(missing_ok=True)
            from . import localvoice
            if localvoice.ready():   # no internet (or the online voice failed): the offline natural voice takes over
                return _local(text, agent, CACHE / f"local-{path.stem}.mp3")
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


def _local_tune(agent: str) -> tuple:
    from .localvoice import CAST
    return ("local",) + CAST.get(agent.upper(), CAST["JARVIS"])


def _local(text: str, agent: str, path: Path) -> Path:
    from datetime import datetime as _dt
    from . import localvoice
    hour = _dt.now(settings.tz).hour
    pieces = []
    for mood, words in segments(text):
        if mood.startswith("!"):
            _said, dr, dp, _vs = EMOTES[mood[1:]]
            pieces.append((emote_words(agent, mood[1:]), dr, dp, 140))
        else:
            pieces += delivery(words, mood, agent, hour)
    if path.with_suffix(".wav").exists():
        return path.with_suffix(".wav")
    return localvoice.synthesize(agent, pieces, path)


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
