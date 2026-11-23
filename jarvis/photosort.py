"""Photo sorter: every night the phone sends its new photos and screenshots to the laptop, and JARVIS files each one
into an album (Pictures/JARVIS Albums/<album>) with a one-line caption, so "find my Uniqlo receipt" works.
Photos of bank cards, IDs or passwords are thrown away, never filed."""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from .config import settings
from .tools import S, ToolContext, tool

def _inbox() -> Path:
    from . import config
    return config.ROOT / "data" / "phone_photos" / "inbox"

ALBUMS = ["Receipts", "Notes & Slides", "Event Setups", "Food", "People", "Places", "Memes", "Documents",
          "Screenshots", "Shopping", "Other"]
PROMPT = ("Sort this phone photo into exactly one album: " + ", ".join(ALBUMS) + ". 'Event Setups' = wedding or event "
          "decor, stages, tables, venues. 'Notes & Slides' = lecture slides, whiteboards, handwritten notes. "
          "'Screenshots' = app screens that fit nothing else. If it shows a bank card, ID, password or banking app, "
          "album is 'PRIVATE'. Reply ONLY with JSON: {\"album\": \"...\", \"caption\": \"one short line with any names, "
          "shops, places, dates or amounts you can read\"}")


def albums_dir() -> Path:
    import os
    pics = Path.home() / "Pictures"
    return Path(os.environ.get("JARVIS_ALBUMS", str(pics / "JARVIS Albums")))


def _ensure(store) -> None:
    store.execute("CREATE TABLE IF NOT EXISTS photo_index (id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT, album TEXT, "
                  "caption TEXT, taken TEXT, sorted TEXT)")


def request_new(store) -> int | None:
    """Ask the phone for photos added since the last sort (first time: the last 30 days)."""
    from . import phonelink
    since = int(store.get("photos:since") or (datetime.now().timestamp() - 30 * 86400))
    return phonelink.queue(store, "photos", since=since, limit=60)


def received(store, path: Path, taken: int | None) -> None:
    if taken:
        store.set("photos:since", str(max(int(store.get("photos:since") or 0), int(taken))))


def classify(path: Path) -> dict:
    from . import vision
    reply = vision.ask(path.read_bytes(), "image/jpeg", PROMPT)
    m = re.search(r"\{[\s\S]*\}", reply or "")
    try:
        out = json.loads(m.group(0)) if m else {}
    except ValueError:
        out = {}
    album = str(out.get("album", "")).strip()
    if album.upper() == "PRIVATE" or "private document" in (reply or "").lower():
        return {"album": "PRIVATE", "caption": ""}
    album = next((a for a in ALBUMS if a.lower() == album.lower()), "Other")
    return {"album": album, "caption": str(out.get("caption", ""))[:200]}


def sort_inbox(store, bus=None, limit: int = 30) -> dict:
    """File waiting photos into albums. Safe to call often; does nothing when the inbox is empty."""
    from . import brain
    _ensure(store)
    inbox = _inbox()
    files = sorted(inbox.glob("*.jpg"))[:limit] if inbox.exists() else []
    if not files or brain.get_mode(store)["mode"] == "paused":
        return {"sorted": 0}
    counts: dict[str, int] = {}
    for f in files:
        try:
            got = classify(f)
        except Exception as exc:  # noqa: BLE001 - no brain that can see right now: try again later
            if bus:
                bus.log("EDITH", f"Photo sorter paused: {exc}"[:200], "system")
            break
        if got["album"] == "PRIVATE":
            f.unlink(missing_ok=True)   # bank cards, IDs, passwords: never kept
            continue
        dest_dir = albums_dir() / got["album"]
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / f.name
        shutil.move(str(f), dest)
        store.execute("INSERT INTO photo_index (path, album, caption, taken, sorted) VALUES (?, ?, ?, ?, ?)",
                      (str(dest), got["album"], got["caption"], f.name[:15], datetime.now(settings.tz).isoformat()))
        counts[got["album"]] = counts.get(got["album"], 0) + 1
    n = sum(counts.values())
    if n and bus:
        bus.log("EDITH", "📸 Sorted " + ", ".join(f"{v} into {k}" for k, v in counts.items()), "job")
    return {"sorted": n, "albums": counts}


@tool("find_photo", "Find photos from the owner's phone by what's in them (e.g. 'Uniqlo receipt', 'Tan wedding stage', "
      "'lecture slides week 5'), or list an album. Albums: " + ", ".join(ALBUMS) + ".", {"query": S, "album": S})
def find_photo(ctx: ToolContext, query: str = "", album: str = "") -> dict:
    _ensure(ctx.store)
    words = [w for w in re.findall(r"\w+", query.lower()) if len(w) > 2]
    rows = ctx.store.query("SELECT path, album, caption, taken FROM photo_index" +
                           (" WHERE album = ?" if album else "") + " ORDER BY id DESC LIMIT 2000",
                           (album,) if album else ())
    if words:
        rows = [r for r in rows if all(w in (r["caption"] + " " + r["album"]).lower() for w in words)] or \
               [r for r in rows if any(w in (r["caption"] + " " + r["album"]).lower() for w in words)]
    return {"count": len(rows), "photos": rows[:15], "albums_folder": str(albums_dir())}


@tool("sort_photos_now", "Sort the phone's new photos and screenshots into albums now (normally runs every night).")
def sort_photos_now(ctx: ToolContext) -> dict:
    request_new(ctx.store)
    out = sort_inbox(ctx.store, ctx.bus)
    return {"asked_phone_for_new_photos": True, **out,
            "note": "New photos from the phone get sorted within the hour as they arrive."}
