"""The agent engine: runs an agent's tool-use loop on Claude."""
from __future__ import annotations

import json
import threading
from datetime import datetime

from .agents import AGENTS, Agent, roster
from .bus import Bus
from .config import Settings
from .store import Store
from .tools import REGISTRY, ToolContext, execute

MAX_STEPS = 16
CHAT_MAX_MESSAGES = 60  # start a fresh conversation after this many messages

RULES = """\
Operating rules:
- You work for {owner}. Address them as "{owner}". Be concise, warm and decisive - a capable chief of staff, not a chatbot.
- Act, don't just advise: when something should be tracked, create or update it with your tools.
- Never invent data. If a tool returns nothing, say so. Dates are in the owner's timezone ({tz}).
- You may only affect the owner's own JARVIS records and send reports to the owner. Never contact third parties,
  make purchases, move money, or submit anything on the owner's behalf - prepare a draft and create a task instead.
- When the owner shares a lasting fact about themselves, store it with `remember`.
- Output Markdown. Keep spoken-style replies short (2-6 sentences) unless a report or document is requested."""


class Engine:
    def __init__(self, store: Store, bus: Bus, settings: Settings):
        self.store, self.bus, self.settings = store, bus, settings
        self._client = None
        self._chats: dict[str, list] = {}
        self._locks: dict[str, threading.Lock] = {name: threading.Lock() for name in AGENTS}

    # ------------------------------------------------------------ client
    @property
    def client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic()
        return self._client

    # ------------------------------------------------------------ prompts
    def system_prompt(self, agent: Agent) -> str:
        team = "\n".join(f"- {a['name']}: {a['title']}" for a in roster())
        profile = self.settings.profile() or "(no profile written yet - learn about the owner and use `remember`)"
        return (
            f"You are {agent.name}, the {agent.title} agent of JARVIS OS, a personal multi-agent system.\n\n"
            f"Mission: {agent.mission}\n\n"
            f"{RULES.format(owner=self.settings.owner_name, tz=self.settings.timezone)}\n\n"
            f"The team:\n{team}\n\n"
            f"About the owner (profile.md):\n{profile}"
        )

    def _context_block(self) -> str:
        now = datetime.now(self.settings.tz)
        facts = [m["fact"] for m in self.store.memories(40)]
        mem = "\n".join(f"- {f}" for f in facts) if facts else "- (none yet)"
        return (f"[Context] Now: {now.strftime('%A %Y-%m-%d %H:%M')} ({self.settings.timezone}).\n"
                f"Known facts about the owner:\n{mem}\n[/Context]\n\n")

    def tools_for(self, agent: Agent) -> list[dict]:
        tools = [REGISTRY[name].schema() for name in agent.tools if name in REGISTRY]
        if agent.web:
            tools.append({"type": "web_search_20260209", "name": "web_search", "max_uses": 5})
        return tools

    # ------------------------------------------------------------ main loop
    def run(self, agent_name: str, prompt: str, *, chat: bool = False, depth: int = 0) -> str:
        """Run `prompt` through an agent. chat=True keeps a running conversation (dashboard chat)."""
        agent = AGENTS.get(agent_name.upper())
        if agent is None:
            return f"No agent named {agent_name}. Available: {', '.join(AGENTS)}."
        if not self.settings.has_llm:
            return self._offline_reply(agent, prompt)

        lock = self._locks[agent.name] if chat else threading.Lock()
        with lock:
            if chat:
                messages = self._chats.setdefault(agent.name, [])
                if len(messages) > CHAT_MAX_MESSAGES:
                    messages.clear()
            else:
                messages = []
            messages.append({"role": "user", "content": self._context_block() + prompt})
            self.bus.status(agent.name, "working")
            try:
                return self._loop(agent, messages, depth)
            except Exception as exc:  # noqa: BLE001
                self.bus.log(agent.name, f"Error: {exc}", "error")
                if chat:
                    messages.clear()  # a broken conversation can't be resumed safely
                return f"{agent.name} hit an error: {exc}"
            finally:
                self.bus.status(agent.name, "online")

    def _loop(self, agent: Agent, messages: list, depth: int) -> str:
        ctx = ToolContext(self.store, self.bus, self.settings, self, agent.name, depth)
        system = [{"type": "text", "text": self.system_prompt(agent), "cache_control": {"type": "ephemeral"}}]
        tools = self.tools_for(agent)
        for _ in range(MAX_STEPS):
            response = self.client.beta.messages.create(
                model=self.settings.model,
                max_tokens=16000,
                system=system,
                tools=tools,
                messages=messages,
                thinking={"type": "adaptive"},
                output_config={"effort": agent.effort},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "refusal":
                return "I can't help with that one."
            if response.stop_reason == "pause_turn":
                continue  # server-side tool (web search) paused; re-send to let it continue

            calls = [b for b in response.content if b.type == "tool_use"]
            if response.stop_reason != "tool_use" or not calls:
                return "".join(b.text for b in response.content if b.type == "text").strip()

            results = []
            for call in calls:
                self.bus.log(agent.name, _describe_call(call.name, call.input), "tool")
                output, is_error = execute(call.name, ctx, call.input)
                results.append({"type": "tool_result", "tool_use_id": call.id,
                                "content": output[:20000], "is_error": is_error})
            messages.append({"role": "user", "content": results})
        return "I've hit my step limit for this request; progress so far is saved."

    def reset_chat(self, agent_name: str | None = None) -> None:
        if agent_name:
            self._chats.pop(agent_name.upper(), None)
        else:
            self._chats.clear()

    # ------------------------------------------------------------ offline mode
    def _offline_reply(self, agent: Agent, prompt: str) -> str:
        open_tasks = self.store.list_tasks("open", limit=500)
        return (f"{agent.name} standing by, {self.settings.owner_name}. My reasoning core is offline - set "
                f"ANTHROPIC_API_KEY in .env and restart to bring the agents fully online. "
                f"Local systems are fine: {len(open_tasks)} open tasks tracked.")


def _describe_call(name: str, args: dict) -> str:
    if name == "delegate":
        return f"→ delegating to {str(args.get('agent', '')).upper()}: {str(args.get('task', ''))[:120]}"
    short = json.dumps(args, default=str)
    return f"{name} {short[:140]}"
