"""Alternative brains: your Claude plan (through Claude Code) and Google Gemini (free tier).

Both use the exact same JARVIS tools as the API brain:
- Claude Code reaches them through JARVIS's local MCP endpoint (/mcp/<agent>), served by the running JARVIS app.
- Gemini gets them as function declarations and JARVIS runs them directly.
"""
from __future__ import annotations

import json
import queue
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


class ProSession:
    """A Claude Code process kept running between messages (stream-json in and out), so a chat reply starts in about
    a second instead of paying Claude Code's start-up on every message. One per agent + effort + model."""

    MAX_TURNS = 40   # then start fresh, so the conversation doesn't grow forever

    def __init__(self, agent, system_text: str, effort: str, model: str | None):
        cli = brain.claude_cli()
        if not cli:
            raise BrainError("Claude Code is not installed - see README 'Use your Claude plan'.")
        WORK.mkdir(parents=True, exist_ok=True)
        sys_file = WORK / f"system-{agent.name}-live.md"
        sys_file.write_text(system_text, encoding="utf-8")
        mcp_file = WORK / f"mcp-{agent.name}-live.json"
        mcp_file.write_text(json.dumps({"mcpServers": {"jarvis": {
            "type": "http", "url": f"http://127.0.0.1:{settings.port}/mcp/{agent.name}?depth=0&approved=0",
            "headers": {"X-Jarvis-Token": settings.bridge_token}}}}), encoding="utf-8")
        cmd = [cli, "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose",
               "--include-partial-messages", "--system-prompt-file", str(sys_file),
               "--mcp-config", str(mcp_file), "--strict-mcp-config",
               "--tools", "WebSearch,WebFetch", "--allowedTools", "mcp__jarvis,WebSearch,WebFetch",
               "--permission-mode", "dontAsk",
               "--model", model if model and not model.startswith("gemini") else settings.pro_model,
               "--effort", effort]
        self.proc = subprocess.Popen(cmd, cwd=WORK, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace", bufsize=1)
        self.lines: "queue.Queue[str | None]" = queue.Queue()
        self.err: list[str] = []
        threading.Thread(target=self._pump, daemon=True).start()
        threading.Thread(target=lambda: self.err.extend(self.proc.stderr), daemon=True).start()
        self.turns = 0
        self.lock = threading.Lock()

    def _pump(self) -> None:
        for line in self.proc.stdout:
            self.lines.put(line)
        self.lines.put(None)   # process ended

    def alive(self) -> bool:
        return self.proc.poll() is None and self.turns < self.MAX_TURNS

    def close(self) -> None:
        try:
            self.proc.stdin.close()
            self.proc.terminate()
        except Exception:  # noqa: BLE001
            pass

    def ask(self, prompt: str, on_text: Callable[[str], None] | None, log: Callable[[str], None],
            timeout: float = 600) -> str:
        with self.lock:
            self.turns += 1
            self.proc.stdin.write(json.dumps({"type": "user", "message": {"role": "user", "content": prompt}}) + "\n")
            self.proc.stdin.flush()
            streamed = False
            while True:
                line = self.lines.get(timeout=timeout)
                if line is None:
                    raise BrainError(" ".join(self.err)[-400:] or "Claude Code stopped")
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                kind = obj.get("type")
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
                    text = (obj.get("result") or "").strip()
                    if obj.get("is_error"):
                        if LIMIT_RE.search(text):
                            raise LimitReached(text[:300])
                        raise BrainError(text[:400] or "Claude Code error")
                    return text


_sessions: dict[tuple, ProSession] = {}
_sessions_lock = threading.Lock()


def run_pro_live(agent, prompt: str, system_text: str, *, effort: str, on_text, log, model: str | None = None) -> str:
    """Chat turn on a kept-alive Claude Code session (falls back to a fresh one if it died)."""
    key = (agent.name, effort, model or settings.pro_model)
    with _sessions_lock:
        sess = _sessions.get(key)
        if sess is None or not sess.alive():
            if sess:
                sess.close()
            sess = _sessions[key] = ProSession(agent, system_text, effort, model)
    try:
        return sess.ask(prompt, on_text, log)
    except (BrainError, queue.Empty):
        close_sessions(agent.name)
        raise


def close_sessions(agent_name: str | None = None) -> None:
    with _sessions_lock:
        for key in [k for k in _sessions if agent_name is None or k[0] == agent_name]:
            _sessions.pop(key).close()


def warm_up(agent, system_text: str, effort: str) -> None:
    """Start JARVIS's chat sessions in the background so the very first reply is quick too
    (the voice one on the quick model, and the typed one)."""
    def go():
        try:
            for model in dict.fromkeys([settings.voice_model if effort == "low" else "", ""]):
                key = (agent.name, effort, model or settings.pro_model)
                with _sessions_lock:
                    if key not in _sessions:
                        _sessions[key] = ProSession(agent, system_text, effort, model or None)
        except Exception:  # noqa: BLE001 - not fatal: the first message will start it
            pass
    threading.Thread(target=go, daemon=True).start()


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
    if out.get("type") == "array" and not out.get("items"):
        out["items"] = {"type": "string"}   # Gemini rejects a list with no item type (it broke every Gemini reply)
    if out.get("type") == "object" and "properties" in out and not out["properties"]:
        out.pop("properties")
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


_quick_ok = {"on": True}


# Each free Gemini model has its own daily allowance: when one is used up, the next one answers instead.
GEMINI_SPARES = ["gemini-flash-latest", "gemini-2.5-flash", "gemini-flash-lite-latest", "gemini-2.5-flash-lite"]
_gem_spent: dict[str, float] = {}   # model -> time its allowance is expected back


def gemini_resting() -> bool:
    """True when every free Gemini model is used up for now (so fast mode goes straight to the main brain)."""
    import time
    now = time.time()
    return all(_gem_spent.get(m, 0) > now for m in dict.fromkeys([settings.gemini_model, *GEMINI_SPARES]))


def _gemini_once(body: dict, model: str) -> dict:
    req = urllib.request.Request(GEMINI_URL.format(model=model), data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "x-goog-api-key": settings.gemini_key})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read())


