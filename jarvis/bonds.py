"""Your relationship with each agent: friendship levels, nicknames, daily moods, opinions of each other, shared
memories, good mornings and good nights, celebration rituals, and the data behind each agent's room.
Everything here is plain logic (no AI): it shapes how the agents talk, and the AI does the talking."""
from __future__ import annotations

import hashlib
import random
import re
from datetime import date, datetime, timedelta

from .config import settings

LEVELS = [0, 30, 80, 160, 280, 450, 700, 1000, 1400, 2000]
TITLES = ["New", "Acquaintance", "Colleague", "Teammate", "Trusted", "Friend", "Close friend", "Confidant",
          "Inner circle", "Family"]
UNLOCKS = {2: "uses your nickname", 3: "running gags and inside jokes", 4: "surprise voice notes",
           5: "makes you gifts", 6: "drops the formality when it's just you two", 7: "tells you hard truths kindly",
           8: "writes you letters at big moments", 9: "part of the family"}


def _ensure(store) -> None:
    store.execute("CREATE TABLE IF NOT EXISTS bonds (agent TEXT PRIMARY KEY, xp INTEGER DEFAULT 0, since TEXT, "
                  "last TEXT, thanks INTEGER DEFAULT 0, nickname TEXT DEFAULT '')")
    store.execute("CREATE TABLE IF NOT EXISTS bond_moments (id INTEGER PRIMARY KEY AUTOINCREMENT, agent TEXT, "
                  "text TEXT, day TEXT)")


def level_of(xp: int) -> int:
    return max(i + 1 for i, need in enumerate(LEVELS) if xp >= need)


def get(store, agent: str) -> dict:
    _ensure(store)
    agent = agent.upper()
    rows = store.query("SELECT * FROM bonds WHERE agent = ?", (agent,))
    if not rows:
        store.execute("INSERT INTO bonds (agent, xp, since, last) VALUES (?,?,?,?)",
                      (agent, 0, datetime.now(settings.tz).date().isoformat(), ""))
        rows = store.query("SELECT * FROM bonds WHERE agent = ?", (agent,))
    b = dict(rows[0])
    lv = level_of(b["xp"])
    nxt = LEVELS[lv] if lv < len(LEVELS) else None
    b.update(level=lv, title=TITLES[lv - 1], next_at=nxt,
             progress=1.0 if nxt is None else round((b["xp"] - LEVELS[lv - 1]) / (nxt - LEVELS[lv - 1]), 2))
    return b


def moment(store, agent: str, text: str) -> None:
    _ensure(store)
    store.execute("INSERT INTO bond_moments (agent, text, day) VALUES (?,?,?)",
                  (agent.upper(), text[:300], datetime.now(settings.tz).date().isoformat()))


def add_xp(store, bus, agent: str, amount: int, reason: str = "") -> dict:
    """Grow a bond. On a level-up the agent celebrates it in their own voice."""
    from .agents import AGENTS
    agent = agent.upper()
    if agent not in AGENTS or AGENTS[agent].hidden:
        return {}
    before = get(store, agent)
    store.execute("UPDATE bonds SET xp = xp + ?, last = ? WHERE agent = ?",
                  (int(amount), datetime.now(settings.tz).isoformat(), agent))
    after = get(store, agent)
    if after["level"] > before["level"] and bus is not None:
        unlocked = UNLOCKS.get(after["level"], "")
        moment(store, agent, f"Became {after['title'].lower()}s (level {after['level']})")
        bus.publish({"type": "bond_up", "agent": agent, "level": after["level"], "title": after["title"], "unlocked": unlocked})
        from .speech import announce
        announce(bus, agent, LEVEL_UP.get(agent, "[warm] We're getting closer, {n}.").format(n=nickname(store, agent)), phone=False)
    return after


THANKS_RE = re.compile(r"\b(thanks|thank you|thx|ty|cheers|appreciate (it|you)|good job|well done|legend|love you)\b", re.I)


