"""Data for the Holo Lab (3D views) and the trophy system. All computed from JARVIS's own records; no AI."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from .config import settings

AREA_COLORS = {"academic": "#5b8cff", "career": "#e8b04b", "health": "#3dff9a", "finance": "#ff4f7b",
               "personal": "#5fd8ff"}

# ------------------------------------------------------------------ Singapore
SG_OUTLINE = [(103.615, 1.32), (103.64, 1.29), (103.68, 1.27), (103.72, 1.27), (103.75, 1.262), (103.80, 1.265),
              (103.83, 1.26), (103.86, 1.275), (103.88, 1.29), (103.92, 1.30), (103.96, 1.31), (103.99, 1.33),
              (104.02, 1.35), (104.03, 1.37), (104.0, 1.39), (103.96, 1.40), (103.92, 1.41), (103.88, 1.43),
              (103.83, 1.46), (103.80, 1.46), (103.76, 1.45), (103.72, 1.43), (103.69, 1.41), (103.66, 1.39),
              (103.64, 1.36), (103.62, 1.34)]
LANDMARKS = {   # name: (lat, lon, keywords)
    "Kaplan City Campus": (1.3005, 103.8497, ["kaplan", "wilkie"]),
    "Raffles Hotel": (1.2949, 103.8545, ["raffles hotel", "raffles"]),
    "Marina Bay Sands": (1.2834, 103.8607, ["marina bay sands", "mbs"]),
    "Botanic Gardens": (1.3138, 103.8159, ["botanic"]),
    "Changi Airport": (1.3644, 103.9915, ["changi", "airport"]),
    "Jewel": (1.3602, 103.9898, ["jewel"]),
    "Orchard": (1.3048, 103.8318, ["orchard", "ion", "ngee ann"]),
    "Tampines": (1.3496, 103.9568, ["tampines"]),
    "Jurong East": (1.3329, 103.7436, ["jurong"]),
    "Sentosa": (1.2494, 103.8303, ["sentosa"]),
    "Woodlands": (1.4382, 103.7890, ["woodlands"]),
    "Punggol": (1.4043, 103.9020, ["punggol"]),
    "Bugis": (1.3008, 103.8558, ["bugis"]),
    "Little India": (1.3066, 103.8518, ["little india", "serangoon road", "mustafa"]),
    "Chinatown": (1.2836, 103.8443, ["chinatown"]),
    "Gardens by the Bay": (1.2816, 103.8636, ["gardens by the bay"]),
    "NUS": (1.2966, 103.7764, ["nus", "kent ridge"]),
    "Bedok": (1.3236, 103.9273, ["bedok"]),
    "Yishun": (1.4304, 103.8354, ["yishun"]),
    "Ang Mo Kio": (1.3691, 103.8454, ["ang mo kio", "amk"]),
    "Toa Payoh": (1.3343, 103.8563, ["toa payoh"]),
    "Clarke Quay": (1.2906, 103.8465, ["clarke quay"]),
    "Fullerton": (1.2863, 103.8531, ["fullerton"]),
    "Kallang": (1.3020, 103.8714, ["kallang", "national stadium", "sports hub"]),
    "Paya Lebar": (1.3178, 103.8930, ["paya lebar", "plq"]),
    "Suntec": (1.2937, 103.8579, ["suntec"]),
}


def place_of(text: str) -> str | None:
    t = (text or "").lower()
    for name, (_lat, _lon, keys) in LANDMARKS.items():
        if any(k in t for k in keys):
            return name
    return None


# ------------------------------------------------------------------ muscles
MUSCLES = {"chest": ["bench", "push", "chest", "fly", "dip"], "back": ["row", "pull", "lat", "deadlift", "chin"],
           "legs": ["squat", "leg", "lunge", "calf", "deadlift", "rdl", "hip thrust"],
           "shoulders": ["overhead", "shoulder", "ohp", "lateral", "military", "arnold"],
           "arms": ["curl", "tricep", "bicep", "extension", "hammer", "skull"],
           "core": ["plank", "crunch", "abs", "core", "sit-up", "situp", "leg raise"]}


def muscle_load(store, today: date) -> dict:
    since = (today - timedelta(days=7)).isoformat()
    load = {m: 0 for m in MUSCLES}
    for w in store.query("SELECT exercise, sets FROM workouts WHERE day >= ?", (since,)):
        ex = (w["exercise"] or "").lower()
        for m, keys in MUSCLES.items():
            if any(k in ex for k in keys):
                load[m] += w["sets"] or 3
    return {m: min(1.0, v / 12) for m, v in load.items()}


# ------------------------------------------------------------------ trophies
def _count(store, sql: str, params: tuple = ()) -> int:
    return int(store.query(sql, params)[0]["n"] or 0)


def trophy_rules(store, today: date) -> list[dict]:
    from .life import workout_streak
    streak = workout_streak(store, today)
    first = store.query("SELECT MIN(created) AS d FROM activity")
    days_running = 0
    if first and first[0]["d"]:
        try:
            days_running = (today - datetime.fromisoformat(first[0]["d"]).date()).days
        except ValueError:
            pass
    booked = _count(store, "SELECT COUNT(*) AS n FROM gigs WHERE status IN ('confirmed','done')")
    R = [
        ("first_week", "First week", "JARVIS has been running for 7 days", "#5fd8ff", days_running, 7),
        ("tasks_10", "Getting things done", "10 tasks completed", "#3dff9a", _count(store, "SELECT COUNT(*) AS n FROM tasks WHERE status='done'"), 10),
        ("tasks_100", "Machine", "100 tasks completed", "#3dff9a", _count(store, "SELECT COUNT(*) AS n FROM tasks WHERE status='done'"), 100),
        ("first_quote", "First quote", "PEPPER sent out a quotation", "#e8b04b", _count(store, "SELECT COUNT(*) AS n FROM gigs WHERE quote_total > 0"), 1),
        ("first_booking", "First booking", "A client confirmed", "#ffcc3d", booked, 1),
        ("ten_events", "Ten events", "10 events booked", "#ffcc3d", booked, 10),
        ("paid_in_full", "Paid in full", "A client paid every dollar", "#ffcc3d",
         _count(store, "SELECT COUNT(*) AS n FROM gigs WHERE quote_total > 0 AND paid >= quote_total"), 1),
        ("crew_10", "The crew", "10 part-timers on the crew list", "#e8b04b", _count(store, "SELECT COUNT(*) AS n FROM crew"), 10),
        ("streak_7", "7-day streak", "Gym 7 days in a row", "#ff7a3d", streak, 7),
        ("streak_30", "30-day streak", "Gym 30 days in a row", "#ff7a3d", streak, 30),
        ("workouts_50", "Iron will", "50 workout days logged", "#ff7a3d", _count(store, "SELECT COUNT(DISTINCT day) AS n FROM workouts"), 50),
        ("lectures_5", "Scholar", "5 lectures turned into notes", "#5b8cff", _count(store, "SELECT COUNT(*) AS n FROM lectures WHERE status='ready'"), 5),
        ("exam_survivor", "Exam survivor", "Made it through an exam", "#5b8cff",
         _count(store, "SELECT COUNT(*) AS n FROM exams WHERE exam_at < ?", (today.isoformat(),)), 1),
        ("checkins_7", "Open book", "Told JARVIS how you felt on 7 days", "#2de0c0", _count(store, "SELECT COUNT(DISTINCT day) AS n FROM mood"), 7),
        ("grateful_30", "Grateful", "30 good moments saved", "#2de0c0", _count(store, "SELECT COUNT(*) AS n FROM gratitude"), 30),
        ("applied_5", "In the hunt", "5 job applications sent", "#ffb020",
         _count(store, "SELECT COUNT(*) AS n FROM applications WHERE status IN ('applied','interview','offer')"), 5),
        ("interview", "Interview landed", "Got an interview", "#ffb020", _count(store, "SELECT COUNT(*) AS n FROM applications WHERE status IN ('interview','offer')"), 1),
        ("offer", "Offer!", "Got a job offer", "#ffb020", _count(store, "SELECT COUNT(*) AS n FROM applications WHERE status='offer'"), 1),
        ("focus_10", "Deep work", "10 focus sessions", "#38d6ff", int(store.get("focus:count") or 0), 10),
    ]
    return [{"key": k, "title": t, "desc": d, "color": c, "progress": min(cur, target), "target": target}
            for k, t, d, c, cur, target in R]


def check_trophies(store, bus=None) -> list[dict]:
    """Unlock any trophy that's now earned. Returns the new ones (and celebrates them)."""
    store.execute("CREATE TABLE IF NOT EXISTS trophies (key TEXT PRIMARY KEY, unlocked TEXT NOT NULL)")
    have = {r["key"] for r in store.query("SELECT key FROM trophies")}
    today = datetime.now(settings.tz).date()
    new = []
    for t in trophy_rules(store, today):
        if t["key"] not in have and t["progress"] >= t["target"]:
            store.execute("INSERT INTO trophies (key, unlocked) VALUES (?,?)", (t["key"], datetime.now(settings.tz).isoformat()))
            new.append(t)
    for t in new:
        if bus is not None:
            from .life import celebrate
            celebrate(bus, "JARVIS", f"🏆 Trophy unlocked: {t['title']}")
        from . import telegram as tg
        if tg.ready():
            try:
                tg.send(f"🏆 Trophy unlocked: {t['title']} · {t['desc']}")
            except Exception:  # noqa: BLE001
                pass
    return new


