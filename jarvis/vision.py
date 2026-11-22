"""Photo understanding: the owner sends a photo (a poster, a lecture slide, a receipt, an event setup) and JARVIS reads it.
Uses whichever brain can see: Gemini (free), the Claude API, or the Claude plan through Claude Code."""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import subprocess
from pathlib import Path

from . import brain
from .config import settings

PROMPT = ("Describe this photo for a personal assistant who can't see it. Transcribe every piece of text exactly "
          "(names, dates, times, places, prices, amounts, codes of courses). Then say in one line what kind of thing "
          "it is (event poster, lecture slide, receipt, timetable, screenshot, food, outfit, venue setup...). "
          "If it shows a bank card, ID or password, say only 'private document' and nothing else.")


def describe(path: str | Path, question: str = "") -> str:
    path = Path(path)
    data = path.read_bytes()
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    return ask(data, mime, PROMPT + (f"\nThe owner also asked: {question}" if question else ""))


def ask(data: bytes, mime: str, prompt: str) -> str:
    """Show an image to whichever brain can see, with any prompt."""
    errors = []
    if (st := _store()) is not None and brain.get_mode(st)["mode"] == "paused":
        raise RuntimeError("I'm paused, so I can't look at photos right now. Say 'resume' first.")
    if settings.gemini_key:
        try:
            from .brains import _gemini_call
            out = _gemini_call({"contents": [{"role": "user", "parts": [
                {"inline_data": {"mime_type": mime, "data": base64.b64encode(data).decode()}}, {"text": prompt}]}]})
            return "".join(p.get("text", "") for p in out["candidates"][0]["content"]["parts"]).strip()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Gemini: {exc}")
    if brain.ready("api"):
        try:
            import anthropic
            msg = anthropic.Anthropic().messages.create(
                model=settings.model, max_tokens=1500,
                messages=[{"role": "user", "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": mime,
                                                 "data": base64.b64encode(data).decode()}},
                    {"type": "text", "text": prompt}]}])
            return "".join(b.text for b in msg.content if b.type == "text").strip()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Claude API: {exc}")
    if brain.ready("pro"):
        try:
            return _via_claude_code(data, mime, prompt)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Claude plan: {exc}")
    raise RuntimeError("No brain could look at the photo. " + "; ".join(errors))


def _via_claude_code(data: bytes, mime: str, prompt: str) -> str:
    msg = {"type": "user", "message": {"role": "user", "content": [
        {"type": "image", "source": {"type": "base64", "media_type": mime, "data": base64.b64encode(data).decode()}},
        {"type": "text", "text": prompt}]}}
    cmd = [brain.claude_cli(), "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
           "--tools", "", "--model", settings.pro_model]
    proc = subprocess.run(cmd, input=json.dumps(msg) + "\n", capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=120, env={**os.environ})
    for line in proc.stdout.splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "result":
            if ev.get("is_error"):
                raise RuntimeError(str(ev.get("result"))[:200])
            return str(ev.get("result", "")).strip()
    raise RuntimeError((proc.stderr or "no answer")[-300:])


def _store():
    from . import telegram as tg
    return tg._store


LIVE = {
    "scan": "Look at this camera view like JARVIS scanning a room for Tony. Point out the 1-4 most useful things you see "
            "(objects, text, problems, opportunities) with a short, witty, helpful comment.",
    "ask": "Answer the owner's question about what the camera sees, briefly and usefully.",
    "meal": "This is food. Name the dish(es), estimate the portion, and give rough protein (g) and calories, plus one tip "
            "for the owner's fitness goals. Say clearly these are estimates.",
    "outfit": "The owner is choosing an outfit. Judge fit, colours and occasion honestly and kindly; pick the best option.",
}


def live(data: bytes, mime: str, mode: str = "scan", question: str = "") -> dict:
    """Camera vision for the phone: a short spoken answer plus labelled boxes for the AR overlay."""
    import json
    import re
    prompt = (LIVE.get(mode, LIVE["scan"]) + (f"\nThe owner asks: {question}" if question else "") +
              "\nIf you see a bank card, ID, password or a banking screen, answer only 'Private, Sir.' with no items.\n"
              'Reply ONLY with JSON: {"answer": "one or two spoken sentences", "items": [{"label": "short name", '
              '"note": "3-6 words", "box": [x, y, w, h]}]} where box values are fractions 0-1 of the image '
              "(x,y = top-left). At most 5 items.")
    raw = ask(data, mime, prompt)
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        out = json.loads(m.group(0)) if m else {"answer": raw.strip(), "items": []}
    except ValueError:
        out = {"answer": raw.strip()[:400], "items": []}
    items = []
    for it in (out.get("items") or [])[:5]:
        try:
            x, y, w, h = (max(0.0, min(1.0, float(v))) for v in it.get("box", [])[:4])
            items.append({"label": str(it.get("label", ""))[:40], "note": str(it.get("note", ""))[:60], "box": [x, y, w, h]})
        except (TypeError, ValueError):
            continue
    return {"answer": str(out.get("answer", ""))[:500], "items": items}
