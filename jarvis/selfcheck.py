"""Nightly self-check: JARVIS tests himself, fixes what he safely can, and tells you only what needs you.

Runs every night at 03:40 (and on "Jarvis, system check"). Each check is ok, fixed or needs you. If anything
needs you, a short Telegram message arrives; otherwise it stays quiet and the result shows in the morning.
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path

from .config import ROOT, settings


def _ago(iso: str, now: datetime) -> float:
    try:
        return (now - datetime.fromisoformat(iso)).total_seconds() / 3600
    except (TypeError, ValueError):
        return 1e9


def run(store, bus=None, live: bool = True) -> dict:
    """[{name, status: ok|fixed|needs_you, detail}], summary text. `live` = also test online services."""
    now = datetime.now(settings.tz)
    out: list[dict] = []

    def add(name, status, detail=""):
        out.append({"name": name, "status": status, "detail": detail})

    # memory (database)
    try:
        store.set("selfcheck:probe", now.isoformat())
        assert store.get("selfcheck:probe") == now.isoformat()
        add("Memory", "ok")
    except Exception as exc:  # noqa: BLE001
        add("Memory", "needs_you", f"the database can't be written ({exc})")

    # disk space: clear JARVIS's own voice cache if it's getting full
    free = shutil.disk_usage(ROOT).free / 1e9
    if free < 2:
        freed = 0
        for d in (ROOT / "data" / "tts", ROOT / "data" / "voice_cache"):
            if d.is_dir():
                for f in d.glob("*"):
                    try:
                        freed += f.stat().st_size
                        f.unlink()
                    except OSError:
                        pass
        free2 = shutil.disk_usage(ROOT).free / 1e9
        add("Disk space", "fixed" if free2 >= 2 else "needs_you",
            f"cleared {freed / 1e6:.0f} MB of old voice clips, {free2:.1f} GB free" if free2 >= 2 else f"only {free2:.1f} GB free on the laptop")
    else:
        add("Disk space", "ok", f"{free:.0f} GB free")

    # phone link
    try:
        st = json.loads(store.get("phone:state") or "{}")
    except ValueError:
        st = {}
    hours = _ago(st.get("at", ""), now)
    if not st:
        add("Phone link", "needs_you", "the phone app has never checked in (open it once while the laptop's on)")
    elif hours > 12:
        add("Phone link", "needs_you", f"no check-in for {hours:.0f} h: is Tailscale on, and is JARVIS allowed to run in the background?")
    else:
        add("Phone link", "ok", f"last check-in {hours * 60:.0f} min ago" if hours < 1 else f"last check-in {hours:.0f} h ago")

    # the phone's offline copy (solo mode)
    sh = _ago(store.get("solo:last_pack") or "", now)
    if sh > 48:
        add("Phone's offline brain", "needs_you" if st else "ok",
            "the phone hasn't copied what it needs to work alone for 2+ days (open the app once while the laptop's on)" if st else "not set up yet")
    else:
        add("Phone's offline brain", "ok", f"refreshed {sh:.0f} h ago")

    # stuck reminders / messages to you
    failed = store.query("SELECT COUNT(*) AS n FROM outbox WHERE status = 'failed' AND created > ?",
                         ((now - timedelta(days=2)).isoformat(),))[0]["n"]
    add("Messages", "ok" if not failed else "needs_you", "" if not failed else f"{failed} message(s) failed to send in the last 2 days (see the outbox)")

    # speech
    from . import stt
    add("Hearing", "ok" if (stt.available() or stt.gemini_hearing_on()) else "needs_you",
        "" if (stt.available() or stt.gemini_hearing_on()) else "voice notes can't be understood yet (send /voicecheck)")

    if live:
        from . import telegram
        if settings.telegram_token:
            try:
                telegram.api("getMe", http_timeout=15)
                add("Telegram", "ok")
            except Exception as exc:  # noqa: BLE001
                add("Telegram", "needs_you", f"the bot didn't answer ({str(exc)[:80]})")
        if settings.gemini_key:
            from . import brain
            ok, secs, why = brain.gemini_check()
            add("Gemini (fast brain, voices, hearing)", "ok" if ok else "needs_you", f"{secs:.1f}s" if ok else why)

    needs = [c for c in out if c["status"] == "needs_you"]
    fixed = [c for c in out if c["status"] == "fixed"]
    good = len(out) - len(needs)
    summary = f"🩺 Self-check: {good}/{len(out)} OK" + (f", fixed {len(fixed)}" if fixed else "") + "."
    if needs:
        summary += "\n" + "\n".join(f"⚠ {c['name']}: {c['detail']}" for c in needs)
    else:
        summary += " Everything's in order, Sir."
    result = {"at": now.isoformat(timespec="seconds"), "checks": out, "summary": summary}
    store.set("selfcheck:last", json.dumps(result))
    if bus is not None:
        bus.log("JARVIS", summary, "job")
    return result


def nightly(store, bus) -> None:
    r = run(store, bus)
    if any(c["status"] == "needs_you" for c in r["checks"]):
        from . import telegram
        try:
            telegram.send(r["summary"])
        except Exception:  # noqa: BLE001
            pass
