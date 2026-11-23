"""Team life: group calls with the whole team, Friday team dinner, surprise voice notes, agent diaries, gifts and
the evolving team photo. Everything the agents say here is one brain call written as a script, then spoken by
each agent in their own voice (on the dashboard, the phone call screen and Telegram)."""
from __future__ import annotations

import json
import random
import re
import textwrap
import threading
from datetime import datetime, timedelta
from pathlib import Path

from .config import ROOT, settings

GIFTS = ROOT / "data" / "gifts"
TEAM_RE = re.compile(r"^\s*(?:(?:hey|ok|yo|jarvis)[,\s]+)?(?:team|everyone|guys|squad)[,:]\s*(.+)$"
                     r"|^\s*(?:jarvis[,\s]+)?(?:group call|call the team|team call|conference call|get the team on)"
                     r"(?:\s+(?:about|on|re)\s+(.+))?\s*[.!?]*\s*$", re.I)
DINNER_RE = re.compile(r"^\s*(?:jarvis[,\s]+)?(?:team dinner|dinner with the team|dinner mode|family dinner)"
                       r"(?: mode| time)?\s*[.!?]*\s*$", re.I)

SCRIPT = ("You're writing a short GROUP CALL script for the owner's AI team (friends who work with them). "
          "Topic: {topic}\n\nPeople on the call: {who}.\n{bonds}\n"
          "Rules: 4 to {n} lines in total. Each agent speaks fully in character (personality, quirks, catchphrases, "
          "their mood today), reacts to each other (agree, tease, interrupt, back each other up), and talks TO the "
          "owner by the name they use. Use real facts if you checked them (status_snapshot is quick). Mood and sound "
          "tags like [excited] or [laughs] are welcome. Each line one or two short spoken sentences.\n"
          "Reply with ONLY a JSON array, no other text: "
          '[{{"agent": "FRIDAY", "line": "..."}}, ...]')
DINNER = ("It's Friday night TEAM DINNER: the work week is done. Casual, warm, funny banter around the table: what "
          "happened this week (check status_snapshot and list_tasks done), light roasts of each other and of the "
          "owner, a running gag or two, someone tells a story, and it ends with JARVIS raising a toast to the owner. "
          "No work talk beyond a joke.")
SURPRISE = ("Unprompted surprise voice note to the owner, as their friend. Nothing needs doing: you just thought of "
            "them. One or two sentences, natural and specific (something from memory, their week, or your own "
            "personality), with feeling. Don't ask them to do anything. Your final answer is the note itself.")
DIARY = ("Write each agent's private DIARY entry for this week, in their own voice and personality, as if nobody "
         "will read it: what they did with the owner, how they feel about them and the team, one small worry or "
         "hope, a funny moment. 3-4 sentences each. Agents: {who}.\n{bonds}\n"
         "Check status_snapshot and recall for real things that happened. Reply with ONLY a JSON object: "
         '{{"AGENT": "entry", ...}}')
GIFT = ("You're {agent}, giving the owner a small gift because you're close friends now (bond level {level}). "
        "Gift type: {kind}. {how}\nReply with ONLY JSON: {{\"title\": \"...\", \"message\": \"a short note from you\", "
        "\"items\": [\"...\"]}}")
GIFT_HOW = {
    "playlist": "Pick 8 real songs that fit you and what they're going through this week (recall, status_snapshot). "
                "items = 'Artist - Song'.",
    "wallpaper": "A quote or line for their phone/laptop wallpaper that fits their goals right now. items = [the line].",
    "card": "A heartfelt card: what you admire about them and one thing you're looking forward to together. "
            "items = 3 short memories or reasons.",
}


def _visible() -> list[str]:
    from .agents import AGENTS
    return [n for n, a in AGENTS.items() if not a.hidden]


def _json(text: str, kind=list):
    """Pull the JSON array/object out of a reply (brains sometimes wrap it in prose or code fences)."""
    pat = r"\[[\s\S]*\]" if kind is list else r"\{[\s\S]*\}"
    m = re.search(pat, text or "")
    if not m:
        return None
    try:
        out = json.loads(m.group(0))
        return out if isinstance(out, kind) else None
    except ValueError:
        return None


