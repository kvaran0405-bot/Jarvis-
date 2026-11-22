"""Google Calendar sync through a tiny Google Apps Script that the owner pastes into their own Google account.

Why a script and not "Sign in with Google": a script needs no Google Cloud project, no OAuth client and no
"unverified app" review. The owner copies the script (with a secret key already filled in), clicks Deploy, and
pastes the web-app link into JARVIS. The script runs as the owner, only answers requests that carry the key,
and only touches their main calendar.

JARVIS keeps its own calendar table as the working copy: Google events are pulled in every few minutes (rows with
a `gid`), and events the agents add are pushed to Google straight away.
"""
from __future__ import annotations

import json
import secrets
import threading
import urllib.request
from datetime import datetime, timedelta

from .config import settings

_store = None
_lock = threading.Lock()
_push_lock = threading.Lock()   # one push at a time, so an event is never created twice in Google
SYNC_DAYS_BACK, SYNC_DAYS_AHEAD = 1, 90
SYNC_EVERY_MIN = 10


def attach(store) -> None:
    global _store
    _store = store


def key() -> str:
    """The secret the script checks. Made once and kept in JARVIS's database."""
    import os
    k = os.environ.get("JARVIS_GOOGLE_KEY", "").strip()
    if k or _store is None:
        return k
    k = _store.get("google:key")
    if not k:
        k = secrets.token_urlsafe(24)
        _store.set("google:key", k)
    return k


def script_url() -> str:
    import os
    return os.environ.get("JARVIS_GOOGLE_SCRIPT_URL", "").strip() or (_store.get("google:script_url") if _store else "") or ""


def ready() -> bool:
    return bool(script_url())


def call(action: str, timeout: int = 30, **params) -> dict:
    url = script_url()
    if not url:
        raise RuntimeError("Google Calendar isn't connected yet (Autopilot tab → Google Calendar → Set up)")
    return _post(url, {"key": key(), "action": action, **params}, timeout)


def _post(url: str, payload: dict, timeout: int = 30) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "text/plain;charset=utf-8"})
    # Apps Script answers with a redirect to the result; urllib follows it as a GET, which is what Google expects.
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", "replace")
    try:
        out = json.loads(raw)
    except json.JSONDecodeError:
        hint = "sign-in page" if "<html" in raw.lower() else raw[:120]
        raise RuntimeError("Google sent back a " + hint + " instead of an answer. In the deployment, 'Who has access' "
                           "must be 'Anyone' (the secret key keeps it private).") from None
    if not out.get("ok"):
        raise RuntimeError(f"Google Calendar: {out.get('error', 'unknown error')}")
    return out


def connect(url: str) -> dict:
    """Test a pasted web-app link and save it."""
    url = url.strip()
    if not url.startswith("https://script.google.com/") or "/exec" not in url:
        raise ValueError("That doesn't look like the web app link. It starts with https://script.google.com/ "
                         "and ends with /exec")
    info = _post(url, {"key": key(), "action": "ping"}, timeout=30)
    _store.set("google:script_url", url)
    threading.Thread(target=sync, daemon=True).start()
    return info


def disconnect() -> None:
    _store.set("google:script_url", "")


# ---------------------------------------------------------------- time conversion
def to_google(local_value: str) -> str:
    """'2026-11-25T14:00' (owner's time) -> '2026-11-25T14:00:00+08:00'. Dates stay dates."""
    if len(local_value) <= 10:
        return local_value
    dt = datetime.fromisoformat(local_value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=settings.tz)
    return dt.isoformat(timespec="seconds")


def from_google(value: str, all_day: bool = False) -> str:
    """Google's UTC time -> the owner's local 'YYYY-MM-DDTHH:MM' (or a plain date for all-day events)."""
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is not None:
        dt = dt.astimezone(settings.tz).replace(tzinfo=None)
    return dt.date().isoformat() if all_day else dt.isoformat(timespec="minutes")


# ---------------------------------------------------------------- push / pull
def push_event(store, event: dict) -> str:
    """Create a JARVIS event in Google Calendar; returns and saves its Google id."""
    with _push_lock:
        fresh = store.get_event(event["id"])
        if fresh is None:
            return ""
        if fresh.get("gid"):
            return fresh["gid"]   # already pushed (by the sync running in the background)
        return _push(store, fresh)


def _push(store, event: dict) -> str:
    start = event["start"]
    all_day = len(start) <= 10
    end = event.get("end") or ""
    if not all_day and not end:
        end = (datetime.fromisoformat(start) + timedelta(hours=1)).isoformat(timespec="minutes")
    notes = event.get("notes") or ""
    out = call("create", title=event["title"], start=to_google(start), end=to_google(end) if end else "",
               allDay=all_day, location=event.get("location") or "", notes=notes)
    gid = f"{out['id']}|{start}"
    store.set_event_gid(event["id"], gid)
    return gid


def delete_event(gid: str) -> None:
    call("delete", id=gid.split("|", 1)[0], start=to_google(gid.split("|", 1)[1]) if "|" in gid else "")


