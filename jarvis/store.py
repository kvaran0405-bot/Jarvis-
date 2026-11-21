"""SQLite-backed memory for JARVIS: tasks, schedule, notes, goals, habits, career, money, reports."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    area TEXT NOT NULL DEFAULT 'personal',      -- personal | career | academic | health | finance
    priority INTEGER NOT NULL DEFAULT 3,         -- 1 (highest) .. 5
    due TEXT,                                    -- ISO date or datetime
    status TEXT NOT NULL DEFAULT 'todo',         -- todo | doing | done | cancelled
    assignee TEXT,                               -- agent that should work on it autonomously (e.g. ORACLE)
    notes TEXT DEFAULT '',
    result TEXT DEFAULT '',
    created TEXT NOT NULL,
    updated TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    start TEXT NOT NULL,
    end TEXT,
    location TEXT DEFAULT '',
    area TEXT DEFAULT 'personal',
    notes TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    tags TEXT DEFAULT '',
    agent TEXT DEFAULT '',
    created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS goals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    area TEXT NOT NULL DEFAULT 'personal',
    target_date TEXT,
    progress INTEGER NOT NULL DEFAULT 0,         -- 0..100
    notes TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'active'
);
CREATE TABLE IF NOT EXISTS habits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    cadence TEXT NOT NULL DEFAULT 'daily'
);
CREATE TABLE IF NOT EXISTS habit_log (
    habit_id INTEGER NOT NULL,
    day TEXT NOT NULL,
    PRIMARY KEY (habit_id, day)
);
CREATE TABLE IF NOT EXISTS applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    company TEXT NOT NULL,
    role TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'interested',   -- interested | applied | interview | offer | rejected
    link TEXT DEFAULT '',
    next_step TEXT DEFAULT '',
    updated TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    day TEXT NOT NULL,
    amount REAL NOT NULL,                        -- negative = spend, positive = income
    category TEXT NOT NULL DEFAULT 'other',
    note TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS memory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fact TEXT NOT NULL,
    created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    agent TEXT NOT NULL,
    title TEXT NOT NULL,
    body TEXT NOT NULL,
    created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS activity (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'log',
    message TEXT NOT NULL,
    created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    phone TEXT DEFAULT '',                       -- international format, digits only, e.g. 2348012345678
    email TEXT DEFAULT '',
    relationship TEXT DEFAULT '',
    notes TEXT DEFAULT '',
    trusted INTEGER NOT NULL DEFAULT 0           -- 1 = agents may message without asking (in 'trusted' mode)
);
CREATE TABLE IF NOT EXISTS outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel TEXT NOT NULL,                       -- email | whatsapp
    recipient TEXT NOT NULL,                     -- email address or phone number
    recipient_name TEXT DEFAULT '',
    subject TEXT DEFAULT '',
    body TEXT NOT NULL,
    reply_to TEXT DEFAULT '',                    -- email Message-ID being answered
    agent TEXT NOT NULL,
    reason TEXT DEFAULT '',                      -- why the agent wants to send it
    status TEXT NOT NULL DEFAULT 'pending',      -- pending | approved | sent | rejected | failed
    send_at TEXT,                                -- ISO datetime; NULL = as soon as allowed
    error TEXT DEFAULT '',
    result TEXT DEFAULT '',                      -- output of a computer action
    created TEXT NOT NULL,
    sent_at TEXT
);
CREATE TABLE IF NOT EXISTS agent_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent TEXT NOT NULL,                         -- each agent's private notebook
    note TEXT NOT NULL,
    created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reply_suggestions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    channel TEXT NOT NULL DEFAULT 'email',
    sender TEXT NOT NULL,                        -- address to reply to
    sender_name TEXT DEFAULT '',
    subject TEXT DEFAULT '',
    message_id TEXT DEFAULT '',                  -- original e-mail Message-ID (for threading)
    language TEXT DEFAULT '',
    translation TEXT DEFAULT '',
    gist TEXT NOT NULL,                          -- what they want, in plain words
    options TEXT NOT NULL,                       -- JSON list of {label, body}
    status TEXT NOT NULL DEFAULT 'open',         -- open | sent | ignored
    chosen TEXT DEFAULT '',
    agent TEXT NOT NULL,
    created TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS routines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    schedule TEXT NOT NULL,                      -- 'daily 08:00' | 'weekly mon 08:00' | 'every 2h'
    agent TEXT NOT NULL,
    prompt TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    last_run TEXT
);
"""


