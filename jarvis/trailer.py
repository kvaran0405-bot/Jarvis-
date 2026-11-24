"""The JARVIS trailer, starring the owner (#8-#12).

`data()` is what the trailer shows: only things that are fine to show friends (counts, the team, places explored, a
city map), never messages, task titles, contacts or money. `save_video()` keeps an exported trailer and sends it
to the owner's phone (Telegram) as an MP4 when the laptop can convert it, else as the original WebM.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

from .config import ROOT, settings

PRIVATE_PLACES = {"home", "my home", "house", "hq"}


def data(store) -> dict:
    from .agents import AGENTS
    from . import holo
    now = datetime.now(settings.tz)
    today = now.date()
    h = {}
    try:
        h = holo.data(store)
    except Exception:  # noqa: BLE001
        pass
    week_steps = sum(int(store.get(f"steps:{(today - timedelta(days=i)).isoformat()}") or 0) for i in range(7))
    done_week = store.query("SELECT COUNT(*) AS n FROM tasks WHERE status = 'done' AND updated >= ?",
                            ((now - timedelta(days=7)).isoformat(),))[0]["n"]
    events_week = len([e for e in h.get("week", []) if not e["title"].startswith("Due:")])
    try:
        saved = json.loads(store.get("places:saved") or "{}")
    except ValueError:
        saved = {}
    places = [{"name": "HQ" if k.lower() in PRIVATE_PLACES else k.upper(), "lat": v[0], "lon": v[1]} for k, v in saved.items()][:12]
    explored = [p.upper() for p in h.get("explored", [])][:12]
    return {
        "owner": settings.owner_name if settings.owner_name and settings.owner_name != "Sir" else "SIR",
        "team": [{"name": a.name, "title": a.title, "color": a.color} for a in AGENTS.values() if not a.hidden],
        "stats": {"steps_week": week_steps, "tasks_done_week": done_week, "events_week": events_week,
                  "memories": len(store.memories(500)), "places_explored": len(h.get("explored", [])),
                  "trophies": len([t for t in h.get("trophies", []) if t.get("unlocked")])},
        "outline": h.get("outline", []), "landmarks": h.get("landmarks", {}), "places": places, "explored": explored,
        "trail": (h.get("trail") or [])[-600:],
    }


def save_video(raw: bytes, ext: str = "webm") -> dict:
    """Keep the exported trailer (data/trailers), convert to MP4 if possible, and send it to the owner's phone."""
    folder = ROOT / "data" / "trailers"
    folder.mkdir(parents=True, exist_ok=True)
    src = folder / f"jarvis-trailer-{datetime.now(settings.tz):%Y%m%d-%H%M%S}.{ext}"
    src.write_bytes(raw)
    out = _to_mp4(src) or src
    sent = False
    try:
        from . import telegram
        if telegram.enabled():
            kind = "sendVideo" if out.suffix == ".mp4" else "sendDocument"
            telegram.api_file(kind, "video" if kind == "sendVideo" else "document", str(out), chat_id=telegram.chat_id(),
                              caption="🎬 Your JARVIS trailer, Sir. Ready to post.")
            sent = True
    except Exception:  # noqa: BLE001 - it's saved either way
        pass
    return {"path": str(out), "mp4": out.suffix == ".mp4", "sent": sent}


def _to_mp4(src: Path) -> Path | None:
    """WebM (what browsers record) -> MP4 (what Instagram and WhatsApp want), using the audio library JARVIS has."""
    try:
        import av
    except ImportError:
        return None
    dst = src.with_suffix(".mp4")
    try:
        with av.open(str(src)) as inp, av.open(str(dst), "w") as out:
            vin = next((s for s in inp.streams if s.type == "video"), None)
            ain = next((s for s in inp.streams if s.type == "audio"), None)
            if vin is None:
                return None
            vcodec = next((c for c in ("libx264", "h264", "libopenh264", "mpeg4") if _has_codec(av, c)), None)
            if vcodec is None:
                return None
            vout = out.add_stream(vcodec, rate=30)
            vout.width, vout.height, vout.pix_fmt = vin.codec_context.width // 2 * 2, vin.codec_context.height // 2 * 2, "yuv420p"
            aout = out.add_stream("aac", rate=48000) if ain is not None and _has_codec(av, "aac") else None
            for packet in inp.demux(*(s for s in (vin, ain) if s is not None)):
                for frame in packet.decode():
                    if packet.stream.type == "video":
                        frame.pts = None
                        for p in vout.encode(frame.reformat(width=vout.width, height=vout.height, format="yuv420p")):
                            out.mux(p)
                    elif aout is not None:
                        frame.pts = None
                        for p in aout.encode(frame):
                            out.mux(p)
            for s in (vout, aout):
                if s is not None:
                    for p in s.encode(None):
                        out.mux(p)
        return dst if dst.stat().st_size > 10_000 else None
    except Exception:  # noqa: BLE001 - keep the WebM
        dst.unlink(missing_ok=True)
        return None


def _has_codec(av, name: str) -> bool:
    try:
        av.codec.Codec(name, "w")
        return True
    except Exception:  # noqa: BLE001
        return False
