"""ORACLE's deal watcher: tells the owner when something they want drops in price.

- Steam: link your Steam profile once ("ORACLE, my Steam is steamcommunity.com/id/<name>"). Your Steam wishlist is
  checked twice a day in Singapore dollars; a game on 40%+ off (or under the price you set) gets a heads-up.
- Anything else ("tell me when AirPods Pro go under $250"): kept on the watch list; ORACLE checks the best price in
  Singapore every day with a web search and tells you when it's at or under your target.
Read-only: nothing is ever bought.
"""
from __future__ import annotations

import json
import re
import urllib.request
from datetime import datetime

from .config import settings

UA = {"User-Agent": "Mozilla/5.0 JARVIS personal assistant"}
STEAM_SALE = 40   # % off that's worth a heads-up


def _get(url: str, timeout: int = 20) -> bytes:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout) as r:
        return r.read()


def _ensure(store) -> None:
    store.execute("""CREATE TABLE IF NOT EXISTS deals (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, name TEXT,
        ref TEXT, target REAL DEFAULT 0, price REAL, discount INTEGER DEFAULT 0, url TEXT DEFAULT '', alerted TEXT DEFAULT '',
        checked TEXT, UNIQUE(kind, ref))""")


# ---------------------------------------------------------------- Steam
def steam_id(profile: str) -> str:
    """A SteamID64 from a profile link, a custom name, or the number itself."""
    p = profile.strip().rstrip("/")
    if m := re.search(r"(\d{17})", p):
        return m.group(1)
    name = p.rsplit("/", 1)[-1]
    xml = _get(f"https://steamcommunity.com/id/{name}/?xml=1").decode("utf-8", "ignore")
    if m := re.search(r"<steamID64>(\d{17})</steamID64>", xml):
        return m.group(1)
    raise ValueError("couldn't find that Steam profile (is it public?)")


def steam_wishlist(sid: str) -> list[int]:
    data = json.loads(_get(f"https://api.steampowered.com/IWishlistService/GetWishlist/v1/?steamid={sid}"))
    return [int(i["appid"]) for i in (data.get("response") or {}).get("items", [])]


def steam_prices(appids: list[int]) -> dict:
    """{appid: {name?, final (SGD), initial, discount}} for up to ~100 games at a time."""
    out = {}
    for i in range(0, len(appids), 50):
        chunk = ",".join(str(a) for a in appids[i:i + 50])
        data = json.loads(_get(f"https://store.steampowered.com/api/appdetails?appids={chunk}&cc=sg&filters=price_overview"))
        for k, v in data.items():
            po = (v or {}).get("data", {}).get("price_overview") if isinstance((v or {}).get("data"), dict) else None
            if po:
                out[int(k)] = {"final": po["final"] / 100, "initial": po["initial"] / 100, "discount": po.get("discount_percent", 0)}
    return out


def steam_name(appid: int) -> str:
    try:
        d = json.loads(_get(f"https://store.steampowered.com/api/appdetails?appids={appid}&cc=sg&filters=basic"))
        return d[str(appid)]["data"]["name"]
    except Exception:  # noqa: BLE001
        return f"Steam game {appid}"


def steam_sync(store) -> dict:
    """Refresh the Steam wishlist and prices; returns the games that just went on a good sale."""
    _ensure(store)
    sid = store.get("deals:steam_id")
    if not sid:
        return {"error": "no Steam profile linked yet"}
    ids = steam_wishlist(sid)
    have = {int(r["ref"]): r for r in store.query("SELECT * FROM deals WHERE kind = 'steam'")}
    for a in ids:
        if a not in have:
            store.execute("INSERT OR IGNORE INTO deals (kind, name, ref, url) VALUES ('steam', ?, ?, ?)",
                          (steam_name(a), str(a), f"https://store.steampowered.com/app/{a}"))
    prices, hits = steam_prices(ids), []
    for a, p in prices.items():
        row = store.query("SELECT * FROM deals WHERE kind = 'steam' AND ref = ?", (str(a),))[0]
        good = p["discount"] >= STEAM_SALE or (row["target"] and p["final"] <= row["target"])
        stamp = f"{datetime.now(settings.tz):%Y-%m}:{p['discount']}"
        store.execute("UPDATE deals SET price = ?, discount = ?, checked = ? WHERE id = ?",
                      (p["final"], p["discount"], datetime.now(settings.tz).isoformat(timespec="minutes"), row["id"]))
        if good and row["alerted"] != stamp:
            store.execute("UPDATE deals SET alerted = ? WHERE id = ?", (stamp, row["id"]))
            hits.append({"name": row["name"], "price": p["final"], "was": p["initial"], "discount": p["discount"], "url": row["url"]})
    return {"wishlist": len(ids), "deals": hits}


