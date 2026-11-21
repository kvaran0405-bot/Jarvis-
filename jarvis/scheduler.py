"""Autopilot: runs the daily routines and the night shift while the owner rests."""
from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from .engine import Engine


@dataclass
class Job:
    name: str
    agent: str
    label: str
    due: Callable[[datetime, str | None], bool]   # (now, last_run_iso) -> should run?
    prompt: str | None = None                     # None = custom runner (night shift)


def daily_at(hhmm: str, weekday: int | None = None):
    """Due once per day after HH:MM (optionally only on a weekday, Monday=0)."""
    h, m = (int(x) for x in hhmm.split(":"))

    def due(now: datetime, last: str | None) -> bool:
        if weekday is not None and now.weekday() != weekday:
            return False
        slot = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if now < slot or now - slot > timedelta(hours=3):   # don't fire stale slots hours later
            return False
        return last is None or datetime.fromisoformat(last) < slot
    return due


def every_hours(hours: float):
    def due(now: datetime, last: str | None) -> bool:
        return last is None or now - datetime.fromisoformat(last) >= timedelta(hours=hours)
    return due


DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def parse_schedule(text: str):
    """'daily 08:00' | 'weekly mon 08:00' | 'every 2h' | 'every 30m' -> due(now, last) function."""
    parts = text.strip().lower().split()
    try:
        if parts[0] == "daily" and len(parts) == 2:
            datetime.strptime(parts[1], "%H:%M")
            return daily_at(parts[1])
        if parts[0] == "weekly" and len(parts) == 3 and parts[1][:3] in DAYS:
            datetime.strptime(parts[2], "%H:%M")
            return daily_at(parts[2], weekday=DAYS.index(parts[1][:3]))
        if parts[0] == "every" and len(parts) == 2 and parts[1][-1] in "hm":
            n = float(parts[1][:-1])
            hours = n if parts[1].endswith("h") else n / 60
            if hours < 0.25:
                raise ValueError("minimum interval is 15 minutes")
            return every_hours(hours)
    except (ValueError, IndexError) as exc:
        raise ValueError(f"Bad schedule '{text}': {exc}") from None
    raise ValueError(f"Bad schedule '{text}'. Use 'daily 08:00', 'weekly mon 08:00', 'every 2h' or 'every 30m'.")


MORNING = ("Compile today's morning brief for the owner: schedule, top 3 priorities, deadlines in the next "
           "7 days, overdue items, habits, goals, career pipeline, money, and what the agents completed "
           "overnight (recent reports and tasks done in the last 24h). Publish it as kind 'morning_brief'. "
           "Then think ahead like a chief of staff: `propose` up to 3 concrete actions that would make today or "
           "this week go better (each a yes/no for the owner).")
EVENING = ("Write the evening report: what got done today, what slipped (and reschedule it sensibly), habit "
           "check-in, and a proposed plan for tomorrow with the top 3 priorities. Publish as 'evening_report'. "
           "If tomorrow's plan needs changes the owner should OK (moving things, messages to send), `propose` them.")
WEEKLY = ("Run the weekly review across personal life, career and academics: wins, misses, goal progress "
          "(update goal progress where the data supports it), next week's deadlines and a focused plan. "
          "Delegate to ATHENA and ZEUS for their sections if useful. Publish as 'weekly_review'.")
INBOX = ("Inbox sweep. Call check_email(new_only=true). For each new e-mail that matters: read it in full, then "
         "call suggest_replies with a one-line gist in your own voice (who, what they want, by when), an English "
         "translation if it isn't in English, and 2-3 ready replies the owner can tap to send. Create tasks or "
         "events for requests and deadlines. Ignore newsletters, promotions and automated mail. If something is "
         "urgent, publish an 'alert' report. Finish with a 2-line summary, or just 'Inbox clear.'")
MONEY = ("Weekly money report. Call bank_alerts(days=7) and spending_summary(days=7). List the week's transactions "
         "from the alerts (date, merchant, amount, card/account last 4 digits), group them by category, total "
         "money in and out, flag anything unusual (large, duplicate, unfamiliar merchant, foreign) and upcoming bills. "
         "Log transactions that aren't already in the money log with log_transaction. Publish as 'money_weekly'. "
         "If no alerts were found, say so and suggest turning on e-mail alerts in the bank's app.")
WATCH = ("Deadline sweep: check overdue and next-48h tasks and events, clashes, stalled goals, applications "
         "without a next step. Fix what you can yourself. For anything that needs the owner's say-so (asking for an "
         "extension, dropping or moving something, a message to send) use `propose` with a ready-to-go plan. "
         "If something needs the owner within the next few hours and they may not have seen it (e.g. an exam "
         "or deadline today not started), use `urgent_alert`. "
         "Otherwise reply with a one-line all-clear.")


