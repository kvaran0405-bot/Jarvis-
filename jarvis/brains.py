"""Alternative brains: your Claude plan (through Claude Code) and Google Gemini (free tier).

Both use the exact same JARVIS tools as the API brain:
- Claude Code reaches them through JARVIS's local MCP endpoint (/mcp/<agent>), served by the running JARVIS app.
- Gemini gets them as function declarations and JARVIS runs them directly.
"""
from __future__ import annotations

import json
import re
import subprocess
import threading
import urllib.error
import urllib.request
from typing import Callable

from . import brain
from .config import ROOT, settings
from .tools import REGISTRY, execute

WORK = ROOT / "data" / "claude-work"


class LimitReached(Exception):
    """The brain refused because a usage / rate limit was hit."""


class BrainError(Exception):
    pass


# ================================================================ Claude Code (your Pro / Max plan)
LIMIT_RE = re.compile(r"(usage|rate|session|weekly)\s*limit|limit reached|hit your limit|out of (extra )?usage", re.I)


def run_pro(agent, prompt: str, system_text: str, tool_names: list[str], *, depth: int, effort: str,
            session_id: str | None, on_text: Callable[[str], None] | None, log: Callable[[str], None],
            model: str | None = None, approved: bool = False) -> tuple[str, str | None]:
    """Run one turn through `claude -p`. Returns (reply, session_id for the next turn)."""
    cli = brain.claude_cli()
    if not cli:
        raise BrainError("Claude Code is not installed - see README 'Use your Claude plan'.")
    WORK.mkdir(parents=True, exist_ok=True)
    sys_file = WORK / f"system-{agent.name}.md"
    sys_file.write_text(system_text, encoding="utf-8")
    mcp_file = WORK / f"mcp-{agent.name}-{depth}{'-ok' if approved else ''}.json"
    mcp_file.write_text(json.dumps({"mcpServers": {"jarvis": {
        "type": "http",
        "url": f"http://127.0.0.1:{settings.port}/mcp/{agent.name}?depth={depth}&approved={int(approved)}",
        "headers": {"X-Jarvis-Token": settings.bridge_token},
    }}}), encoding="utf-8")

    cmd = [cli, "-p",
           "--output-format", "stream-json", "--verbose", "--include-partial-messages",
           "--system-prompt-file", str(sys_file),
           "--mcp-config", str(mcp_file), "--strict-mcp-config",
           "--tools", "WebSearch,WebFetch",                      # no file/terminal tools: only JARVIS's own
           "--allowedTools", "mcp__jarvis,WebSearch,WebFetch",
           "--permission-mode", "dontAsk",
           "--model", model if model and not model.startswith("gemini") else settings.pro_model,
           "--effort", effort]
    if session_id:
        cmd += ["--resume", session_id]

    proc = subprocess.Popen(cmd, cwd=WORK, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, encoding="utf-8", errors="replace")
    err_lines: list[str] = []
    threading.Thread(target=lambda: err_lines.extend(proc.stderr), daemon=True).start()
    proc.stdin.write(prompt)
    proc.stdin.close()

    new_session, result, is_error, streamed = session_id, None, False, False
    for line in proc.stdout:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = obj.get("type")
        if obj.get("session_id"):
            new_session = obj["session_id"]
        if kind == "stream_event":
            ev = obj.get("event", {})
            delta = ev.get("delta", {}) if ev.get("type") == "content_block_delta" else {}
            if delta.get("type") == "text_delta" and on_text:
                on_text(delta.get("text", ""))
                streamed = True
            elif ev.get("type") == "message_stop" and on_text and streamed:
                on_text("\n")
        elif kind == "assistant":
            for block in obj.get("message", {}).get("content", []):
                if block.get("type") == "tool_use" and not block.get("name", "").startswith("mcp__jarvis"):
                    log(f"{block.get('name')} {json.dumps(block.get('input', {}))[:120]}")
        elif kind == "result":
            result, is_error = obj.get("result") or "", bool(obj.get("is_error"))
    proc.wait(timeout=60)

    text = (result or "").strip()
    problem = text if is_error or proc.returncode else ""
    if not problem and result is None:
        problem = " ".join(err_lines)[-500:] or f"Claude Code exited with code {proc.returncode}"
    if problem:
        if LIMIT_RE.search(problem):
            raise LimitReached(problem[:300])
        if re.search(r"log ?in|/login|authenticat|api key", problem, re.I):
            raise BrainError("Claude Code isn't logged in. Open a terminal, run  claude  once and log in with "
                             "your Claude account.")
        raise BrainError(problem[:400])
    return text, new_session


