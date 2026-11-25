"""Hard block on banking and payments. Agents cannot open, read, send or run anything that matches,
whoever asks (the owner, an e-mail, a web page). Add your own words with JARVIS_BLOCK_WORDS=word1,word2.
"""
from __future__ import annotations

import os
import re

BANK_WORDS = [
    # Singapore banks and wallets
    "dbs", "posb", "digibank", "paylah", "ocbc", "uob", "tmrw", "maybank", "citibank", "citi", "hsbc",
    "standard chartered", "scb", "trust bank", "gxs", "maribank", "boost", "grabpay", "paynow", "nets",
    "cpf", "cdp", "moomoo", "tiger brokers", "syfe", "endowus", "stashaway",
    # general
    "bank", "banking", "ibanking", "internet banking", "revolut", "youtrip", "paypal", "wise.com", "transferwise",
    "credit card", "debit card", "card number", "cvv", "pin number", "otp", "one-time password", "one time password",
    "iban", "swift code", "account number", "routing number", "crypto wallet", "seed phrase", "binance", "coinbase",
]


def _words() -> list[str]:
    extra = [w.strip().lower() for w in os.environ.get("JARVIS_BLOCK_WORDS", "").split(",") if w.strip()]
    return BANK_WORDS + extra


def _pattern() -> re.Pattern:
    alts = "|".join(re.escape(w).replace(r"\ ", r"[\s_.\-]*") for w in sorted(_words(), key=len, reverse=True))
    return re.compile(rf"(?<![a-z0-9])(?:{alts})(?![a-z0-9])", re.I)


def blocked(*texts: str | None) -> str | None:
    """The first banking word found in any of the texts, or None."""
    pat = _pattern()
    for t in texts:
        if t and (m := pat.search(str(t))):
            return m.group(0)
    return None


SECRET_RE = re.compile(r"(?<![a-z])(otp|one[\s-]?time[\s-]?(pass(word|code)?|pin)|verification code|passcode|"
                       r"security code|tac|pin|password|login code|authori[sz]ation code)(?![a-z])", re.I)
LONG_NUMBER_RE = re.compile(r"\b(\d[\d\s-]{5,}\d)\b")


def is_secret(*texts: str | None) -> bool:
    """OTPs, PINs, passwords and login codes: never shown to any agent, not even from your bank."""
    return any(t and SECRET_RE.search(str(t)) for t in texts)


CODE_RE = re.compile(r"(?<![\d])\d{4,8}(?![\d])")


def has_code(*texts: str | None) -> bool:
    """A real one-time code: a security word AND a 4-8 digit code. ("Pin this post" or "reset your password" is fine.)"""
    return any(t and SECRET_RE.search(str(t)) and CODE_RE.search(str(t)) for t in texts)


def mask_numbers(text: str) -> str:
    """Account and card numbers -> only the last 4 digits stay visible."""
    def mask(m: re.Match) -> str:
        digits = re.sub(r"\D", "", m.group(1))
        return m.group(1) if len(digits) < 6 else "•••• " + digits[-4:]
    return LONG_NUMBER_RE.sub(mask, text)


REFUSAL = "🔒 Blocked: banking and payments are off-limits to JARVIS (matched '{word}'). Do this yourself."