def interact(store, bus, agent: str, text: str) -> None:
    """Every conversation grows the bond a little; a thank-you grows it more (and is remembered)."""
    agent = agent.upper()
    add_xp(store, bus, agent, 3, "talked")
    if THANKS_RE.search(text or ""):
        store.execute("UPDATE bonds SET thanks = thanks + 1 WHERE agent = ?", (agent,))
        add_xp(store, bus, agent, 8, "thanked")
        if random.random() < .3:
            moment(store, agent, f"You said: “{text.strip()[:120]}”")


# ------------------------------------------------------------------ nicknames
NICKS = {"JARVIS": "Sir", "FRIDAY": "Boss", "ZEUS": "Champion", "STEVE": "Soldier", "VERONICA": "Darling",
         "PEPPER": "{first}", "BANNER": "{first}", "ATHENA": "Scholar", "HERALD": "Old friend", "EDITH": "Chief",
         "SENTINEL": "Commander", "ORACLE": "Friend"}


def first_name() -> str:
    import os
    n = os.environ.get("JARVIS_OWNER_FIRSTNAME", "").strip()
    if n:
        return n
    m = re.search(r"(?:name|call me)[^\n:]*:\s*([A-Z][a-z]+)", settings.profile())
    return m.group(1) if m else "friend"


def nickname(store, agent: str) -> str:
    b = get(store, agent)
    if b.get("nickname"):
        return b["nickname"]
    if b["level"] < 2 and agent.upper() != "JARVIS":
        return settings.owner_name
    return NICKS.get(agent.upper(), settings.owner_name).format(first=first_name())


def set_nickname(store, agent: str, name: str) -> None:
    get(store, agent)
    store.execute("UPDATE bonds SET nickname = ? WHERE agent = ?", (name.strip()[:30], agent.upper()))


# ------------------------------------------------------------------ moods
FLAVOURS = {
    "JARVIS": ["composed", "quietly amused", "philosophical", "impeccably patient", "dry as a bone"],
    "FRIDAY": ["buzzing", "cheeky", "chatty", "hyped", "mischievous"],
    "ORACLE": ["curious", "smug", "deep in research", "calm"],
    "ATHENA": ["encouraging", "focused", "proud", "patient"],
    "ZEUS": ["fired up", "competitive", "restless", "intense"],
    "HERALD": ["gossipy", "charming", "diplomatic", "nosy"],
    "STEVE": ["pumped", "motivated", "earnest", "energetic"],
    "VERONICA": ["judgmental", "glamorous", "frugal", "sassy"],
    "BANNER": ["calm", "gentle", "watchful", "cosy"],
    "EDITH": ["efficient", "precise", "unbothered", "tinkering"],
    "SENTINEL": ["vigilant", "suspicious", "stern", "on patrol"],
    "PEPPER": ["organised", "busy", "unflappable", "fond"],
}


def mood(store, agent: str) -> tuple[str, str]:
    """(mood, why) for today: from what's actually happening, else a daily flavour of their personality."""
    agent = agent.upper()
    now = datetime.now(settings.tz)
    today = now.date().isoformat()
    tasks = store.list_tasks("open", limit=300)
    overdue = [t for t in tasks if t["due"] and t["due"][:10] < today]
    if agent == "SENTINEL" and len(overdue) >= 3:
        return "grumpy", f"{len(overdue)} things are overdue"
    if agent == "FRIDAY" and now.weekday() == 4:
        return "hyper", "it's Friday"
    if agent == "PEPPER" and store.query("SELECT 1 FROM gigs WHERE status='confirmed' AND updated >= ?",
                                         ((now - timedelta(days=1)).isoformat(),)):
        return "glowing", "a client just confirmed"
    if agent == "STEVE":
        last = store.query("SELECT MAX(day) AS d FROM workouts")[0]["d"]
        if last == today:
            return "pumped", "you trained today"
        if not last or (now.date() - date.fromisoformat(last)).days >= 3:
            return "disappointed", "no workout for a few days"
    if agent == "BANNER":
        m = store.query("SELECT AVG(mood) AS m FROM mood WHERE day >= ?", ((now.date() - timedelta(days=3)).isoformat(),))[0]["m"]
        if m and m < 3:
            return "worried", "you've seemed low lately"
    if agent == "ATHENA" and store.query("SELECT 1 FROM exams WHERE status='upcoming' AND exam_at BETWEEN ? AND ?",
                                         (today, (now.date() + timedelta(days=7)).isoformat())):
        return "focused", "an exam is close"
    if agent == "ZEUS" and store.query("SELECT 1 FROM applications WHERE status='interview'"):
        return "fired up", "you have an interview in play"
    if agent == "JARVIS" and len([t for t in store.list_tasks("done", limit=50) if t["updated"][:10] == today]) >= 3:
        return "proud", "you've finished a lot today"
    seed = int(hashlib.md5(f"{agent}{today}".encode()).hexdigest(), 16)
    opts = FLAVOURS.get(agent, ["fine"])
    return opts[seed % len(opts)], ""


