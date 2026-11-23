"""Drag-and-drop life: drop a file on the reactor (JARVIS) or on an agent's card and they read it and tell you
what matters. Images are looked at, documents are read. Nothing is sent anywhere; files are kept in data/drops."""
from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from .config import ROOT, settings

DROPS = ROOT / "data" / "drops"
IMAGES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif"}
DOCS = {".pdf", ".docx", ".pptx", ".txt", ".md", ".csv", ".json", ".py", ".js", ".html", ".log", ".ics", ".xml"}
MAX = 20_000_000
PROMPT = ("The owner just dragged a file called '{name}' onto you on the dashboard. Read it and, in your own voice, "
          "tell them in 2-4 spoken sentences what it is and what matters in it (dates, deadlines, money, people, "
          "action items). Then offer the obvious next step (add the deadline, make tasks, summarise for a client, "
          "quiz them...), and do it only if they say yes. {extra}\n\n--- {name} ---\n{content}")


def safe_name(name: str) -> str:
    base = re.sub(r"[^\w.\- ]+", "_", Path(name or "file").name).strip(" .") or "file"
    return base[-120:]


def save(name: str, data: bytes) -> Path:
    DROPS.mkdir(parents=True, exist_ok=True)
    path = DROPS / f"{datetime.now(settings.tz):%Y%m%d-%H%M%S}-{safe_name(name)}"
    path.write_bytes(data)
    return path


def handle(engine, name: str, data: bytes, agent: str = "JARVIS", note: str = "") -> dict:
    """Save the file and have the agent react to it. Returns {agent, reply, path}."""
    from .agents import AGENTS
    from .guard import blocked, is_secret
    agent = agent.upper() if agent.upper() in AGENTS and not AGENTS[agent.upper()].hidden else "JARVIS"
    if len(data) > MAX:
        return {"agent": agent, "reply": "That file's a bit heavy for me, Sir. Anything under 20 MB."}
    if blocked(name):
        return {"agent": agent, "reply": "That looks like banking, Sir, so I've left it alone."}
    path = save(name, data)
    ext = path.suffix.lower()
    extra = f"The owner added: {note}" if note else ""
    if ext in IMAGES:
        from . import vision
        try:
            seen = vision.ask(data, IMAGES[ext], vision.PROMPT)
        except Exception as exc:  # noqa: BLE001
            return {"agent": agent, "reply": f"I couldn't look at that: {exc}"[:300], "path": str(path)}
        if "private document" in seen.lower():
            return {"agent": agent, "reply": "That's a private document, Sir. I've not read it out.", "path": str(path)}
        content = "(an image; what it shows:)\n" + seen
    elif ext in DOCS:
        from .files_index import extract
        try:
            content = "\n\n".join((f"[{lbl}] " if lbl else "") + txt for lbl, txt in extract(path))
        except Exception as exc:  # noqa: BLE001
            return {"agent": agent, "reply": f"I couldn't open that file: {exc}"[:300], "path": str(path)}
        content = content.strip()[:14000] or "(the file is empty)"
    else:
        return {"agent": agent, "reply": f"I've kept {path.name} safe, Sir, but I can't read {ext or 'that'} files yet. "
                                         "PDFs, Word, PowerPoint, text and images work.", "path": str(path)}
    if blocked(content[:4000]) or is_secret(content[:4000]):
        return {"agent": agent, "reply": "There's private financial or password stuff in there, so I've left it "
                                         "unread, Sir.", "path": str(path)}
    reply = engine.run(agent, PROMPT.format(name=path.name.split("-", 2)[-1], extra=extra, content=content),
                       chat=True, voice=True)
    return {"agent": agent, "reply": reply, "path": str(path)}
