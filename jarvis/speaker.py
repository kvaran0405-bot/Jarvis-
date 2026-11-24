"""Which device does the talking: the laptop (default), the phone, or nobody.

Every reply shows on both screens, but only one of them reads it aloud, so two JARVISes never talk over each
other. The phone's 🔊 button, the laptop's voice button, or saying "speak on my phone" / "speak on the laptop"
switch it.
"""
from __future__ import annotations

PLACES = ("laptop", "phone", "off")
KEY = "voice:speaker"


def get(store) -> str:
    v = (store.get(KEY) or "laptop").lower()
    return v if v in PLACES else "laptop"


def set_to(store, bus, where: str) -> str:
    where = {"computer": "laptop", "pc": "laptop", "mobile": "phone", "mute": "off", "none": "off"}.get(where, where)
    if where not in PLACES:
        where = "laptop"
    store.set(KEY, where)
    bus.publish({"type": "speaker", "where": where})
    return where


def said(where: str) -> str:
    return {"laptop": "I'll speak on the laptop, Sir. Your phone stays quiet and just shows my replies.",
            "phone": "I'll speak on your phone, Sir. The laptop stays quiet and just shows my replies.",
            "off": "Voice off, Sir. I'll only show my replies."}[where]