def sync(force: bool = False) -> dict:
    """Two-way sync: push JARVIS's new events, pull Google's events for the next weeks."""
    store = _store
    if store is None or not ready():
        return {"synced": False, "reason": "not connected"}
    if not (_lock.acquire(timeout=60) if force else _lock.acquire(blocking=False)):
        return {"synced": False, "reason": "already syncing"}
    try:
        now = datetime.now(settings.tz)
        last = store.get("google:last_sync")
        if not force and last and datetime.fromisoformat(last) > now - timedelta(minutes=SYNC_EVERY_MIN):
            return {"synced": False, "reason": "synced recently"}
        start = (now - timedelta(days=SYNC_DAYS_BACK)).date()
        end = (now + timedelta(days=SYNC_DAYS_AHEAD)).date()
        pushed = 0
        for ev in store.unsynced_events(now.date().isoformat()):
            push_event(store, ev)
            pushed += 1
        out = call("list", start=to_google(start.isoformat() + "T00:00"), end=to_google(end.isoformat() + "T00:00"),
                   timeout=60)
        seen = set()
        for g in out.get("events", []):
            local_start = from_google(g["start"], g.get("allDay", False))
            local_end = None
            if not g.get("allDay"):
                local_end = from_google(g["end"])
            gid = f"{g['id']}|{local_start}"
            seen.add(gid)
            store.upsert_google_event(gid, g.get("title") or "(no title)", local_start, local_end,
                                      g.get("location") or "", g.get("notes") or "")
        removed = 0
        for ev in store.google_events_between(start.isoformat(), end.isoformat()):
            if ev["gid"] not in seen:   # deleted or moved in Google
                store.delete_event(ev["id"])
                removed += 1
        store.set("google:last_sync", now.isoformat())
        store.set("google:last_error", "")
        return {"synced": True, "pulled": len(seen), "pushed": pushed, "removed": removed}
    except Exception as exc:  # noqa: BLE001 - keep working offline, report on the dashboard
        store.set("google:last_error", str(exc)[:300])
        store.set("google:last_sync", datetime.now(settings.tz).isoformat())   # don't hammer Google on errors
        return {"synced": False, "reason": str(exc)}
    finally:
        _lock.release()


def status() -> dict:
    if _store is None:
        return {"ready": False}
    return {"ready": ready(), "last_sync": _store.get("google:last_sync"), "error": _store.get("google:last_error")}


# ---------------------------------------------------------------- the script the owner pastes into Google
SCRIPT = r"""// JARVIS <-> Google Calendar. Paste this whole file into script.google.com, then Deploy > New deployment >
// Web app, Execute as: Me, Who has access: Anyone. The secret key below keeps everyone else out.
const KEY = "__KEY__";

function doPost(e) {
  var out;
  try {
    var req = JSON.parse(e.postData.contents);
    if (req.key !== KEY) throw new Error("wrong key");
    var cal = CalendarApp.getDefaultCalendar();
    if (req.action === "ping") {
      out = {ok: true, calendar: cal.getName(), timezone: Session.getScriptTimeZone()};
    } else if (req.action === "list") {
      var events = cal.getEvents(new Date(req.start), new Date(req.end));
      out = {ok: true, events: events.map(function (ev) {
        return {id: ev.getId(), title: ev.getTitle(), allDay: ev.isAllDayEvent(),
                start: ev.isAllDayEvent() ? Utilities.formatDate(ev.getAllDayStartDate(), Session.getScriptTimeZone(), "yyyy-MM-dd") : ev.getStartTime().toISOString(),
                end: ev.getEndTime().toISOString(), location: ev.getLocation(),
                notes: (ev.getDescription() || "").slice(0, 500)};
      })};
    } else if (req.action === "create") {
      var opts = {location: req.location || "", description: req.notes || ""};
      var ev = req.allDay ? cal.createAllDayEvent(req.title, parseDay(req.start), opts)
                          : cal.createEvent(req.title, new Date(req.start), new Date(req.end), opts);
      out = {ok: true, id: ev.getId()};
    } else if (req.action === "delete") {
      var ev = cal.getEventById(req.id);
      if (ev && !ev.isRecurringEvent()) ev.deleteEvent();
      out = {ok: true, deleted: !!ev && !ev.isRecurringEvent()};
    } else {
      throw new Error("unknown action " + req.action);
    }
  } catch (err) {
    out = {ok: false, error: String(err)};
  }
  return ContentService.createTextOutput(JSON.stringify(out)).setMimeType(ContentService.MimeType.JSON);
}

function parseDay(s) {
  var p = s.split("-");
  return new Date(Number(p[0]), Number(p[1]) - 1, Number(p[2]));
}

// Run this once from the editor (Run button) so Google asks for calendar permission.
function authorize() {
  Logger.log(CalendarApp.getDefaultCalendar().getName());
}
"""


def script_text() -> str:
    return SCRIPT.replace("__KEY__", key())