def _bond_lines(store, agents: list[str]) -> str:
    from . import bonds
    parts = []
    for a in agents:
        b = bonds.get(store, a)
        md, why = bonds.mood(store, a)
        parts.append(f"{a}: bond level {b['level']} ({b['title']}), calls the owner \"{bonds.nickname(store, a)}\", "
                     f"mood {md}{' (' + why + ')' if why else ''}")
    return "About each of them:\n" + "\n".join(parts)


def pick_team(store, topic: str, size: int = 4) -> list[str]:
    """JARVIS always, plus whoever's named, plus the closest friends, plus someone at random for spice."""
    from . import bonds
    names = _visible()
    named = [n for n in names if re.search(rf"\b{n}\b", topic, re.I)]
    close = sorted(names, key=lambda n: -bonds.get(store, n)["xp"])
    team = ["JARVIS"] + [n for n in named if n != "JARVIS"]
    for n in close + random.sample(names, len(names)):
        if len(team) >= size:
            break
        if n not in team:
            team.append(n)
    return team


def call(engine, topic: str, *, who: list[str] | None = None, prompt: str = "", size: int = 4,
         publish: bool = True) -> list[dict]:
    """A group call: returns [{agent, line}] and plays it on the dashboard (each agent in their own voice)."""
    store, bus = engine.store, engine.bus
    team = [a.upper() for a in who] if who else pick_team(store, topic, size)
    text = SCRIPT.format(topic=(prompt or topic).strip() or "a catch-up", who=", ".join(team),
                         bonds=_bond_lines(store, team), n=max(6, len(team) * 2))
    reply = engine.run("JARVIS", text, background=False)
    lines = [{"agent": str(x.get("agent", "")).upper(), "line": str(x.get("line", "")).strip()}
             for x in (_json(reply) or []) if isinstance(x, dict)]
    lines = [x for x in lines if x["agent"] in _visible() and x["line"]][:12]
    if not lines:
        lines = [{"agent": "JARVIS", "line": reply.strip() or "The team's line is a little crackly, Sir. Try again?"}]
    if publish:
        bus.publish({"type": "team", "topic": topic, "agents": team, "lines": lines})
        bus.log("JARVIS", f"Group call ({', '.join(team)}): {topic[:80]}", "job")
    from . import bonds
    for a in {x["agent"] for x in lines}:
        bonds.add_xp(store, bus, a, 3, "group call")
    return lines


def transcript(lines: list[dict]) -> str:
    return "\n".join(f"{x['agent'].title()}: {x['line']}" for x in lines)


def call_async(engine, topic: str, **kw) -> None:
    threading.Thread(target=call, args=(engine, topic), kwargs=kw, daemon=True).start()


def dinner(engine, publish: bool = True) -> list[dict]:
    team = pick_team(engine.store, "", 5)
    lines = call(engine, "Friday team dinner", who=team, prompt=DINNER, publish=False)
    if publish:
        engine.bus.publish({"type": "team", "topic": "Team dinner", "agents": team, "lines": lines, "dinner": True})
        engine.bus.log("JARVIS", "Team dinner is served 🍽", "job")
    return lines


# ---------------------------------------------------------------- surprise voice notes
def surprise_agent(store, now: datetime | None = None, roll: float | None = None) -> str | None:
    """At most two surprise notes a week, from an agent at bond level 4+, on a random day."""
    from . import bonds
    now = now or datetime.now(settings.tz)
    week = (now - timedelta(days=7)).isoformat()
    bonds._ensure(store)
    sent = store.query("SELECT COUNT(*) AS n FROM bond_moments WHERE text LIKE 'Surprise voice note%' AND day >= ?",
                       (week[:10],))
    if sent and sent[0]["n"] >= 2:
        return None
    if (random.random() if roll is None else roll) > 0.35:
        return None
    friends = [n for n in _visible() if bonds.get(store, n)["level"] >= 4]
    return random.choice(friends) if friends else None


# ---------------------------------------------------------------- diaries
def write_diaries(engine) -> int:
    from . import bonds
    store = engine.store
    bonds.room(store, "JARVIS")   # makes sure the diary tables exist
    agents = sorted(_visible(), key=lambda n: -bonds.get(store, n)["xp"])[:5]
    reply = engine.run("JARVIS", DIARY.format(who=", ".join(agents), bonds=_bond_lines(store, agents)), background=True)
    entries = _json(reply, dict) or {}
    day = datetime.now(settings.tz).date().isoformat()
    n = 0
    for agent, text in entries.items():
        agent = str(agent).upper()
        if agent in agents and str(text).strip():
            store.execute("INSERT INTO agent_diary (agent, day, text) VALUES (?, ?, ?)", (agent, day, str(text).strip()))
            n += 1
    if n:
        engine.bus.log("JARVIS", f"{n} agents wrote in their diaries this week (open an agent's room to peek)", "job")
    return n


