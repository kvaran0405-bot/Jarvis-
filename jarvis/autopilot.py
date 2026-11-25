"""The team's everyday autopilot (the owner's picks, Nov 2026):

- ATHENA's deadline radar: every task or event with a due date gets a nudge 3 days and 1 day before.
- EDITH's laptop care: nightly health check (disk space, memory, battery wear, the backup) with a heads-up in
  the boss's briefing when something needs attention.
- SENTINEL's scam shield on phone notifications (see scam.py).
All of it goes through notify_owner, so nothing reaches the owner while they sleep: it waits for them.
"""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timedelta

from .config import ROOT, settings

SCHOOL = re.compile(r"\b(exam|assignment|submit|submission|deadline|quiz|project|essay|test|presentation|report|lab|tutorial|due)\b", re.I)


# ---------------------------------------------------------------- ATHENA: deadline nudges (3 days and 1 day before)
def deadline_nudges(store, bus, now: datetime | None = None) -> list[str]:
    now = now or datetime.now(settings.tz)
    said = []
    items = [{"title": t["title"], "due": t["due"], "key": f"t{t['id']}"} for t in store.list_tasks("open", limit=200) if t.get("due")]
    for e in store.list_events(now.isoformat(), (now + timedelta(days=3, hours=2)).isoformat()):
        if SCHOOL.search(e["title"] or ""):
            items.append({"title": e["title"], "due": e["start"], "key": f"e{e['id']}"})
    for it in items:
        try:
            due = datetime.fromisoformat(it["due"][:16] if len(it["due"]) > 10 else it["due"][:10] + "T23:59")
            if due.tzinfo is None:
                due = due.replace(tzinfo=settings.tz)
        except ValueError:
            continue
        left = due - now
        for stage, window in (("1d", timedelta(days=1)), ("3d", timedelta(days=3))):
            key = f"nudge:{it['key']}:{stage}"
            if timedelta(0) < left <= window and not store.get(key):
                store.set(key, now.isoformat())
                if stage == "3d" and left <= timedelta(days=1):
                    break   # already inside the last day: only the 1-day nudge
                agent = "ATHENA" if SCHOOL.search(it["title"]) else "JARVIS"
                when = "tomorrow" if left <= timedelta(days=1) else f"in {left.days or 1} days"
                msg = (f"Heads up: {it['title']} is due {when} ({due:%a %d %b, %H:%M})."
                       + (" Want me to block out time to finish it?" if stage == "1d" else " Let's get ahead of it."))
                from .notify import notify_owner
                from .speech import announce
                notify_owner(f"⏳ {agent}: due {when}", msg, short=True)
                announce(bus, agent, msg)
                said.append(msg)
                break
    return said


# ---------------------------------------------------------------- EDITH: laptop health
def laptop_health() -> dict:
    issues, info = [], {}
    try:
        du = shutil.disk_usage(str(ROOT.anchor or "/"))
        free_pct = du.free / du.total * 100
        info["disk_free_gb"] = round(du.free / 1e9, 1)
        if free_pct < 10 or du.free < 15e9:
            issues.append(f"the main drive is nearly full ({info['disk_free_gb']} GB free)")
    except Exception:  # noqa: BLE001
        pass
    try:
        import psutil
        vm = psutil.virtual_memory()
        info["memory_used_pct"] = vm.percent
        if vm.percent > 90:
            hogs = sorted(psutil.process_iter(["name", "memory_percent"]), key=lambda p: -(p.info.get("memory_percent") or 0))[:3]
            issues.append(f"memory is {vm.percent:.0f}% full (biggest: {', '.join(p.info['name'] for p in hogs if p.info.get('name'))})")
        b = psutil.sensors_battery()
        if b is not None:
            info["battery_pct"] = b.percent
        boot = datetime.fromtimestamp(psutil.boot_time())
        info["uptime_days"] = (datetime.now() - boot).days
        if info["uptime_days"] >= 7:
            issues.append(f"it hasn't restarted in {info['uptime_days']} days (a restart clears the slowdown)")
    except Exception:  # noqa: BLE001
        pass
    try:
        from . import devices
        backups = sorted((devices.WORKSPACE / "Backups").iterdir()) if (devices.WORKSPACE / "Backups").exists() else []
        info["last_backup"] = backups[-1].name if backups else None
        if not backups or backups[-1].name < (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d"):
            issues.append("there's no backup from the last 3 days")
    except Exception:  # noqa: BLE001
        pass
    return {"issues": issues, "info": info, "checked": datetime.now(settings.tz).isoformat(timespec="minutes")}


def laptop_check(store) -> dict:
    out = laptop_health()
    store.set("laptop:health", json.dumps(out))
    return out


# ---------------------------------------------------------------- SENTINEL: scam shield on what arrives on the phone
def scam_watch(store, bus, app: str, sender: str, text: str) -> str:
    from .scam import check
    c = check(f"{sender}\n{text}", sender)
    if not c["scam"]:
        return ""
    key = f"scam:{abs(hash((app, sender, text[:80]))) % 10**9}"
    if store.get(key):
        return ""
    store.set(key, "1")
    msg = (f"Careful: that {app} message from {sender[:40]} looks like a scam ({', '.join(c['reasons'][:3])}). "
           "Don't tap the link, pay, or share any code.")
    from .notify import notify_owner
    from .speech import announce
    notify_owner("🛡 SENTINEL: likely scam", msg, short=True, urgent=True)   # a scam can't wait till you wake
    announce(bus, "SENTINEL", msg, critical=True)
    return msg