# ================================================================ Google Gemini (free tier)
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def _gemini_schema(schema: dict) -> dict:
    """Gemini accepts an OpenAPI-style subset of JSON Schema."""
    keep = {"type", "description", "properties", "required", "enum", "items", "minimum", "maximum", "format"}
    out = {k: v for k, v in schema.items() if k in keep}
    if "properties" in out:
        out["properties"] = {k: _gemini_schema(v) for k, v in out["properties"].items()}
    if "items" in out:
        out["items"] = _gemini_schema(out["items"])
    return out


def gemini_tools(tool_names: list[str]) -> list[dict]:
    decls = []
    for name in tool_names:
        t = REGISTRY[name]
        d = {"name": t.name, "description": t.description}
        if t.properties:
            d["parameters"] = _gemini_schema(t.schema()["input_schema"])
        decls.append(d)
    return [{"functionDeclarations": decls}] if decls else []


def _gemini_call(body: dict, model: str | None = None) -> dict:
    req = urllib.request.Request(GEMINI_URL.format(model=model or settings.gemini_model), data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "x-goog-api-key": settings.gemini_key})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        if exc.code == 429:
            raise LimitReached(f"Gemini free limit reached: {detail}") from None
        raise BrainError(f"Gemini error {exc.code}: {detail}") from None


def run_gemini(agent, contents: list, system_text: str, tool_names: list[str], ctx, *,
               on_text: Callable[[str], None] | None, log: Callable[[str], None], max_steps: int = 12) -> str:
    """Run one turn on Gemini. `contents` is the running conversation (appended to in place)."""
    if not settings.gemini_key:
        raise BrainError("No GEMINI_API_KEY in .env")
    tools = gemini_tools(tool_names)
    for _ in range(max_steps):
        body = {"systemInstruction": {"parts": [{"text": system_text}]}, "contents": contents}
        if tools:
            body["tools"] = tools
        data = _gemini_call(body, agent.model if agent.model.startswith("gemini") else None)
        cands = data.get("candidates") or []
        if not cands:
            reason = (data.get("promptFeedback") or {}).get("blockReason", "no answer")
            return f"I couldn't answer that ({reason})."
        content = cands[0].get("content") or {"role": "model", "parts": []}
        content.setdefault("role", "model")
        contents.append(content)  # keep parts verbatim (incl. thought signatures) for the next request
        parts = content.get("parts", [])
        calls = [p["functionCall"] for p in parts if "functionCall" in p]
        text = "".join(p.get("text", "") for p in parts if "text" in p and not p.get("thought"))
        if not calls:
            if on_text and text:
                on_text(text)
            return text.strip() or "Done."
        responses = []
        for call in calls:
            name, args = call.get("name", ""), call.get("args") or {}
            log(f"{name} {json.dumps(args, default=str)[:140]}")
            if name not in tool_names:
                output, is_error = f"Tool {name} is not available to {agent.name}", True
            else:
                output, is_error = execute(name, ctx, args)
            fr = {"name": name, "response": {"error" if is_error else "result": output[:20000]}}
            if call.get("id"):
                fr["id"] = call["id"]
            responses.append({"functionResponse": fr})
        contents.append({"role": "user", "parts": responses})
    return "I've hit my step limit for this request; progress so far is saved."