def trophies(store) -> list[dict]:
    store.execute("CREATE TABLE IF NOT EXISTS trophies (key TEXT PRIMARY KEY, unlocked TEXT NOT NULL)")
    got = {r["key"]: r["unlocked"] for r in store.query("SELECT key, unlocked FROM trophies")}
    out = trophy_rules(store, datetime.now(settings.tz).date())
    for t in out:
        t["unlocked"] = got.get(t["key"])
    return out


# ------------------------------------------------------------------ diagnostics
def diagnostics(store, today: date) -> list[dict]:
    since7 = (today - timedelta(days=7)).isoformat()
    m = store.query("SELECT AVG(mood) AS mood, AVG(energy) AS energy, AVG(sleep) AS sleep FROM mood WHERE day >= ?", (since7,))[0]
    acad_open = _count(store, "SELECT COUNT(*) AS n FROM tasks WHERE area='academic' AND status IN ('todo','doing')")
    acad_late = _count(store, "SELECT COUNT(*) AS n FROM tasks WHERE area='academic' AND status IN ('todo','doing') AND due < ?",
                       (today.isoformat(),))
    acad_done = _count(store, "SELECT COUNT(*) AS n FROM tasks WHERE area='academic' AND status='done' AND updated >= ?", (since7,))
    gigs = store.list_gigs("active", 100)
    stale = sum(1 for g in gigs if not g["next_step"])
    gym_days = _count(store, "SELECT COUNT(DISTINCT day) AS n FROM workouts WHERE day >= ?", (since7,))
    overdue = _count(store, "SELECT COUNT(*) AS n FROM tasks WHERE status IN ('todo','doing') AND due < ?", (today.isoformat(),))

    def avg(v, default):
        return round(v / 5, 2) if v else default
    studies = 0.75 if not (acad_open or acad_done) else max(0.1, min(1, (acad_done + 1) / (acad_done + acad_late * 2 + 1)))
    business = 0.6 if not gigs else max(0.1, 1 - stale / len(gigs))
    return [
        {"key": "sleep", "label": "SLEEP", "value": avg(m["sleep"], 0.6), "color": "#5fd8ff"},
        {"key": "energy", "label": "ENERGY", "value": avg(m["energy"], 0.65), "color": "#3dff9a"},
        {"key": "mood", "label": "MOOD", "value": avg(m["mood"], 0.7), "color": "#ffcc3d"},
        {"key": "studies", "label": "STUDIES", "value": round(studies, 2), "color": "#5b8cff"},
        {"key": "business", "label": "BUSINESS", "value": round(business, 2), "color": "#e8b04b"},
        {"key": "fitness", "label": "FITNESS", "value": round(min(1, gym_days / 4), 2), "color": "#ff7a3d"},
        {"key": "control", "label": "ON TOP OF THINGS", "value": round(max(0.05, 1 - overdue / 10), 2), "color": "#b06bff"},
    ]


