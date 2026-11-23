"""Side quests for the Explorer map: Singapore spots worth discovering, by kind. A quest completes by itself when the
phone's trail passes within ~250 m of it. Coordinates are approximate (to the building/park entrance)."""
from __future__ import annotations

import math

from .config import settings

KINDS = {   # kind: (label, colour, icon)
    "food": ("Food", "#ffb347", "🍜"),
    "nature": ("Nature", "#3dff9a", "🌿"),
    "heritage": ("Heritage", "#ff5c9a", "🏛"),
    "views": ("Views", "#5fd8ff", "🌇"),
    "night": ("Night", "#b06bff", "🌙"),
}

QUESTS = [   # (name, kind, lat, lon, why)
    ("Lau Pa Sat", "food", 1.2807, 103.8504, "Victorian hawker hall; satay street opens at night"),
    ("Maxwell Food Centre", "food", 1.2803, 103.8448, "Tian Tian chicken rice, the queue is part of it"),
    ("Tiong Bahru Market", "food", 1.2850, 103.8326, "Chwee kueh breakfast in an art-deco estate"),
    ("Old Airport Road Food Centre", "food", 1.3083, 103.8856, "Locals' favourite: char kway teow, rojak"),
    ("Newton Food Centre", "food", 1.3120, 103.8395, "Late-night BBQ stingray and oyster omelette"),
    ("Chomp Chomp", "food", 1.3644, 103.8664, "Serangoon Gardens supper spot"),
    ("Geylang Serai Market", "food", 1.3168, 103.8981, "Malay food, kueh and the Raya bazaar"),
    ("Jalan Besar coffee row", "food", 1.3065, 103.8580, "Old shophouses, new third-wave cafés"),
    ("MacRitchie TreeTop Walk", "nature", 1.3540, 103.8131, "Suspension bridge above the rainforest canopy"),
    ("Henderson Waves", "nature", 1.2756, 103.8155, "Highest pedestrian bridge, Southern Ridges"),
    ("Pulau Ubin", "nature", 1.4045, 103.9605, "Bumboat to the last kampong; cycle Chek Jawa"),
    ("Sungei Buloh Wetlands", "nature", 1.4467, 103.7300, "Mudskippers, monitor lizards, maybe a croc"),
    ("Bukit Timah summit", "nature", 1.3546, 103.7760, "Singapore's highest hill (163 m)"),
    ("Coney Island", "nature", 1.4092, 103.9218, "Wild beaches and casuarina trails"),
    ("East Coast Park", "nature", 1.3008, 103.9124, "Cycle, chill, seafood at sunset"),
    ("Punggol Waterway", "nature", 1.4086, 103.9047, "Lights, bridges and the Coney link"),
    ("Labrador Nature Park", "nature", 1.2672, 103.8023, "WWII bunkers on a sea cliff"),
    ("Lower Peirce boardwalk", "nature", 1.3693, 103.8253, "Quiet reservoir walk, long-tailed macaques"),
    ("Fort Canning", "heritage", 1.2945, 103.8459, "Ancient hill, Battlebox, the tree tunnel"),
    ("Sultan Mosque, Kampong Glam", "heritage", 1.3022, 103.8590, "Golden domes and Haji Lane murals"),
    ("Buddha Tooth Relic Temple", "heritage", 1.2814, 103.8443, "Chinatown's grand temple, rooftop garden"),
    ("Sri Veeramakaliamman Temple", "heritage", 1.3080, 103.8520, "Little India's colourful heart"),
    ("Haw Par Villa", "heritage", 1.2830, 103.7820, "Wonderfully weird statue park (Ten Courts of Hell)"),
    ("Koon Seng Road shophouses", "heritage", 1.3141, 103.9029, "Pastel Peranakan houses in Joo Chiat"),
    ("Thian Hock Keng", "heritage", 1.2808, 103.8476, "Oldest Hokkien temple, no nails used"),
    ("National Gallery", "heritage", 1.2903, 103.8515, "Two courts, one rooftop with a view"),
    ("Gardens by the Bay", "views", 1.2816, 103.8636, "Supertree light show at 7:45 and 8:45 pm"),
    ("Marina Barrage", "views", 1.2806, 103.8711, "Rooftop lawn picnics with the skyline"),
    ("Jewel Changi", "views", 1.3602, 103.9898, "The Rain Vortex, best at night"),
    ("Pinnacle@Duxton skybridge", "views", 1.2768, 103.8418, "50th-floor skybridge, small fee"),
    ("Mount Faber", "views", 1.2718, 103.8195, "Cable car and harbour views"),
    ("Helix Bridge", "views", 1.2875, 103.8607, "DNA bridge, perfect for the night skyline"),
    ("Jurong Lake Gardens", "views", 1.3388, 103.7280, "Rasau walk and the lakeside sunset"),
    ("Merlion Park", "views", 1.2868, 103.8545, "Classic, but you have to"),
    ("Clarke Quay", "night", 1.2906, 103.8465, "River bars and the reverse bungee"),
    ("Esplanade outdoor theatre", "night", 1.2898, 103.8558, "Free live music by the bay"),
    ("Holland Village", "night", 1.3112, 103.7960, "Chill bars and late food"),
    ("Dempsey Hill", "night", 1.3053, 103.8105, "Dinner in old army barracks under the trees"),
    ("Night Safari", "night", 1.4021, 103.7880, "The world's first night zoo"),
    ("Orchard Road", "night", 1.3048, 103.8318, "Lights, malls and the Christmas light-up"),
]

RADIUS_KM = 0.25


def _km(a, b) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def status(trail: list[list[float]], here: tuple[float, float] | None = None) -> list[dict]:
    """Every quest with done (your trail passed by) and how far it is from you now."""
    out = []
    for name, kind, lat, lon, why in QUESTS:
        done = any(abs(t[0] - lat) < 0.004 and abs(t[1] - lon) < 0.004 and _km((t[0], t[1]), (lat, lon)) <= RADIUS_KM
                   for t in trail)
        q = {"name": name, "kind": kind, "lat": lat, "lon": lon, "why": why, "done": done}
        if here:
            q["km"] = round(_km(here, (lat, lon)), 1)
        out.append(q)
    return out


def map_data(store) -> dict:
    """Everything the Explorer map draws."""
    from . import explore, phonelink
    tr = explore.trail(store)
    st = phonelink.state(store)
    here = (st["lat"], st["lon"]) if st.get("lat") is not None else None
    qs = status(tr, here)
    saved = phonelink.places(store)
    return {"trail": tr, "stats": explore.stats(store), "route": explore.current_route(store),
            "path": [[p[1], p[2]] for p in explore.path(store)], "here_at": st.get("loc_at") or st.get("at"),
            "here": list(here) if here else None, "quests": qs, "kinds": KINDS,
            "done": sum(q["done"] for q in qs), "total": len(qs),
            "places": [{"name": n, "lat": p[0], "lon": p[1]} for n, p in saved.items()],
            "owner": settings.owner_name}
