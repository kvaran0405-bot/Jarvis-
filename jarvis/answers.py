"""Natural spoken answers to whatever JARVIS last asked: "yes", "nah leave it", "send the second one".

Only short, whole-sentence answers count, and they go to the most recent open question (a proposal, an e-mail
with suggested replies, or a message waiting for approval). Anything longer is treated as a normal order.
"""
from __future__ import annotations

import re

_SEP = r"[\s,]+"
_FILLER = r"(?:(?:um+|uh+|oh|hmm+|well)" + _SEP + r")?"
_TAIL = r"(?:" + _SEP + r"(?:please|thanks|thank you|jarvis|sir|mate|bro|boss))*[\s.!,]*$"
_YES_WORDS = ["yes", "yeah", "yep", "yup", "ya", "sure", "ok", "okay", "alright", "absolutely", "definitely",
              "do it", "go ahead", "go for it", "send it", "approve it", "approve", "please do", "sounds good",
              "let's do it", "lets do it", "yes please", "of course", "why not"]
_NO_WORDS = ["no", "nah", "nope", "don't", "dont", "do not", "skip it", "skip", "leave it", "cancel it", "cancel",
             "not now", "ignore it", "ignore", "no thanks", "forget it", "not really", "pass"]


def _phrase(words: list[str]) -> str:
    alts = "|".join(sorted((w.replace(" ", _SEP) for w in words), key=len, reverse=True))
    return rf"(?:{alts})"


def _answer(words: list[str]) -> re.Pattern:
    w = _phrase(words)
    return re.compile(rf"^\s*{_FILLER}{w}(?:{_SEP}{w}){{0,2}}{_TAIL}", re.I)


YES = _answer(_YES_WORDS)
NO = _answer(_NO_WORDS)
OPTION = re.compile(r"^\s*" + _FILLER + r"(?:(?:send|go with|pick|choose|use|reply with)" + _SEP + r")?"
                    r"(?:option" + _SEP + r"|reply" + _SEP + r")?"
                    r"(a|b|c|d|the" + _SEP + r"(?:first|second|third|fourth)|first|second|third|fourth)"
                    r"(?:" + _SEP + r"one)?" + _TAIL, re.I)
ORDINAL = {"a": 0, "b": 1, "c": 2, "d": 3, "first": 0, "second": 1, "third": 2, "fourth": 3}


def latest_open(store) -> tuple[str, dict] | None:
    """The most recent thing waiting for the owner: ('proposal'|'suggestion'|'outbox', row)."""
    items = [("proposal", p) for p in store.list_proposals("open", 1)]
    items += [("suggestion", s) for s in store.list_suggestions("open", 1)]
    items += [("outbox", m) for m in store.list_outbox("pending", 1)]
    if not items:
        return None
    return max(items, key=lambda kv: kv[1]["created"])


def parse(text: str) -> tuple[str, int | None] | None:
    """('yes'|'no'|'option', index) for a bare answer, else None."""
    if YES.match(text):
        return "yes", None
    if NO.match(text):
        return "no", None
    if m := OPTION.match(text):
        return "option", ORDINAL[re.sub(r"^the[\s,]+", "", m.group(1).lower())]
    return None


def spoken_question(kind: str, row: dict, agent: str, owner: str) -> str:
    """What the dashboard says out loud when something new needs an answer."""
    if kind == "proposal":
        return f"{owner}, {agent.title()} suggests: {row['title']}. Shall I?"
    if kind == "suggestion":
        labels = ", ".join(f"{'ABCD'[i]}, {o['label']}" for i, o in enumerate(row["options"]))
        return f"{row['gist']} I can reply: {labels}. Which one?"
    return f"{owner}, a message is waiting for your OK."