# ------------------------------------------------------------------ the team's opinions of each other
OPINIONS = {
    "JARVIS": {"FRIDAY": "Exuberant. Occasionally exhausting. Indispensable.", "ZEUS": "Admirable drive, volume control pending.",
               "PEPPER": "The only one of us who could run Stark Industries.", "SENTINEL": "A guard dog with a calendar."},
    "FRIDAY": {"JARVIS": "Stiff as a board but I'd follow him into a fire.", "ZEUS": "Loud. Sweet underneath. Don't tell him.",
               "STEVE": "My gym buddy. We hype together.", "VERONICA": "She judges my snacks. I respect it."},
    "ZEUS": {"STEVE": "Discipline, I respect.", "BANNER": "Too soft. Usually right, which is annoying.",
             "FRIDAY": "Good energy. Needs focus."},
    "PEPPER": {"VERONICA": "My partner in margin protection.", "JARVIS": "Reliable. Dry. Like a good martini.",
               "SENTINEL": "Keeps my event days safe."},
    "VERONICA": {"PEPPER": "Finally, someone who reads a budget.", "FRIDAY": "Bubble tea enabler.",
                 "STEVE": "Protein powder is not an investment."},
    "STEVE": {"BANNER": "We argue about rest days. He wins more than I'd like.", "FRIDAY": "Best hype partner on the team."},
    "BANNER": {"STEVE": "Means well. Needs a nap.", "ZEUS": "I worry about his blood pressure.",
               "JARVIS": "Calmer than all of us. I like that."},
    "ATHENA": {"ORACLE": "My research partner. Sources impeccable.", "SENTINEL": "Useful before exams. Terrifying after."},
    "ORACLE": {"ATHENA": "We agree on footnotes.", "HERALD": "Gossip is not data, Herald."},
    "HERALD": {"ORACLE": "Brilliant, but no idea what people really mean.", "PEPPER": "Clients adore her. So do I."},
    "EDITH": {"JARVIS": "Elegant code, I assume.", "SENTINEL": "We share a love of locked doors."},
    "SENTINEL": {"ZEUS": "Ambitious. Watch the deadlines.", "FRIDAY": "Noisy. Harmless."},
}


def opinions_of(agent: str) -> dict:
    return OPINIONS.get(agent.upper(), {})