# ------------------------------------------------------------------ everything for the Holo Lab
def data(store) -> dict:
    now = datetime.now(settings.tz)
    today = now.date()
    week = []
    for e in store.list_events(today.isoformat(), (today + timedelta(days=7)).isoformat()):
        d = (date.fromisoformat(e["start"][:10]) - today).days
        start_h = int(e["start"][11:13]) + int(e["start"][14:16]) / 60 if len(e["start"]) > 10 else 0
        dur = 24.0 if len(e["start"]) <= 10 else 1.0
        if e.get("end") and len(e["end"]) > 10 and e["end"][:10] == e["start"][:10]:
            dur = max(0.25, int(e["end"][11:13]) + int(e["end"][14:16]) / 60 - start_h)
        week.append({"day": d, "start": start_h, "dur": dur, "title": e["title"],
                     "color": "#ff4d5e" if "exam" in e["title"].lower() else AREA_COLORS.get(e["area"], "#5fd8ff")})
    for t in store.list_tasks("open", limit=300):
        if t["due"] and today.isoformat() <= t["due"][:10] < (today + timedelta(days=7)).isoformat():
            d = (date.fromisoformat(t["due"][:10]) - today).days
            week.append({"day": d, "start": 23.0, "dur": 0.6, "title": "Due: " + t["title"], "color": "#ff4d5e"})
    gigs = []
    for g in store.list_gigs(None, 200):
        if g["status"] == "lost":
            continue
        days = (date.fromisoformat(g["event_date"][:10]) - today).days if g["event_date"] else None
        gigs.append({"client": g["client"], "type": g["event_type"], "value": float(g["quote_total"] or 0),
                     "status": g["status"], "days": days, "next": g["next_step"]})
    spend = store.spending_summary(today.replace(day=1).isoformat())["by_category"]
    places_today, explored = [], set()
    for e in store.list_events((today - timedelta(days=365)).isoformat(), (today + timedelta(days=1)).isoformat()):
        p = place_of(f"{e['title']} {e.get('location') or ''}")
        if p:
            (places_today if e["start"][:10] == today.isoformat() else []).append({"place": p, "title": e["title"],
                                                                                    "time": e["start"][11:16]})
            if e["start"][:10] < today.isoformat():
                explored.add(p)
    explored |= set(filter(None, (store.get("places:visited") or "").split("|")))
    return {
        "now": now.isoformat(timespec="minutes"), "week": week,
        "days": [(today + timedelta(days=i)).strftime("%a").upper() for i in range(7)],
        "gigs": gigs, "muscles": muscle_load(store, today),
        "spending": [{"category": r["category"], "amount": round(-r["total"], 2)} for r in spend if r["total"] < 0],
        "income": round(sum(r["total"] for r in spend if r["total"] > 0), 2),
        "outline": SG_OUTLINE, "landmarks": {k: [v[0], v[1]] for k, v in LANDMARKS.items()},
        "today_places": places_today, "explored": sorted(explored),
        "diagnostics": diagnostics(store, today), "trophies": trophies(store),
    }