# ---------------------------------------------------------------- gifts
def _font(size: int, bold: bool = False):
    from PIL import ImageFont
    for name in (("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf") if bold else
                 ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf")):
        for base in ("C:/Windows/Fonts/", "/usr/share/fonts/truetype/dejavu/", ""):
            try:
                return ImageFont.truetype(base + name, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _rgb(hex_colour: str) -> tuple[int, int, int]:
    h = (hex_colour or "#00e5ff").lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) if len(h) == 6 else (0, 229, 255)


def _neon_canvas(w: int, h: int, colour: tuple[int, int, int]):
    """Dark background with a soft neon glow and a faint HUD grid."""
    from PIL import Image, ImageDraw, ImageFilter
    img = Image.new("RGB", (w, h), (4, 8, 16))
    glow = Image.new("RGB", (w, h), (0, 0, 0))
    d = ImageDraw.Draw(glow)
    d.ellipse((w * 0.1, h * 0.15, w * 0.9, h * 0.85), fill=tuple(c // 3 for c in colour))
    img = Image.blend(img, glow.filter(ImageFilter.GaussianBlur(min(w, h) // 5)), 0.9)
    d = ImageDraw.Draw(img)
    step = max(24, w // 30)
    for x in range(0, w, step):
        d.line((x, 0, x, h), fill=(10, 22, 34))
    for y in range(0, h, step):
        d.line((0, y, w, y), fill=(10, 22, 34))
    return img


def _glow_text(img, xy, text, font, colour, anchor="mm"):
    from PIL import Image, ImageChops, ImageDraw, ImageFilter
    layer = Image.new("RGB", img.size, (0, 0, 0))
    ImageDraw.Draw(layer).text(xy, text, font=font, fill=colour, anchor=anchor)
    out = ImageChops.add(img, layer.filter(ImageFilter.GaussianBlur(6)))
    ImageDraw.Draw(out).text(xy, text, font=font, fill=(240, 250, 255), anchor=anchor)
    return out


def render_gift(agent: str, kind: str, title: str, message: str, items: list[str], colour: str) -> Path:
    """A phone-wallpaper-sized neon image for the gift (wallpaper, card or playlist cover)."""
    GIFTS.mkdir(parents=True, exist_ok=True)
    rgb = _rgb(colour)
    w, h = (1080, 2340) if kind == "wallpaper" else (1200, 1500)
    img = _neon_canvas(w, h, rgb)
    big = _font(78 if kind == "wallpaper" else 64, True)
    small = _font(36)
    if kind == "wallpaper":
        line = (items or [message])[0]
        y = h // 2 - 60 * len(textwrap.wrap(line, 20)) // 2
        for part in textwrap.wrap(line, 20):
            img = _glow_text(img, (w // 2, y), part, big, rgb)
            y += 100
        img = _glow_text(img, (w // 2, h - 260), f"— {agent.title()}", small, rgb)
    else:
        img = _glow_text(img, (w // 2, 160), title[:40], big, rgb)
        y = 300
        for i, it in enumerate(items[:10], 1):
            for part in textwrap.wrap((f"{i}. " if kind == "playlist" else "• ") + it, 44):
                img = _glow_text(img, (100, y), part, small, rgb, anchor="lm")
                y += 52
            y += 10
        y = max(y + 40, h - 420)
        for part in textwrap.wrap(message, 46)[:5]:
            img = _glow_text(img, (w // 2, y), part, small, rgb)
            y += 50
        img = _glow_text(img, (w // 2, h - 90), f"with love, {agent.title()} ♥", small, rgb)
    path = GIFTS / f"{agent.lower()}-{kind}-{datetime.now(settings.tz):%Y%m%d-%H%M%S}.png"
    img.save(path)
    return path


def give_gift(engine, agent: str | None = None, kind: str | None = None) -> dict | None:
    """A friend (bond level 5+) makes the owner something: a playlist, a wallpaper or a card."""
    from . import bonds
    from .agents import AGENTS
    store = engine.store
    friends = [n for n in _visible() if bonds.get(store, n)["level"] >= 5]
    agent = (agent or (random.choice(friends) if friends else "")).upper()
    if agent not in AGENTS or AGENTS[agent].hidden:
        return None
    kind = kind or random.choice(list(GIFT_HOW))
    level = bonds.get(store, agent)["level"]
    reply = engine.run(agent, GIFT.format(agent=agent, level=level, kind=kind, how=GIFT_HOW[kind]), background=True)
    data = _json(reply, dict) or {"title": f"A {kind} from {agent.title()}", "message": reply.strip()[:300], "items": []}
    items = [str(x) for x in data.get("items") or []][:10]
    title, message = str(data.get("title") or kind.title())[:60], str(data.get("message") or "")[:400]
    path = render_gift(agent, kind, title, message, items, AGENTS[agent].color)
    body = message + ("\n\n" + "\n".join(items) if items else "")
    if kind == "playlist":
        body += "\n\n" + "\n".join("https://www.youtube.com/results?search_query=" + re.sub(r"\s+", "+", it)
                                   for it in items)
    bonds.room(store, agent)
    gift_id = store.execute("INSERT INTO agent_gifts (agent, kind, title, body, file, day) VALUES (?, ?, ?, ?, ?, ?)",
                        (agent, kind, title, body, str(path), datetime.now(settings.tz).date().isoformat()))
    bonds.moment(store, agent, f"Gave you a gift: {title}")
    engine.bus.publish({"type": "gift", "agent": agent, "id": gift_id, "kind": kind, "title": title, "message": message})
    from . import telegram as tg
    if tg.ready():
        try:
            tg.send(f"🎁 {agent.title()} made you something: {title}\n{message}")
            tg.send_file(str(path), f"{title} — from {agent.title()}")
        except Exception:  # noqa: BLE001 - the gift is saved either way
            pass
    return {"id": gift_id, "agent": agent, "kind": kind, "title": title, "file": str(path)}


# ---------------------------------------------------------------- the team photo
def team_photo(store) -> Path:
    """A neon group portrait that changes as friendships grow: closer friends stand in front, bigger and brighter,
    with their hearts under them. Redrawn whenever it's asked for."""
    from PIL import ImageDraw
    from . import bonds
    from .agents import AGENTS
    GIFTS.mkdir(parents=True, exist_ok=True)
    w, h = 1600, 1000
    img = _neon_canvas(w, h, (0, 160, 220))
    people = sorted(_visible(), key=lambda n: -bonds.get(store, n)["xp"])
    front, back = people[:5], people[5:]
    rows = [(back, 330, 70), (front, 640, 105)]
    for row, cy, base in rows:
        if not row:
            continue
        gap = w / (len(row) + 1)
        for i, name in enumerate(row):
            b = bonds.get(store, name)
            r = int(base + b["level"] * 4)
            cx = int(gap * (i + 1))
            rgb = _rgb(AGENTS[name].color)
            bright = 0.45 + 0.055 * b["level"]
            ring = tuple(min(255, int(c * bright)) for c in rgb)
            d = ImageDraw.Draw(img)
            for k in range(8, 0, -1):   # glow halo
                d.ellipse((cx - r - k * 3, cy - r - k * 3, cx + r + k * 3, cy + r + k * 3),
                          outline=tuple(int(c * (0.12 + 0.02 * (8 - k))) for c in ring), width=3)
            d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(8, 14, 24), outline=ring, width=5)
            img = _glow_text(img, (cx, cy - 6), name[:2], _font(int(r * 0.7), True), ring)
            img = _glow_text(img, (cx, cy + r + 34), name.title(), _font(30, True), ring)
            img = _glow_text(img, (cx, cy + r + 70), "♥" * min(b["level"], 10), _font(22), (255, 80, 140))
    img = _glow_text(img, (w // 2, 90), "THE TEAM", _font(70, True), (0, 229, 255))
    img = _glow_text(img, (w // 2, 150), f"{(bonds.first_name() or settings.owner_name).title()}'s crew · {datetime.now(settings.tz):%d %b %Y}",
                     _font(28), (120, 220, 255))
    path = GIFTS / "team-photo.png"
    img.save(path)
    return path
