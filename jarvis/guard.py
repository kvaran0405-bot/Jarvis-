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


REFUSAL = "🔒 Blocked: banking and payments are off-limits to JARVIS (matched '{word}'). Do this yourself."