def check(store, bus) -> list[dict]:
    """Twice a day: Steam sales on the wishlist -> ORACLE tells the owner."""
    try:
        out = steam_sync(store)
    except Exception as exc:  # noqa: BLE001
        store.set("deals:last_error", str(exc)[:200])
        return []
    hits = out.get("deals") or []
    if hits:
        from .notify import notify_owner
        from .speech import announce
        lines = [f"🎮 {h['name']}: S${h['price']:.2f} ({h['discount']}% off, was S${h['was']:.2f})\n{h['url']}" for h in hits[:6]]
        notify_owner("🛒 ORACLE: Steam deals on your wishlist", "\n\n".join(lines), short=True)
        top = hits[0]
        announce(bus, "ORACLE", f"{top['name']} on your Steam wishlist is {top['discount']}% off, S${top['price']:.0f}."
                 + (f" And {len(hits) - 1} more." if len(hits) > 1 else ""))
    return hits


# ---------------------------------------------------------------- ORACLE's tools
from .tools import ToolContext, tool  # noqa: E402


@tool("steam_link", "Link the owner's Steam profile (link like steamcommunity.com/id/NAME or /profiles/NUMBER) so their "
      "wishlist is watched for sales. Their profile and wishlist must be public.", {"profile": {"type": "string"}}, ["profile"])
def steam_link(ctx: ToolContext, profile: str) -> dict:
    try:
        sid = steam_id(profile)
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
    ctx.store.set("deals:steam_id", sid)
    try:
        out = steam_sync(ctx.store)
    except Exception as exc:  # noqa: BLE001
        return {"linked": sid, "warning": f"couldn't read the wishlist yet: {exc}"}
    return {"linked": sid, **out}


@tool("deal_watch", "Watch the price of something the owner wants (any product, or a Steam game name) and tell them when "
      "it's at or under target_price (SGD). remove=true stops watching it.",
      {"name": {"type": "string"}, "target_price": {"type": "number"}, "remove": {"type": "boolean"}}, ["name"])
def deal_watch(ctx: ToolContext, name: str, target_price: float = 0, remove: bool = False) -> dict:
    _ensure(ctx.store)
    if remove:
        ctx.store.execute("DELETE FROM deals WHERE lower(name) = lower(?)", (name,))
        return {"removed": name}
    ctx.store.execute("INSERT OR REPLACE INTO deals (kind, name, ref, target) VALUES ('web', ?, ?, ?)", (name, name.lower(), target_price))
    return {"watching": name, "target": target_price}


@tool("deal_list", "The owner's watch list: Steam wishlist games (price, % off) and products with target prices.", {})
def deal_list(ctx: ToolContext) -> list:
    _ensure(ctx.store)
    return ctx.store.query("SELECT id, kind, name, target, price, discount, checked FROM deals ORDER BY kind, discount DESC LIMIT 80")


@tool("deal_update", "Record a price you found for a watched product (after searching the web), so the owner can be told "
      "when it hits their target.", {"name": {"type": "string"}, "price": {"type": "number"}, "url": {"type": "string"}}, ["name", "price"])
def deal_update(ctx: ToolContext, name: str, price: float, url: str = "") -> dict:
    _ensure(ctx.store)
    ctx.store.execute("UPDATE deals SET price = ?, url = ?, checked = ? WHERE kind = 'web' AND lower(name) = lower(?)",
                      (price, url, datetime.now(settings.tz).isoformat(timespec="minutes"), name))
    row = ctx.store.query("SELECT target FROM deals WHERE kind = 'web' AND lower(name) = lower(?)", (name,))
    hit = bool(row and row[0]["target"] and price <= row[0]["target"])
    return {"updated": name, "at_target": hit}