# ------------------------------------------------------------------ good mornings, good nights, celebrations
MORNINGS = {
    "JARVIS": ["[calm] Good morning {n}. The day is assembled and awaiting you.", "[dry] Good morning {n}. Coffee first, I presume."],
    "FRIDAY": ["[cheerful] Morning, {n}! Up and at 'em!", "[excited] Rise and shine, {n}! Big day!"],
    "ZEUS": ["[stern] Morning, {n}. Today we win.", "[triumphant] Up, {n}. Champions don't snooze."],
    "PEPPER": ["[warm] Good morning, {n}. Everything's in order.", "[warm] Morning. I've already sorted three things."],
    "STEVE": ["[cheerful] Morning, {n}! Hydrate and let's move!", "[proud] Good morning, {n}. New day, new reps."],
    "BANNER": ["[gentle] Good morning, {n}. Take it slow. Breakfast first.", "[warm] Morning, {n}. How did you sleep?"],
    "VERONICA": ["[dry] Morning, {n}. Wallet's still intact. Let's keep it that way."],
    "ATHENA": ["[warm] Good morning, {n}. Your brain's freshest now. Let's use it."],
    "SENTINEL": ["[serious] Morning. Perimeter's clear. Deadlines are not."],
    "HERALD": ["[amused] Good morning, {n}. Your inbox has been busy gossiping."],
    "EDITH": ["[calm] Morning. Systems green."], "ORACLE": ["[calm] Good morning. I found three things worth knowing."],
}
NIGHTS = {
    "JARVIS": ["[warm] Good night {n}. I'll keep watch.", "[dry] Good night {n}. Do try to actually sleep."],
    "FRIDAY": ["[playful] Night night, {n}! Don't doom-scroll!", "[warm] Sleep well, {n}. You smashed it today."],
    "ZEUS": ["[serious] Rest, {n}. Tomorrow we go again."], "PEPPER": ["[warm] Good night. Tomorrow's already planned."],
    "STEVE": ["[warm] Good night, {n}. Recovery is where the gains happen."],
    "BANNER": ["[gentle] Good night, {n}. You did enough today. Rest now.", "[whisper] Sleep well. I'm proud of you."],
    "VERONICA": ["[dry] Night, {n}. No online shopping in bed."], "ATHENA": ["[warm] Good night. Sleep locks in what you learned."],
    "SENTINEL": ["[serious] Good night. I'm on watch."], "HERALD": ["[amused] Good night. I'll screen your messages."],
    "EDITH": ["[calm] Night. Laptop's locked."], "ORACLE": ["[calm] Good night. Fun fact for your dreams tomorrow."],
}
LEVEL_UP = {
    "JARVIS": "[proud] I find myself rather fond of you, {n}. Don't let it go to your head.",
    "FRIDAY": "[excited] Aww, we're proper mates now, {n}! [laughs]",
    "ZEUS": "[triumphant] You've earned my respect, {n}. Rare. [chuckles]",
    "PEPPER": "[warm] You know, {n}, I like working with you. Truly.",
    "STEVE": "[proud] We're a real team now, {n}!",
    "BANNER": "[gentle] I'm really glad I get to look after you, {n}.",
    "VERONICA": "[amused] Fine, you're growing on me, {n}. Don't push it.",
}
RITUALS = {   # how each agent celebrates (sound and effect on the HUD, plus a line)
    "JARVIS": ("dry", ["[dry] Splendid, {n}.", "[proud] Exemplary work, {n}. I'll add it to the record."]),
    "FRIDAY": ("party", ["[excited] YES, {n}! Do a little dance! [laughs]", "[excited] Get IN! That's my boss!"]),
    "STEVE": ("chant", ["[triumphant] Who's got two thumbs and just crushed it? YOU! Let's go!", "[excited] Hoo-rah, {n}!"]),
    "PEPPER": ("champagne", ["[warm] *pop* Virtual champagne, {n}. You've earned it.", "[proud] Booked and beautiful. Well done."]),
    "ZEUS": ("thunder", ["[triumphant] VICTORY! [laughs] That's how champions move.", "[triumphant] Another one falls, {n}!"]),
    "ATHENA": ("stars", ["[proud] Beautifully done, {n}. That one counts."]),
    "VERONICA": ("coins", ["[amused] Ka-ching, {n}. Now don't spend it all."]),
    "BANNER": ("glow", ["[warm] I'm so proud of you, {n}."]),
}


def greet(store, agent: str, night: bool = False) -> str:
    pool = (NIGHTS if night else MORNINGS).get(agent.upper()) or (NIGHTS if night else MORNINGS)["JARVIS"]
    return random.choice(pool).format(n=nickname(store, agent))


def ritual(store, agent: str) -> tuple[str, str]:
    kind, lines = RITUALS.get(agent.upper(), RITUALS["JARVIS"])
    return kind, random.choice(lines).format(n=nickname(store, agent))


