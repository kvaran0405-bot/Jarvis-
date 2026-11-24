"""Cloud JARVIS + laptop satellite (#7).

JARVIS can run in one of three roles (JARVIS_ROLE in .env):

- "laptop" (default): everything on the laptop, as before.
- "cloud": JARVIS lives on an always-on server (e.g. Oracle Cloud's free tier). Telegram, the night shift, the phone
  link and the brain run there 24/7. Anything that needs the laptop itself (its screen, files, apps, shell commands
  you approved, the lecture recorder) is passed to the laptop satellite when the laptop is on; when it's off, JARVIS
  says so and offers to do it later.
- "satellite": the laptop's side. `python -m jarvis satellite` keeps a link to the cloud (JARVIS_CLOUD_URL) and
  carries out those laptop jobs. The token JARVIS_SATELLITE_TOKEN must match on both machines (the setup script
  makes one and copies it across; it never goes into the repository).
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta

from .config import settings

LAPTOP_TOOLS = {   # tools that act on the laptop itself
    "laptop_status", "open_on_laptop", "laptop_screenshot", "lock_laptop", "find_files", "read_file", "write_file",
    "send_file_to_phone", "start_recording", "stop_recording",
    "list_windows", "window_action", "snap_windows", "show_desktop", "media_control", "set_brightness",
    "save_workspace", "open_workspace", "organise_folder", "rename_files", "make_slides", "make_spreadsheet", "look_at_screen",
}


def role() -> str:
    r = (os.environ.get("JARVIS_ROLE") or "laptop").strip().lower()
    return r if r in ("laptop", "cloud", "satellite") else "laptop"


def token() -> str:
    return os.environ.get("JARVIS_SATELLITE_TOKEN", "")


def _ensure(store) -> None:
    store.execute("CREATE TABLE IF NOT EXISTS sat_cmds (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT, payload TEXT, "
                  "status TEXT DEFAULT 'pending', result TEXT DEFAULT '', created TEXT)")


def online(store, seconds: int = 90) -> bool:
    last = store.get("sat:last_seen")
    return bool(last) and datetime.fromisoformat(last) > datetime.now(settings.tz) - timedelta(seconds=seconds)


def remote(store, kind: str, payload: dict, timeout: float = 75) -> str:
    """Ask the laptop satellite to do something and wait for its answer. Raises if the laptop is off or too slow."""
    if not online(store):
        raise RuntimeError("the laptop is off or asleep right now")
    _ensure(store)
    cid = store.execute("INSERT INTO sat_cmds (kind, payload, created) VALUES (?,?,?)",
                        (kind, json.dumps(payload, default=str), datetime.now(settings.tz).isoformat()))
    end = time.time() + timeout
    while time.time() < end:
        row = store.query("SELECT status, result FROM sat_cmds WHERE id = ?", (cid,))[0]
        if row["status"] in ("done", "failed"):
            if row["status"] == "failed":
                raise RuntimeError(row["result"] or "the laptop couldn't do it")
            return row["result"]
        time.sleep(.4)
    store.execute("UPDATE sat_cmds SET status = 'expired' WHERE id = ? AND status IN ('pending','sent')", (cid,))
    raise RuntimeError("the laptop didn't answer in time")


def run_tool_remotely(store, name: str, args: dict) -> tuple[str, bool]:
    """On the cloud: a laptop tool. Done by the satellite if the laptop is on, else a clear answer."""
    try:
        out = remote(store, "tool", {"name": name, "args": args})
        data = json.loads(out)
        return data.get("output", ""), bool(data.get("error"))
    except RuntimeError as exc:
        return (f"{name} needs the laptop, and {exc}. I can do it as soon as it's back on, Sir."), True


# ---------------------------------------------------------------- the cloud's side of the link
def checkin(store) -> list[dict]:
    """The satellite checks in: hand over pending jobs."""
    _ensure(store)
    store.set("sat:last_seen", datetime.now(settings.tz).isoformat())
    rows = store.query("SELECT id, kind, payload FROM sat_cmds WHERE status = 'pending' ORDER BY id LIMIT 10")
    for r in rows:
        store.execute("UPDATE sat_cmds SET status = 'sent' WHERE id = ?", (r["id"],))
    return [{"id": r["id"], "kind": r["kind"], "payload": json.loads(r["payload"])} for r in rows]


def done(store, cid: int, result: str, ok: bool) -> None:
    _ensure(store)
    store.execute("UPDATE sat_cmds SET status = ?, result = ? WHERE id = ?", ("done" if ok else "failed", result[:200000], cid))


# ---------------------------------------------------------------- the laptop's side of the link
def serve_forever(cloud_url: str | None = None) -> None:   # pragma: no cover - a long-running loop on the laptop
    """`python -m jarvis satellite`: keep the laptop linked to the cloud JARVIS and do its laptop jobs."""
    import urllib.request
    from .store import Store
    from .bus import Bus
    from .tools import ToolContext, execute
    url = (cloud_url or os.environ.get("JARVIS_CLOUD_URL", "")).rstrip("/")
    if not url or not token():
        raise SystemExit("Set JARVIS_CLOUD_URL and JARVIS_SATELLITE_TOKEN in .env (the cloud setup script does this).")
    store = Store(settings.db_path)
    bus = Bus(store)

    def call(path: str, body: dict) -> dict:
        req = urllib.request.Request(url + path, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", "X-Jarvis-Satellite": token()})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    print(f"JARVIS satellite: linked to {url}. Laptop jobs from the cloud JARVIS run here.")
    while True:
        try:
            jobs = call("/api/satellite/poll", {"host": os.environ.get("COMPUTERNAME", "laptop")}).get("jobs", [])
            for j in jobs:
                ok, out = True, ""
                try:
                    if j["kind"] == "tool":
                        ctx = ToolContext(store, bus, settings, None, "JARVIS", 0, True)
                        o, err = execute(j["payload"]["name"], ctx, j["payload"].get("args") or {})
                        out = json.dumps({"output": o, "error": err})
                    elif j["kind"] == "shell":
                        from . import devices
                        out = devices.run_command(j["payload"]["command"])
                    else:
                        ok, out = False, "unknown job"
                except Exception as exc:  # noqa: BLE001
                    ok, out = False, str(exc)
                call("/api/satellite/done", {"id": j["id"], "result": out, "ok": ok})
            time.sleep(1.5 if jobs else 3)
        except Exception as exc:  # noqa: BLE001 - cloud unreachable: keep trying
            print("satellite: waiting for the cloud…", str(exc)[:80])
            time.sleep(10)
