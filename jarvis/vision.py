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
    prompt = PROMPT + (f"\nThe owner also asked: {question}" if question else "")
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