def narrate(view: str, d: dict) -> str:
    """What JARVIS says when a hologram opens."""
    owner = settings.owner_name
    if view == "week":
        busy = max(range(7), key=lambda i: sum(e["dur"] for e in d["week"] if e["day"] == i)) if d["week"] else None
        n = len([e for e in d["week"] if not e["title"].startswith("Due:")])
        due = len([e for e in d["week"] if e["title"].startswith("Due:")])
        return (f"Your week, {owner}. {n} events and {due} deadlines. "
                + (f"{d['days'][busy].title()} is the heaviest." if busy is not None and n else "Wide open."))
    if view == "business":
        active = [g for g in d["gigs"] if g["status"] in ("enquiry", "quoted", "confirmed")]
        value = sum(g["value"] for g in active)
        return (f"Shaabaz, {owner}. {len(active)} active clients, ${value:,.0f} in play." if active
                else "The business galaxy is empty for now. PEPPER is ready when the enquiries come.")
    if view == "body":
        trained = [m for m, v in d["muscles"].items() if v > 0.15]
        return (f"This week you've trained {', '.join(trained)}." if trained
                else f"No workouts logged this week, {owner}. The suit needs maintenance.")
    if view == "money":
        total = sum(s["amount"] for s in d["spending"])
        top = max(d["spending"], key=lambda s: s["amount"])["category"] if d["spending"] else None
        return (f"${total:,.0f} spent this month, most of it on {top}." if top else "No spending logged this month.")
    if view == "singapore":
        if d["today_places"]:
            p = d["today_places"][0]
            return f"Today takes you to {p['place']}. {len(d['explored'])} places explored so far."
        return f"{len(d['explored'])} places explored so far, {owner}. Plenty of map left to light up."
    if view == "diagnostics":
        low = min(d["diagnostics"], key=lambda x: x["value"])
        high = max(d["diagnostics"], key=lambda x: x["value"])
        return (f"Diagnostics complete. {high['label'].title()} is strongest at {round(high['value'] * 100)} percent. "
                f"{low['label'].title()} is the weak point at {round(low['value'] * 100)} percent.")
    if view == "trophies":
        got = [t for t in d["trophies"] if t["unlocked"]]
        nearest = max((t for t in d["trophies"] if not t["unlocked"]), key=lambda t: t["progress"] / t["target"], default=None)
        return (f"{len(got)} of {len(d['trophies'])} trophies unlocked."
                + (f" Closest next: {nearest['title']}." if nearest else " Every one of them. Show-off."))
    return "Holo Lab online."