class Scheduler:
    def __init__(self, engine: Engine):
        self.engine = engine
        self.store, self.bus, self.settings = engine.store, engine.bus, engine.settings
        s = self.settings
        self.jobs = [
            Job("morning_brief", "FRIDAY", "Morning brief", daily_at(s.morning_brief_at), MORNING),
            Job("evening_report", "FRIDAY", "Evening report", daily_at(s.evening_report_at), EVENING),
            Job("weekly_review", "JARVIS", "Weekly review", daily_at(s.weekly_review_at, weekday=6), WEEKLY),
            Job("deadline_watch", "SENTINEL", "Deadline watch", every_hours(s.watch_every_hours), WATCH),
            Job("night_shift", "JARVIS", "Night shift", daily_at(s.night_shift_at), None),
        ]
        from . import channels as ch
        if ch.email_read_ready():
            self.jobs.append(Job("money_weekly", "VERONICA", "Weekly money report",
                                 daily_at(s.money_weekly_at, weekday=6), MONEY))
        if s.inbox_sweep_minutes > 0 and (ch.email_read_ready() or ch.whatsapp_ready()):
            self.jobs.append(Job("inbox_sweep", "HERALD", "Inbox sweep", every_hours(s.inbox_sweep_minutes / 60), INBOX))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._running: set[str] = set()
        self._lock = threading.Lock()

    def job_table(self) -> list[dict]:
        return [{"name": j.name, "agent": j.agent, "label": j.label,
                 "last_run": self.store.get(f"job:{j.name}:last"), "running": j.name in self._running}
                for j in self.jobs]

    # ------------------------------------------------------------ execution
    def run_job(self, name: str) -> str:
        job = next((j for j in self.jobs if j.name == name), None)
        if job is None:
            return f"Unknown job {name}"
        with self._lock:
            if name in self._running:
                return f"{job.label} is already running"
            self._running.add(name)
        try:
            self.store.set(f"job:{name}:last", datetime.now(self.settings.tz).isoformat())
            self.bus.log(job.agent, f"{job.label} started", "job")
            result = self.night_shift() if job.prompt is None else self.engine.run(job.agent, job.prompt,
                                                                                    background=True)
            self.bus.log(job.agent, f"{job.label} complete: {result[:200]}", "job")
            return result
        finally:
            with self._lock:
                self._running.discard(name)

    def run_job_async(self, name: str) -> None:
        threading.Thread(target=self.run_job, args=(name,), daemon=True).start()

    def night_shift(self) -> str:
        """Work through every open task that has an agent assignee, then hand off to the morning brief."""
        from . import brain
        queue = [t for t in self.store.list_tasks("open", limit=200) if t["assignee"]]
        if queue and brain.pick(self.store, background=True) is None:
            return f"No brain available (paused or not set up) - {len(queue)} task(s) left for later, resting."
        done = []
        for task in queue:
            agent = task["assignee"]
            self.store.update_task(task["id"], status="doing")
            prompt = (f"Night-shift assignment (task #{task['id']}, area {task['area']}, due {task['due'] or 'n/a'}):\n"
                      f"{task['title']}\n\nNotes: {task['notes'] or '-'}\n\n"
                      "Do the work fully now. Save the deliverable with `save_note` (title it after the task). "
                      "If the task needs the owner to act, create a clear follow-up task for them. "
                      "Reply with a 2-3 sentence summary of the result.")
            result = self.engine.run(agent, prompt, background=True)
            failed = any(x in result for x in ("hit an error", "reasoning core is offline", "I'm paused",
                                                "AI limit is reached", "I'm resting"))
            self.store.update_task(task["id"], status="todo" if failed else "done", result=result[:4000])
            done.append(f"#{task['id']} {task['title']} ({agent}): {'FAILED' if failed else 'done'}")
        self.bus.publish({"type": "data", "what": "tasks"})
        if not queue:
            return "No assigned tasks in the queue tonight."
        return f"Night shift processed {len(queue)} task(s): " + "; ".join(done)

    # ------------------------------------------------------------ routines & outbox
    def run_routine(self, routine: dict) -> str:
        key = f"routine:{routine['id']}"
        with self._lock:
            if key in self._running:
                return "already running"
            self._running.add(key)
        try:
            self.store.update_routine(routine["id"], last_run=datetime.now(self.settings.tz).isoformat())
            self.bus.log(routine["agent"], f"Routine '{routine['name']}' started", "job")
            result = self.engine.run(routine["agent"], f"Scheduled routine '{routine['name']}':\n{routine['prompt']}",
                                     background=True)
            self.bus.log(routine["agent"], f"Routine '{routine['name']}' done: {result[:200]}", "job")
            return result
        finally:
            with self._lock:
                self._running.discard(key)

    def dispatch_outbox(self) -> int:
        from .channels import deliver
        now = datetime.now(self.settings.tz).isoformat(timespec="seconds")
        sent = 0
        for msg in self.store.due_messages(now):
            sent += deliver(self.store, self.bus, msg)
        return sent

    # ------------------------------------------------------------ loop
    def tick(self) -> None:
        from . import brain
        now = datetime.now(self.settings.tz)
        self.dispatch_outbox()  # approved messages still go out - sending them needs no AI
        if brain.pick(self.store, background=True) is None:
            return  # paused (or no brain): no automatic thinking at all
        for job in self.jobs:
            if job.name not in self._running and job.due(now, self.store.get(f"job:{job.name}:last")):
                self.run_job_async(job.name)
        for routine in self.store.list_routines(enabled_only=True):
            try:
                due = parse_schedule(routine["schedule"])(now, routine["last_run"])
            except ValueError:
                continue
            if due and f"routine:{routine['id']}" not in self._running:
                threading.Thread(target=self.run_routine, args=(routine,), daemon=True).start()

    def start(self) -> None:
        if self._thread:
            return

        def loop():
            while not self._stop.wait(20):
                try:
                    self.tick()
                except Exception as exc:  # noqa: BLE001
                    self.bus.log("JARVIS", f"Scheduler error: {exc}", "error")

        self._thread = threading.Thread(target=loop, daemon=True, name="jarvis-scheduler")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
