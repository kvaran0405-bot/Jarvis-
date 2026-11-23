"""Location chatter: when the owner has been somewhere for a few minutes, the agent who fits the area sends a short,
friendly message about it, like a friend who noticed ("Hi Sir, I see you're at City Hall! Lau Pa Sat is 8 minutes
away..."). Never at home, never while driving, never in quiet hours or focus; at most once per area a day, four a
day, and 90 minutes apart. Say "location chat off" to stop it."""
from __future__ import annotations

import json
import math
import random
import threading
from datetime import datetime, timedelta

from .config import settings

AREAS = {   # neighbourhood: (lat, lon)
    "City Hall": (1.2931, 103.8520), "Raffles Place": (1.2840, 103.8515), "Marina Bay": (1.2820, 103.8590),
    "Bugis": (1.3005, 103.8558), "Little India": (1.3066, 103.8492), "Chinatown": (1.2836, 103.8443),
    "Tanjong Pagar": (1.2765, 103.8455), "Orchard": (1.3040, 103.8318), "Somerset": (1.3007, 103.8390),
    "Dhoby Ghaut": (1.2990, 103.8455), "Clarke Quay": (1.2888, 103.8464), "Tiong Bahru": (1.2860, 103.8270),
    "HarbourFront": (1.2653, 103.8220), "Sentosa": (1.2494, 103.8303), "Holland Village": (1.3112, 103.7960),
    "Buona Vista": (1.3071, 103.7900), "Clementi": (1.3151, 103.7652), "Jurong East": (1.3331, 103.7422),
    "Boon Lay": (1.3386, 103.7058), "Bukit Batok": (1.3490, 103.7497), "Choa Chu Kang": (1.3854, 103.7443),
    "Woodlands": (1.4370, 103.7865), "Yishun": (1.4295, 103.8350), "Sembawang": (1.4491, 103.8201),
    "Ang Mo Kio": (1.3700, 103.8495), "Bishan": (1.3510, 103.8485), "Toa Payoh": (1.3327, 103.8471),
    "Novena": (1.3204, 103.8438), "Newton": (1.3138, 103.8380), "Serangoon": (1.3498, 103.8735),
    "Hougang": (1.3712, 103.8925), "Sengkang": (1.3917, 103.8950), "Punggol": (1.4053, 103.9024),
    "Paya Lebar": (1.3180, 103.8927), "Geylang": (1.3133, 103.8838), "Katong": (1.3050, 103.9050),
    "Bedok": (1.3240, 103.9300), "Tampines": (1.3532, 103.9452), "Pasir Ris": (1.3730, 103.9493),
    "Changi": (1.3644, 103.9915), "Kallang": (1.3115, 103.8714), "Bukit Timah": (1.3294, 103.8021),
    "Dempsey": (1.3053, 103.8105), "Kent Ridge": (1.2937, 103.7845), "Bukit Panjang": (1.3784, 103.7620),
}
AREA_KM = 1.1
DWELL_MIN = 5
PER_DAY = 4
GAP_MIN = 90
WHO = {"food": "FRIDAY", "nature": "STEVE", "heritage": "ATHENA", "views": "HERALD", "night": "HERALD"}
PROMPT = ("You're texting the owner a short, spontaneous message as their friend, because you noticed from their "
          "phone that they're around {area} right now ({time}). Mention ONE specific nearby thing worth doing: {tip}. "
          "Sound natural and in character (start like 'Hi Sir, I see you're at {area}!' or your own style), 1-2 short "
          "sentences, maybe one emoji. Don't ask them to reply. Your final answer is just the message.")


def _km(a, b) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def area_of(lat: float, lon: float) -> str | None:
    best = min(((n, _km((lat, lon), p)) for n, p in AREAS.items()), key=lambda x: x[1])
    return best[0] if best[1] <= AREA_KM else None


def enabled(store) -> bool:
    return (store.get("chatter:on") or "on") != "off"


