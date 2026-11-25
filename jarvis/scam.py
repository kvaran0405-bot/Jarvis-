"""SENTINEL's scam shield: spots scam and phishing messages, e-mails and fake job offers before the owner taps.

Singapore's common scams: fake parcel "pay a fee", "your account is suspended / verify now", Telegram/WhatsApp
"task" and "like videos, earn $300 a day" jobs, fake bank or government (MOM, ICA, IRAS, SPF) officers, lucky
draws and prizes, investment and crypto "guaranteed returns", and links that aren't the real site.
A score from 0 to 100 plus the reasons; 60+ is flagged. Fast and offline (no AI needed).
"""
from __future__ import annotations

import re

SIGNS = [   # (pattern, points, reason)
    (r"\b(urgent|immediately|within 24 hours|final notice|last warning|act now|account (?:will be )?(?:suspended|locked|deactivated|closed))\b", 20, "pressure to act fast"),
    (r"\b(verify|confirm|update|unlock|reactivate)\b.{0,30}\b(account|identity|details|card|payment|password)\b", 25, "asks you to verify your account"),
    (r"\b(parcel|package|delivery|shipment)\b.{0,60}\b(fee|pay|held|failed|reschedule|customs)\b", 40, "parcel 'fee' or 'held' trick"),
    (r"\b(won|winner|congratulations|lucky draw|prize|reward|claim your|free gift)\b", 25, "prize or lucky draw"),
    (r"\b(earn|make)\b.{0,20}\$?\d{2,4}.{0,20}\b(a day|per day|daily|an hour|per hour|weekly)\b", 35, "'earn $X a day' job"),
    (r"\b(like|rate|review|subscribe to)\b.{0,30}\b(videos?|products?|hotels?|apps?)\b.{0,40}\b(earn|commission|paid)\b", 40, "'task' job (like and earn)"),
    (r"\b(no experience (?:needed|required)|work from home|part[- ]time).{0,60}\b(telegram|whatsapp)\b", 30, "job that moves you to Telegram/WhatsApp"),
    (r"\b(guaranteed|risk[- ]free|double your|high returns?|passive income|crypto|usdt|forex signal)\b", 25, "too-good-to-be-true investment"),
    (r"\b(mom|ica|iras|cpf board|spf|police|interpol|customs|court)\b.{0,60}\b(case|investigation|warrant|fine|arrest|transfer)\b", 40, "fake government officer"),
    (r"\b(gift ?cards?|itunes card|google play card|steam card)\b.{0,40}\b(pay|buy|send)\b", 35, "asks for gift cards"),
    (r"\b(otp|one[- ]time password|verification code|pin)\b.{0,40}\b(send|share|give|tell)\b", 45, "asks for your OTP/PIN"),
    (r"\b(transfer|send|pay|move)\b.{0,25}\b(funds?|money|deposit|payment)\b.{0,25}\b(now|immediately|today|urgently|to (?:a |this )?(?:safe|secure|new) account)\b", 25, "asks you to move money fast"),
    (r"\b(kindly|dear (?:customer|user|valued))\b", 10, "generic greeting"),
    (r"(?:https?://)?\b(?:bit\.ly|tinyurl\.com|t\.co|cutt\.ly|rb\.gy|is\.gd|shorturl\.at|s\.id|ow\.ly)/", 20, "shortened link"),
    (r"https?://[^\s/]*(?:dbs|posb|ocbc|uob|singpass|gov|singpost|ninjavan|shopee|lazada|paypal|apple|microsoft)[^\s/]*\.(?!com\.sg\b|gov\.sg\b|com\b|sg\b)[a-z]{2,10}\b", 40, "look-alike website"),
    (r"https?://\d{1,3}(?:\.\d{1,3}){3}", 30, "link to a bare IP address"),
    (r"\bt\.me/|\bwa\.me/", 15, "pushes you to a Telegram/WhatsApp chat"),
]
_RX = [(re.compile(p, re.I | re.S), pts, why) for p, pts, why in SIGNS]
TRUSTED_SENDERS = re.compile(r"@(?:[a-z0-9-]+\.)*(?:gov\.sg|dbs\.com|ocbc\.com|uobgroup\.com|singpost\.com|shopee\.sg|lazada\.sg|"
                             r"google\.com|apple\.com|linkedin\.com|jobstreet\.com|mycareersfuture\.gov\.sg)>?$", re.I)


def check(text: str, sender: str = "") -> dict:
    t = f"{text or ''}"
    score, why = 0, []
    for rx, pts, reason in _RX:
        if rx.search(t):
            score += pts
            why.append(reason)
    if sender and TRUSTED_SENDERS.search(sender.strip()):
        score -= 35   # mail really from the bank's / government's own domain
    score = max(0, min(100, score))
    return {"score": score, "scam": score >= 60, "reasons": why[:4]}


def warning(text: str, sender: str = "") -> str:
    """A one-line SENTINEL warning, or '' if it looks fine."""
    c = check(text, sender)
    if not c["scam"]:
        return ""
    return f"⚠️ Looks like a scam ({', '.join(c['reasons'][:3])}). Don't tap links, pay, or share codes."
