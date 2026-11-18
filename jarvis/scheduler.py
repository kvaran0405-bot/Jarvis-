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


def every_hours(hours: int):
    def due(now: datetime, last: str | None) -> bool:
        return last is None or now - datetime.fromisoformat(last) >= timedelta(hours=hours)
    return due


MORNING = ("Compile today's morning brief for the owner: schedule, top 3 priorities, deadlines in the next "
           "7 days, overdue items, habits, goals, career pipeline, money, and what the agents completed "
           "overnight (recent reports and tasks done in the last 24h). Publish it as kind 'morning_brief'.")
EVENING = ("Write the evening report: what got done today, what slipped (and reschedule it sensibly), habit "
           "check-in, and a proposed plan for tomorrow with the top 3 priorities. Publish as 'evening_report'.")
WEEKLY = ("Run the weekly review across personal life, career and academics: wins, misses, goal progress "
          "(update goal progress where the data supports it), next week's deadlines and a focused plan. "
          "Delegate to ATHENA and ZEUS for their sections if useful. Publish as 'weekly_review'.")
WATCH = ("Deadline sweep: check overdue and next-48h tasks and events, clashes, stalled goals, applications "
         "without a next step. Fix what you can. Only publish an 'alert' if the owner must act soon; "
         "otherwise reply with a one-line all-clear.")


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
            result = self.night_shift() if job.prompt is None else self.engine.run(job.agent, job.prompt)
            self.bus.log(job.agent, f"{job.label} complete: {result[:200]}", "job")
            return result
        finally:
            with self._lock:
                self._running.discard(name)

    def run_job_async(self, name: str) -> None:
        threading.Thread(target=self.run_job, args=(name,), daemon=True).start()

    def night_shift(self) -> str:
        """Work through every open task that has an agent assignee, then hand off to the morning brief."""
        queue = [t for t in self.store.list_tasks("open", limit=200) if t["assignee"]]
        done = []
        for task in queue:
            agent = task["assignee"]
            self.store.update_task(task["id"], status="doing")
            prompt = (f"Night-shift assignment (task #{task['id']}, area {task['area']}, due {task['due'] or 'n/a'}):\n"
                      f"{task['title']}\n\nNotes: {task['notes'] or '-'}\n\n"
                      "Do the work fully now. Save the deliverable with `save_note` (title it after the task). "
                      "If the task needs the owner to act, create a clear follow-up task for them. "
                      "Reply with a 2-3 sentence summary of the result.")
            result = self.engine.run(agent, prompt)
            failed = "hit an error" in result or "reasoning core is offline" in result
            self.store.update_task(task["id"], status="todo" if failed else "done", result=result[:4000])
            done.append(f"#{task['id']} {task['title']} ({agent}): {'FAILED' if failed else 'done'}")
        self.bus.publish({"type": "data", "what": "tasks"})
        if not queue:
            return "No assigned tasks in the queue tonight."
        return f"Night shift processed {len(queue)} task(s): " + "; ".join(done)

    # ------------------------------------------------------------ loop
    def tick(self) -> None:
        now = datetime.now(self.settings.tz)
        for job in self.jobs:
            if job.name not in self._running and job.due(now, self.store.get(f"job:{job.name}:last")):
                self.run_job_async(job.name)

    def start(self) -> None:
        if self._thread:
            return

        def loop():
            while not self._stop.wait(30):
                try:
                    self.tick()
                except Exception as exc:  # noqa: BLE001
                    self.bus.log("JARVIS", f"Scheduler error: {exc}", "error")

        self._thread = threading.Thread(target=loop, daemon=True, name="jarvis-scheduler")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