def nearby_tip(store, lat: float, lon: float) -> tuple[str, str] | None:
    """(kind, tip text) for the best nearby side quest: undiscovered first, then favourites."""
    from . import explore, quests
    qs = [q for q in quests.status(explore.trail(store), (lat, lon)) if q["km"] <= 1.5]
    if not qs:
        return None
    hour = datetime.now(settings.tz).hour
    pref = [q for q in qs if q["kind"] == ("night" if hour >= 19 else "food" if 11 <= hour <= 14 or 17 <= hour <= 20
                                            else q["kind"])]
    q = sorted(pref or qs, key=lambda q: (q["done"], q["km"]))[0]
    walk = max(2, round(q["km"] * 13))
    return q["kind"], f"{q['name']} is about {walk} minutes' walk away ({q['why']})"


def should_chat(store, lat: float, lon: float, speed: float, now: datetime | None = None) -> str | None:
    """The area to chat about now, or None. Tracks how long the owner has been in the area."""
    from .phonelink import where
    from .speech import in_quiet_hours
    from .life import in_focus
    now = now or datetime.now(settings.tz)
    area = area_of(lat, lon)
    seen = json.loads(store.get("chatter:seen") or "{}")
    if not area or speed * 3.6 > 20:
        store.set("chatter:seen", "{}")
        return None
    if seen.get("area") != area:
        store.set("chatter:seen", json.dumps({"area": area, "since": now.isoformat()}))
        return None
    if now - datetime.fromisoformat(seen["since"]) < timedelta(minutes=DWELL_MIN):
        return None
    if not enabled(store) or (where(store, lat, lon, 0.3) or "").lower() == "home" or in_quiet_hours() or in_focus(store):
        return None
    log = json.loads(store.get("chatter:log") or "[]")
    today = now.date().isoformat()
    todays = [x for x in log if x["day"] == today]
    if len(todays) >= PER_DAY or any(x["area"] == area for x in todays):
        return None
    if log and now - datetime.fromisoformat(log[-1]["at"]) < timedelta(minutes=GAP_MIN):
        return None
    log = [x for x in log if x["day"] >= (now.date() - timedelta(days=3)).isoformat()]
    log.append({"area": area, "day": today, "at": now.isoformat()})
    store.set("chatter:log", json.dumps(log))
    return area


def compose(store, area: str, lat: float, lon: float, engine=None) -> tuple[str, str]:
    """(agent, message). An agent writes it when a brain is free; otherwise a friendly template."""
    tip = nearby_tip(store, lat, lon)
    kind, text = tip if tip else ("views", "have a look around, there's always something new")
    agent = WHO.get(kind, "JARVIS")
    if engine is not None:
        try:
            from . import brain
            if brain.pick(store, background=True):
                msg = engine.run(agent, PROMPT.format(area=area, tip=text,
                                                      time=datetime.now(settings.tz).strftime("%A %H:%M")),
                                 background=True).strip()
                if msg and "hit an error" not in msg and not msg.startswith(("⚠", "⏸")) and len(msg) < 400:
                    return agent, msg
        except Exception:  # noqa: BLE001 - fall back to the template
            pass
    openers = [f"Hi Sir, I see you're at {area}!", f"Ooh, {area}!", f"Spotted you around {area}, Sir."]
    return agent, f"{random.choice(openers)} {text[0].upper() + text[1:]}."


def deliver(store, bus, agent: str, msg: str) -> None:
    from . import bonds, phonelink
    from . import telegram as tg
    phonelink.queue(store, "notify", title=agent, text=msg, url="/map.html")
    if tg.ready():
        try:
            tg.send(f"{agent}: {msg}")
        except Exception:  # noqa: BLE001
            pass
    if bus is not None:
        bus.log(agent, "📍 " + msg, "reply")
    try:
        bonds.moment(store, agent, "Noticed you out and about: " + msg[:100])
    except Exception:  # noqa: BLE001
        pass


def on_location(store, bus, lat: float, lon: float, speed: float) -> None:
    """Called on every phone check-in with a location. Cheap; the message is written in the background."""
    area = should_chat(store, lat, lon, speed)
    if not area:
        return

    def go():
        try:
            from .server import engine
        except Exception:  # noqa: BLE001
            engine = None
        agent, msg = compose(store, area, lat, lon, engine)
        deliver(store, bus, agent, msg)
    threading.Thread(target=go, daemon=True).start()