def normalize_phone(phone: str) -> str:
    """Digits only, international format (no +). '+234 801-234 5678' -> '2348012345678'."""
    return "".join(ch for ch in str(phone or "") if ch.isdigit())


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        if str(path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._db.executescript(SCHEMA)
        self._db.commit()

    # ---------- low level ----------
    def query(self, sql: str, params: tuple | list = ()) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._db.execute(sql, params).fetchall()]

    def execute(self, sql: str, params: tuple | list = ()) -> int:
        with self._lock:
            cur = self._db.execute(sql, params)
            self._db.commit()
            return cur.lastrowid or cur.rowcount

    def _update(self, table: str, row_id: int, fields: dict[str, Any], allowed: set[str]) -> bool:
        fields = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if not fields:
            return False
        sets = ", ".join(f"{k} = ?" for k in fields)
        n = self.execute(f"UPDATE {table} SET {sets} WHERE id = ?", [*fields.values(), row_id])
        return n > 0

    # ---------- tasks ----------
    TASK_FIELDS = {"title", "area", "priority", "due", "status", "assignee", "notes", "result"}

    def add_task(self, title: str, area: str = "personal", priority: int = 3, due: str | None = None,
                 notes: str = "", assignee: str | None = None) -> int:
        ts = now_iso()
        return self.execute(
            "INSERT INTO tasks (title, area, priority, due, notes, assignee, created, updated) VALUES (?,?,?,?,?,?,?,?)",
            (title, area, priority, due, notes, assignee.upper() if assignee else None, ts, ts),
        )

    def update_task(self, task_id: int, **fields: Any) -> bool:
        if fields.get("assignee"):
            fields["assignee"] = str(fields["assignee"]).upper()
        ok = self._update("tasks", task_id, fields, self.TASK_FIELDS)
        if ok:
            self.execute("UPDATE tasks SET updated = ? WHERE id = ?", (now_iso(), task_id))
        return ok

    def list_tasks(self, status: str | None = "open", area: str | None = None, assignee: str | None = None,
                   limit: int = 50) -> list[dict]:
        sql, params = "SELECT * FROM tasks WHERE 1=1", []
        if status == "open":
            sql += " AND status IN ('todo','doing')"
        elif status and status != "all":
            sql += " AND status = ?"
            params.append(status)
        if area:
            sql += " AND area = ?"
            params.append(area)
        if assignee:
            sql += " AND assignee = ?"
            params.append(assignee.upper())
        sql += " ORDER BY (due IS NULL), due, priority, id LIMIT ?"
        params.append(limit)
        return self.query(sql, params)

    def get_task(self, task_id: int) -> dict | None:
        rows = self.query("SELECT * FROM tasks WHERE id = ?", (task_id,))
        return rows[0] if rows else None

    # ---------- events ----------
    def add_event(self, title: str, start: str, end: str | None = None, location: str = "",
                  area: str = "personal", notes: str = "") -> int:
        return self.execute("INSERT INTO events (title, start, end, location, area, notes) VALUES (?,?,?,?,?,?)",
                            (title, start, end, location, area, notes))

    def list_events(self, start: str, end: str) -> list[dict]:
        return self.query("SELECT * FROM events WHERE start >= ? AND start < ? ORDER BY start", (start, end))

    def delete_event(self, event_id: int) -> bool:
        return self.execute("DELETE FROM events WHERE id = ?", (event_id,)) > 0

    # ---------- notes / memory ----------
    def add_note(self, title: str, body: str, tags: str = "", agent: str = "") -> int:
        return self.execute("INSERT INTO notes (title, body, tags, agent, created) VALUES (?,?,?,?,?)",
                            (title, body, tags, agent, now_iso()))

    def search_notes(self, query: str = "", limit: int = 10) -> list[dict]:
        like = f"%{query}%"
        return self.query("SELECT * FROM notes WHERE title LIKE ? OR body LIKE ? OR tags LIKE ? "
                          "ORDER BY id DESC LIMIT ?", (like, like, like, limit))

    def remember(self, fact: str) -> int:
        return self.execute("INSERT INTO memory (fact, created) VALUES (?,?)", (fact, now_iso()))

    def memories(self, limit: int = 100) -> list[dict]:
        return self.query("SELECT * FROM memory ORDER BY id DESC LIMIT ?", (limit,))

    def forget(self, memory_id: int) -> bool:
        return self.execute("DELETE FROM memory WHERE id = ?", (memory_id,)) > 0

    # ---------- each agent's private notebook ----------
    def add_agent_note(self, agent: str, note: str) -> int:
        return self.execute("INSERT INTO agent_notes (agent, note, created) VALUES (?,?,?)",
                            (agent.upper(), note, now_iso()))

    def agent_notes(self, agent: str, limit: int = 30) -> list[dict]:
        return self.query("SELECT * FROM agent_notes WHERE agent = ? ORDER BY id DESC LIMIT ?", (agent.upper(), limit))

    def delete_agent_note(self, note_id: int) -> bool:
        return self.execute("DELETE FROM agent_notes WHERE id = ?", (note_id,)) > 0

    # ---------- suggested replies ----------
    def add_suggestion(self, *, sender: str, gist: str, options: list[dict], agent: str, sender_name: str = "",
                       subject: str = "", message_id: str = "", language: str = "", translation: str = "",
                       channel: str = "email") -> int:
        return self.execute(
            "INSERT INTO reply_suggestions (channel, sender, sender_name, subject, message_id, language, translation, "
            "gist, options, agent, created) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (channel, sender, sender_name, subject, message_id, language, translation, gist, json.dumps(options),
             agent, now_iso()))

    def get_suggestion(self, sid: int) -> dict | None:
        rows = self.query("SELECT * FROM reply_suggestions WHERE id = ?", (sid,))
        if not rows:
            return None
        row = rows[0]
        row["options"] = json.loads(row["options"])
        return row

    def list_suggestions(self, status: str = "open", limit: int = 20) -> list[dict]:
        rows = self.query("SELECT * FROM reply_suggestions WHERE status = ? ORDER BY id DESC LIMIT ?", (status, limit))
        for r in rows:
            r["options"] = json.loads(r["options"])
        return rows

    def set_suggestion(self, sid: int, status: str, chosen: str = "") -> bool:
        return self.execute("UPDATE reply_suggestions SET status = ?, chosen = ? WHERE id = ?",
                            (status, chosen, sid)) > 0

    # ---------- goals ----------
    def add_goal(self, title: str, area: str = "personal", target_date: str | None = None, notes: str = "") -> int:
        return self.execute("INSERT INTO goals (title, area, target_date, notes) VALUES (?,?,?,?)",
                            (title, area, target_date, notes))

    def update_goal(self, goal_id: int, **fields: Any) -> bool:
        return self._update("goals", goal_id, fields, {"title", "area", "target_date", "progress", "notes", "status"})

    def list_goals(self, status: str = "active") -> list[dict]:
        return self.query("SELECT * FROM goals WHERE status = ? ORDER BY (target_date IS NULL), target_date", (status,))

    # ---------- habits ----------
    def add_habit(self, name: str, cadence: str = "daily") -> int:
        self.execute("INSERT OR IGNORE INTO habits (name, cadence) VALUES (?,?)", (name, cadence))
        return self.query("SELECT id FROM habits WHERE name = ?", (name,))[0]["id"]

    def log_habit(self, name: str, day: str) -> bool:
        habit_id = self.add_habit(name)
        self.execute("INSERT OR IGNORE INTO habit_log (habit_id, day) VALUES (?,?)", (habit_id, day))
        return True

    def habit_status(self, since_day: str) -> list[dict]:
        return self.query(
            "SELECT h.name, h.cadence, COUNT(l.day) AS done_count, MAX(l.day) AS last_done "
            "FROM habits h LEFT JOIN habit_log l ON l.habit_id = h.id AND l.day >= ? "
            "GROUP BY h.id ORDER BY h.name", (since_day,))

    # ---------- career ----------
    def add_application(self, company: str, role: str, status: str = "interested", link: str = "",
                        next_step: str = "") -> int:
        return self.execute("INSERT INTO applications (company, role, status, link, next_step, updated) "
                            "VALUES (?,?,?,?,?,?)", (company, role, status, link, next_step, now_iso()))

    def update_application(self, app_id: int, **fields: Any) -> bool:
        ok = self._update("applications", app_id, fields, {"company", "role", "status", "link", "next_step"})
        if ok:
            self.execute("UPDATE applications SET updated = ? WHERE id = ?", (now_iso(), app_id))
        return ok

    def list_applications(self, status: str | None = None) -> list[dict]:
        if status:
            return self.query("SELECT * FROM applications WHERE status = ? ORDER BY updated DESC", (status,))
        return self.query("SELECT * FROM applications ORDER BY updated DESC")

    # ---------- money ----------
    def log_transaction(self, day: str, amount: float, category: str = "other", note: str = "") -> int:
        return self.execute("INSERT INTO transactions (day, amount, category, note) VALUES (?,?,?,?)",
                            (day, amount, category, note))

    def spending_summary(self, since_day: str) -> dict:
        rows = self.query("SELECT category, SUM(amount) AS total, COUNT(*) AS n FROM transactions "
                          "WHERE day >= ? GROUP BY category ORDER BY total", (since_day,))
        total = sum(r["total"] for r in rows)
        return {"since": since_day, "net": round(total, 2), "by_category": rows}

    # ---------- reports / activity ----------
    def save_report(self, kind: str, agent: str, title: str, body: str) -> int:
        return self.execute("INSERT INTO reports (kind, agent, title, body, created) VALUES (?,?,?,?,?)",
                            (kind, agent, title, body, now_iso()))

    def list_reports(self, limit: int = 20, kind: str | None = None) -> list[dict]:
        if kind:
            return self.query("SELECT * FROM reports WHERE kind = ? ORDER BY id DESC LIMIT ?", (kind, limit))
        return self.query("SELECT * FROM reports ORDER BY id DESC LIMIT ?", (limit,))

    def get_report(self, report_id: int) -> dict | None:
        rows = self.query("SELECT * FROM reports WHERE id = ?", (report_id,))
        return rows[0] if rows else None

    def log_activity(self, agent: str, message: str, kind: str = "log") -> dict:
        row = {"agent": agent, "kind": kind, "message": message, "created": now_iso()}
        row["id"] = self.execute("INSERT INTO activity (agent, kind, message, created) VALUES (?,?,?,?)",
                                 (agent, kind, message, row["created"]))
        return row

    def recent_activity(self, limit: int = 50) -> list[dict]:
        return list(reversed(self.query("SELECT * FROM activity ORDER BY id DESC LIMIT ?", (limit,))))

    # ---------- contacts ----------
    def add_contact(self, name: str, phone: str = "", email: str = "", relationship: str = "", notes: str = "",
                    trusted: bool = False) -> int:
        return self.execute("INSERT INTO contacts (name, phone, email, relationship, notes, trusted) "
                            "VALUES (?,?,?,?,?,?)",
                            (name, normalize_phone(phone), email.strip().lower(), relationship, notes, int(trusted)))

    def update_contact(self, contact_id: int, **fields: Any) -> bool:
        if "phone" in fields and fields["phone"] is not None:
            fields["phone"] = normalize_phone(fields["phone"])
        if "trusted" in fields and fields["trusted"] is not None:
            fields["trusted"] = int(bool(fields["trusted"]))
        return self._update("contacts", contact_id, fields,
                            {"name", "phone", "email", "relationship", "notes", "trusted"})

    def find_contacts(self, query: str = "") -> list[dict]:
        like = f"%{query.strip()}%"
        return self.query("SELECT * FROM contacts WHERE name LIKE ? OR phone LIKE ? OR email LIKE ? "
                          "OR relationship LIKE ? ORDER BY name LIMIT 50", (like, like, like, like))

    def contact_for(self, channel: str, recipient: str) -> dict | None:
        if channel == "email":
            rows = self.query("SELECT * FROM contacts WHERE email = ?", (recipient.strip().lower(),))
        else:
            rows = self.query("SELECT * FROM contacts WHERE phone = ?", (normalize_phone(recipient),))
        return rows[0] if rows else None

    # ---------- outbox ----------
    def queue_message(self, channel: str, recipient: str, body: str, agent: str, *, subject: str = "",
                      recipient_name: str = "", reply_to: str = "", reason: str = "", status: str = "pending",
                      send_at: str | None = None) -> int:
        if channel == "whatsapp":
            recipient = normalize_phone(recipient)
        return self.execute(
            "INSERT INTO outbox (channel, recipient, recipient_name, subject, body, reply_to, agent, reason, status, "
            "send_at, created) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (channel, recipient, recipient_name, subject, body, reply_to, agent, reason, status, send_at, now_iso()))

    def get_message(self, msg_id: int) -> dict | None:
        rows = self.query("SELECT * FROM outbox WHERE id = ?", (msg_id,))
        return rows[0] if rows else None

    def list_outbox(self, status: str | None = None, limit: int = 50) -> list[dict]:
        if status:
            return self.query("SELECT * FROM outbox WHERE status = ? ORDER BY id DESC LIMIT ?", (status, limit))
        return self.query("SELECT * FROM outbox ORDER BY id DESC LIMIT ?", (limit,))

    def set_message(self, msg_id: int, **fields: Any) -> bool:
        return self._update("outbox", msg_id, fields,
                            {"status", "body", "subject", "error", "result", "sent_at", "send_at", "recipient"})

    def due_messages(self, now: str) -> list[dict]:
        return self.query("SELECT * FROM outbox WHERE status = 'approved' AND (send_at IS NULL OR send_at <= ?) "
                          "ORDER BY id", (now,))

    # ---------- routines ----------
    def add_routine(self, name: str, schedule: str, agent: str, prompt: str) -> int:
        return self.execute("INSERT INTO routines (name, schedule, agent, prompt) VALUES (?,?,?,?)",
                            (name, schedule.strip().lower(), agent.upper(), prompt))

    def list_routines(self, enabled_only: bool = False) -> list[dict]:
        sql = "SELECT * FROM routines" + (" WHERE enabled = 1" if enabled_only else "") + " ORDER BY id"
        return self.query(sql)

    def update_routine(self, routine_id: int, **fields: Any) -> bool:
        return self._update("routines", routine_id, fields, {"name", "schedule", "agent", "prompt", "enabled",
                                                             "last_run"})

    def delete_routine(self, routine_id: int) -> bool:
        return self.execute("DELETE FROM routines WHERE id = ?", (routine_id,)) > 0

    # ---------- kv ----------
    def get(self, key: str, default: Any = None) -> Any:
        rows = self.query("SELECT value FROM kv WHERE key = ?", (key,))
        return json.loads(rows[0]["value"]) if rows else default

    def set(self, key: str, value: Any) -> None:
        self.execute("INSERT INTO kv (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                     (key, json.dumps(value)))