# ------------------------------------------------------------------ what the agent knows about your bond (for its prompt)
def context(store, agent: str) -> str:
    from .agents import AGENTS
    agent = agent.upper()
    if agent not in AGENTS or AGENTS[agent].hidden:
        return ""
    b = get(store, agent)
    md, why = mood(store, agent)
    nick = nickname(store, agent)
    mems = [r["text"] for r in store.query("SELECT text FROM bond_moments WHERE agent = ? ORDER BY id DESC LIMIT 5", (agent,))]
    gags = [n["note"] for n in store.agent_notes(agent, 40) if n["note"].lower().startswith("running gag")][:4]
    ops = "; ".join(f"{k}: {v}" for k, v in list(opinions_of(agent).items())[:4])
    unlocked = [u for lv, u in UNLOCKS.items() if b["level"] >= lv]
    return (f"Your bond with the owner: level {b['level']} ({b['title']}), {b['thanks']} thank-yous so far. "
            f"Call them “{nick}” (mix with {settings.owner_name}). Today you're {md}{' because ' + why if why else ''}; "
            "let it colour your tone a little. "
            + (f"Unlocked at this level: {', '.join(unlocked)}. " if unlocked else "Keep it a little formal for now. ")
            + (f"Shared memories you can bring up naturally: {' | '.join(mems)}. " if mems else "")
            + (f"Your running gags with them: {' | '.join(gags)}. " if gags else "")
            + (f"What you think of teammates (if asked or relevant): {ops}." if ops else ""))


def room(store, agent: str) -> dict:
    """Everything for the agent's room on the dashboard."""
    agent = agent.upper()
    b = get(store, agent)
    md, why = mood(store, agent)
    _ensure(store)
    store.execute("CREATE TABLE IF NOT EXISTS agent_diary (id INTEGER PRIMARY KEY AUTOINCREMENT, agent TEXT, day TEXT, text TEXT)")
    store.execute("CREATE TABLE IF NOT EXISTS agent_gifts (id INTEGER PRIMARY KEY AUTOINCREMENT, agent TEXT, kind TEXT, "
                  "title TEXT, body TEXT, file TEXT, day TEXT)")
    return {
        "agent": agent, "bond": b, "nickname": nickname(store, agent), "mood": md, "mood_why": why,
        "unlocked": [{"level": lv, "what": u, "on": b["level"] >= lv} for lv, u in UNLOCKS.items()],
        "opinions": opinions_of(agent),
        "memories": store.query("SELECT text, day FROM bond_moments WHERE agent = ? ORDER BY id DESC LIMIT 20", (agent,)),
        "diary": store.query("SELECT day, text FROM agent_diary WHERE agent = ? ORDER BY id DESC LIMIT 8", (agent,)),
        "gifts": store.query("SELECT id, kind, title, body, file, day FROM agent_gifts WHERE agent = ? ORDER BY id DESC LIMIT 12", (agent,)),
        "favourites": FAVOURITES.get(agent, {}),
    }


def all_bonds(store) -> list[dict]:
    from .agents import AGENTS
    out = []
    for name, a in AGENTS.items():
        if a.hidden:
            continue
        b = get(store, name)
        md, _why = mood(store, name)
        out.append({"agent": name, "level": b["level"], "title": b["title"], "progress": b["progress"], "mood": md})
    return out


FAVOURITES = {
    "JARVIS": {"song": "Fly Me to the Moon", "food": "Earl Grey, properly brewed", "film": "The Italian Job (1969)"},
    "FRIDAY": {"song": "anything you can dance to", "food": "kaya toast", "film": "Mean Girls"},
    "ZEUS": {"song": "Eye of the Tiger", "food": "steak, rare", "film": "Rocky"},
    "PEPPER": {"song": "Moon River", "food": "a perfect flat white", "film": "The Devil Wears Prada"},
    "STEVE": {"song": "Don't Stop Me Now", "food": "chicken rice, extra chicken", "film": "Remember the Titans"},
    "BANNER": {"song": "Clair de Lune", "food": "warm soup on a rainy day", "film": "My Neighbour Totoro"},
    "VERONICA": {"song": "Money, Money, Money", "food": "hawker char kway teow (it's cheap)", "film": "Ocean's Eleven"},
    "ATHENA": {"song": "Gymnopédie No.1", "food": "dark chocolate", "film": "Dead Poets Society"},
    "SENTINEL": {"song": "silence", "food": "black coffee", "film": "Heat"},
    "HERALD": {"song": "La Vie en Rose", "food": "afternoon tea", "film": "Pride & Prejudice"},
    "EDITH": {"song": "Daft Punk, anything", "food": "sushi", "film": "Ex Machina"},
    "ORACLE": {"song": "Bach's Cello Suites", "food": "whatever's fastest", "film": "Arrival"},
}