def _gemini_call(body: dict, model: str | None = None) -> dict:
    import time
    first = model or settings.gemini_model
    order = [first] if model and model != settings.gemini_model else list(dict.fromkeys([first, *GEMINI_SPARES]))
    last = ""
    for m in order:
        if _gem_spent.get(m, 0) > time.time():
            continue
        try:
            return _gemini_once(body, m)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:400]
            if exc.code == 429:
                _gem_spent[m] = time.time() + (3600 if "PerDay" in detail or "per day" in detail.lower() else 120)
                last = detail
                continue
            if exc.code == 404:
                continue
            if exc.code == 400 and "thinking" in detail.lower() and "thinkingConfig" in json.dumps(body.get("generationConfig", {})):
                plain = {**body, "generationConfig": {k: v for k, v in body["generationConfig"].items() if k != "thinkingConfig"}}
                return _gemini_call(plain, m)
            raise BrainError(f"Gemini error {exc.code}: {detail}") from None
    if not last:   # nothing was rate-limited: the model(s) just aren't offered (retired or not for this key)
        raise BrainError(f"Gemini model not available: {', '.join(order)}")
    raise LimitReached("Gemini's free allowance is used up for now" + (" (it refills daily)" if "day" in last.lower() else ""))


def run_gemini(agent, contents: list, system_text: str, tool_names: list[str], ctx, *,
               on_text: Callable[[str], None] | None, log: Callable[[str], None], max_steps: int = 12,
               quick: bool = False) -> str:
    """Run one turn on Gemini. `contents` is the running conversation (appended to in place).
    quick=True (spoken questions): no long silent "thinking" first, so the answer starts right away."""
    if not settings.gemini_key:
        raise BrainError("No GEMINI_API_KEY in .env")
    tools = gemini_tools(tool_names)
    for _ in range(max_steps):
        body = {"systemInstruction": {"parts": [{"text": system_text}]}, "contents": contents}
        if tools:
            body["tools"] = tools
        if quick and _quick_ok["on"]:
            body["generationConfig"] = {"thinkingConfig": {"thinkingBudget": 0}}
        try:
            data = _gemini_call(body, agent.model if agent.model.startswith("gemini") else None)
        except BrainError as exc:
            if "generationConfig" not in body or "400" not in str(exc):
                raise
            _quick_ok["on"] = False   # this model insists on thinking: never ask again
            body.pop("generationConfig")
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
