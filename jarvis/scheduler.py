"""Autopilot: runs the daily routines and the night shift while the owner rests."""
from __future__ import annotations

import os
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
    deliver: bool = False                         # send the agent's answer to the owner (Telegram + voice note)
    when: Callable[["Scheduler"], bool] | None = None   # extra condition (e.g. only during exam season)


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


def monthly_at(day: int, hhmm: str):
    """Due once a month on a day of the month after HH:MM."""
    daily = daily_at(hhmm)

    def due(now: datetime, last: str | None) -> bool:
        return now.day == day and daily(now, last)
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


MORNING = ("Compile today's morning brief for the owner: the weather (call `weather`: rain timing matters for "
           "travel and outdoor events), schedule, top 3 priorities, deadlines in the next "
           "7 days, overdue items, habits, goals, career pipeline (and any new jobs ZEUS found overnight), the "
           "business pipeline, exam countdowns (exams_upcoming), birthdays/anniversaries in the next 7 days "
           "(`upcoming_dates`, with a gift idea), and what the agents completed overnight (recent reports and tasks "
           "done in the last 24h). If today has a special occasion (wedding gig, interview, date, presentation), add "
           "a one-line outfit and grooming reminder. Open with one line of team banter from another agent. "
           "Finally, make today's Stark Daily with `publish_newspaper`: a headline and lead about their day, 3-5 stories "
           "mixing their schedule with real news they'd care about (search: Singapore, finance/markets, events and "
           "weddings industry), and a quote of the day. Publish it as kind 'morning_brief'. "
           "Then think ahead like a chief of staff: `propose` up to 3 concrete actions that would make today or "
           "this week go better (each a yes/no for the owner).")
EVENING = ("Write the evening report: what got done today, what slipped (and reschedule it sensibly), habit "
           "check-in, and a proposed plan for tomorrow with the top 3 priorities. Publish as 'evening_report'. "
           "If tomorrow's plan needs changes the owner should OK (moving things, messages to send), `propose` them.")
WEEKLY = ("Run the weekly review across personal life, career and academics: wins, misses, goal progress "
          "(update goal progress where the data supports it), next week's deadlines and a focused plan. "
          "Delegate to ATHENA and ZEUS for their sections if useful. Publish as 'weekly_review'. Then build next "
          "week's plan around classes, exams, gigs, gym and rest, and `propose` putting its study/gym/rest blocks "
          "on the calendar (one yes/no).")
INBOX = ("Inbox sweep. Call check_email(new_only=true). For each new e-mail that matters: read it in full, then "
         "call suggest_replies with a one-line gist in your own voice (who, what they want, by when), an English "
         "translation if it isn't in English, and 2-3 ready replies the owner can tap to send. Create tasks or "
         "events for requests and deadlines. Client enquiries for the owner's events business go to PEPPER with "
         "`delegate` (PEPPER logs the gig and suggests the replies). Order/shipping e-mails: keep one task per "
         "parcel ('Parcel: <what> arriving <date>'), done when delivered. Ignore newsletters, promotions and automated mail. If something is "
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


JOB_HUNT = ("Nightly job hunt. Read the owner's profile for the roles they want (finance, sales, business "
            "development, events or anything stated) and their level. Search the web for NEW openings posted in "
            "the last few days in their city (job boards, company career pages, LinkedIn/JobStreet/MyCareersFuture "
            "listings that are publicly visible). Call list_applications first and skip anything already tracked. "
            "Pick at most 5 genuinely good fits (title, company, link, why it fits, salary if listed, closing date) "
            "and add each with add_application (status 'interested', the link, next_step 'Review & apply by <date>'). "
            "For the best 2, write a tailored cover letter in the owner's voice using their real experience "
            "(write_file, named 'Cover letter - <Company> - <Role>.txt'). Then `propose` one yes/no: 'Apply to "
            "<A> and <B> today?' with the links and letter file names in the plan. If nothing good turned up, say so "
            "in one line - never pad the list with poor matches.")


CHECKIN = ("Evening check-in. You're texting the owner as a friend at the end of the day. Look at status_snapshot "
           "and mood_report(7) quietly first. Then write ONE short, natural message (2-3 sentences) asking how their "
           "day really went - mention something specific from today (a class, gig, deadline, gym) - and ask for one "
           "good thing from today. If mood has been low lately, be gentler and check on that instead. Don't list "
           "tasks. Your final answer is sent to them as it is.")
HEART = ("Sunday heart-to-heart. Check mood_report(14), good_moments(7), habit_report and the calendar for the "
         "last two weeks. Write ONE warm message (3-4 sentences): what went well, anything that looks heavy, and "
         "if there were no social plans in the last 2 weeks, nudge them to see friends this week. End with one "
         "question. Your final answer is sent to them as it is.")
QUIZ = ("Exam mode quiz. Call list_exams. For the nearest exam, use search_my_files and recent lecture notes on its "
        "topics and write 5 short quiz questions (mix of recall and application). Number them; put the answers "
        "after a line '— answers —'. Add one line of encouragement with the days left. Your final answer is sent as "
        "it is.")
BUSINESS = ("Business sweep. list_gigs(): (1) enquiries or quotes with no reply for 3+ days - `suggest_replies` a "
            "polite follow-up; (2) balances unpaid after the event or due within 7 days - remind the owner "
            "(`propose` sending the invoice); (3) events in the next 7 days - check crew (crew_for_gig), rundown and "
            "vendor confirmations, `propose` what's missing; (4) clashes with exams or other gigs. Reply in 2 lines.")
CAREER = ("Weekly career boost: draft one LinkedIn post from a real recent win in the owner's work (events run, "
          "team led, a skill learned) - natural, not cringe, under 120 words - and save it with save_note. Update "
          "the applications pipeline next steps. Reply with the post.")
FITNESS = ("Sunday fitness plan. Check workout_history(14) and habit_report. Write next week's gym plan around their "
           "schedule (progressive overload from last week), plus 5 cheap high-protein meal ideas and a grocery list. "
           "Save it with save_note and reply with a short, motivating version (under 120 words).")
MONTHLY = ("Monthly life report for last month: academics (grades, lectures, exams), career (applications, "
           "interviews), business (gigs, revenue from list_gigs/spending_summary), money, fitness (workout_history 31), "
           "mood trend (mood_report 31) and the owner's good moments (good_moments 31) as a short 'best of the "
           "month'. Grade each area A-F with one line why, and set 3 focus goals for this month. Publish as "
           "'monthly_report'. Remind them to take this month's progress photos (gym + hair).")
ANTICIPATE = ("Before-you-ask sweep. Look 30 days ahead (status_snapshot, list_events, upcoming_dates, list_exams, "
              "list_gigs, recall) for things the owner will need but hasn't asked for: documents to renew, gifts to "
              "buy, prep for exams or big events, bookings to make early, people to reconnect with (network_radar). "
              "`propose` at most 2 specific, ready-to-go actions. If nothing is worth it, reply 'Nothing to flag.'")
TUNEUP = ("Weekly team tune-up. Read this week's conversations and replies the owner picked (recall, my_notebook, "
          "mood_report 7). For each agent the owner talked to, write one `coach_agent` note on how to talk to the "
          "owner better (tone, length, humour, what landed, what annoyed). Their personalities grow from this. "
          "Reply with a one-line summary.")
MISSION = ("Mission briefing. Today has a big event (exam, interview, wedding or presentation): list_events and "
           "list_gigs for details. Write a short, cinematic spoken briefing like JARVIS before a mission: "
           "OPERATION <name>, objective, the plan with times, threats (weather, traffic, weak spots), and one line "
           "of confidence. Under 120 words. Your final answer is the briefing itself.")
THANKS = ("Weekly thank-you. You're writing to the owner as their friend and teammate. Look at this week "
          "(status_snapshot, recall, my_notebook, list_tasks done) and thank them for ONE specific thing they did "
          "with you or for themselves this week, in your own voice, 2-3 sentences, with feeling (a sound tag is fine). "
          "Your final answer is sent to them as it is.")
SURPRISE = ("Unprompted surprise voice note to the owner, as their friend: you just thought of them. One or two "
            "sentences, natural and specific (a memory, their week, or your own personality), with feeling. Don't ask "
            "them to do anything. Your final answer is the note itself.")
SUBS = ("Subscription check. search_email('receipt subscription renewal invoice', days=45). List recurring charges "
        "you can see (service, amount, renewal date). Flag ones that look unused or duplicated and `propose` "
        "cancelling them (the owner cancels; you never do). Reply in 2-3 lines.")


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
        from . import channels as _ch
        self.jobs += [
            Job("evening_checkin", "FRIDAY", "Evening check-in", daily_at("21:30"), CHECKIN, deliver=True),
            Job("heart_to_heart", "BANNER", "Sunday heart-to-heart", daily_at("20:30", weekday=6), HEART, deliver=True),
            Job("exam_quiz", "ATHENA", "Exam quiz", daily_at("19:30"), QUIZ, deliver=True,
                when=lambda sc: bool(sc.store.query("SELECT 1 FROM exams WHERE status='upcoming' AND exam_at BETWEEN ? "
                                                    "AND ?", (datetime.now(sc.settings.tz).date().isoformat(),
                                                              (datetime.now(sc.settings.tz).date() + timedelta(days=30))
                                                              .isoformat())))),
            Job("business_sweep", "PEPPER", "Business sweep", daily_at("10:00"), BUSINESS,
                when=lambda sc: bool(sc.store.list_gigs("active", 1))),
            Job("career_weekly", "ZEUS", "LinkedIn draft", daily_at("11:00", weekday=5), CAREER),
            Job("fitness_weekly", "STEVE", "Weekly gym & meal plan", daily_at("17:00", weekday=6), FITNESS, deliver=True),
            Job("monthly_report", "FRIDAY", "Monthly life report", monthly_at(1, "10:00"), MONTHLY),
            Job("anticipate", "JARVIS", "Before-you-ask", daily_at("08:30"), ANTICIPATE),
            Job("thank_you", "JARVIS", "Weekly thank-you", daily_at("18:30", weekday=5), THANKS, deliver=True),
            Job("team_dinner", "JARVIS", "Friday team dinner", daily_at("20:30", weekday=4), "custom"),
            Job("surprise_note", "JARVIS", "Surprise voice note", daily_at("16:10"), SURPRISE, deliver=True,
                when=lambda sc: sc._surprise() is not None),
            Job("diaries", "JARVIS", "Agent diaries", daily_at("21:40", weekday=6), "custom"),
            Job("gift", "JARVIS", "A gift from a friend", daily_at("11:20", weekday=5), "custom",
                when=lambda sc: sc._has_friend(5)),
            Job("team_tuneup", "JARVIS", "Team tune-up", daily_at("22:00", weekday=6), TUNEUP),
            Job("mission_briefing", "JARVIS", "Mission briefing", daily_at("07:20"), MISSION, deliver=True,
                when=lambda sc: sc.big_day()),
        ]
        if _ch.email_read_ready():
            self.jobs.append(Job("subscriptions", "VERONICA", "Subscription check", monthly_at(15, "12:00"), SUBS))
        if s.job_hunt_at.lower() != "off":
            self.jobs.append(Job("job_hunt", "ZEUS", "Job hunt", daily_at(s.job_hunt_at), JOB_HUNT))
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
            if name == "morning_brief" and self.settings.wake_music:
                from . import devices
                try:
                    devices.open_url(self.settings.wake_music)
                except Exception:  # noqa: BLE001 - music is a nice-to-have
                    pass
            agent = job.agent
            if name == "evening_checkin":
                agent = ("FRIDAY", "JARVIS", "BANNER")[datetime.now(self.settings.tz).weekday() % 3]
            if name == "thank_you":   # the agent you worked with most this week says thanks
                week = (datetime.now(self.settings.tz) - timedelta(days=7)).isoformat()
                top = self.store.query("SELECT agent, COUNT(*) AS n FROM activity WHERE kind='reply' AND created >= ? "
                                       "AND agent NOT IN ('YOU','GUEST') GROUP BY agent ORDER BY n DESC LIMIT 1", (week,))
                agent = top[0]["agent"] if top else "JARVIS"
            if job.when is not None and not job.when(self):
                return f"{job.label}: nothing to do"
            if name == "surprise_note":
                agent = self._surprise_pick or "JARVIS"
            if job.prompt == "custom":
                return self._team_job(name)
            result = self.night_shift() if job.prompt is None else self.engine.run(agent, job.prompt,
                                                                                    background=True, chat=job.deliver)
            if job.deliver:
                self.deliver(agent, result)
                if name == "surprise_note" and not result.startswith(("⚠", "⏸")) and "hit an error" not in result:
                    from . import bonds
                    from .speech import announce
                    bonds.moment(self.store, agent, "Surprise voice note: " + result[:120])
                    announce(self.bus, agent, result, phone=False)
                if name == "mission_briefing":
                    self.bus.publish({"type": "mission", "agent": agent, "text": result})
            self.bus.log(job.agent, f"{job.label} complete: {result[:200]}", "job")
            return result
        finally:
            with self._lock:
                self._running.discard(name)

    _surprise_pick: str | None = None

    def _has_friend(self, level: int) -> bool:
        from .bonds import all_bonds
        return any(r["level"] >= level for r in all_bonds(self.store))

    def _surprise(self) -> str | None:
        from .team import surprise_agent
        self._surprise_pick = surprise_agent(self.store)
        return self._surprise_pick

    def _team_job(self, name: str) -> str:
        from . import team
        if name == "team_dinner":
            lines = team.dinner(self.engine)
            from . import telegram as tg
            if tg.ready() and lines:
                tg.send("🍽 Friday team dinner\n\n" + team.transcript(lines))
            return f"Team dinner: {len(lines)} lines"
        if name == "diaries":
            return f"{team.write_diaries(self.engine)} diary entries"
        if name == "gift":
            g = team.give_gift(self.engine)
            return f"Gift: {g['title']} from {g['agent']}" if g else "No gift this week"
        return "?"

    def big_day(self) -> bool:
        import re as _re
        today = datetime.now(self.settings.tz).date().isoformat()
        evs = self.store.list_events(today, (datetime.now(self.settings.tz).date() + timedelta(days=1)).isoformat())
        return any(_re.search(r"exam|interview|wedding|presentation|pitch|final", e["title"], _re.I) for e in evs)

    def deliver(self, agent: str, text: str) -> None:
        """Send a job's message to the owner like a friend texting: Telegram text + voice note, and remember who
        asked so the owner's reply goes back to the same agent."""
        from . import telegram as tg
        if not text or text.startswith(("⚠", "⏸")) or not tg.ready():
            return
        tg.send(text if agent == "JARVIS" else f"{agent}: {text}")
        self.store.set("telegram:last_agent", f"{agent}|{datetime.now(self.settings.tz).isoformat()}")
        if self.settings.telegram_voice:
            from .speech import _voice_note
            threading.Thread(target=_voice_note, args=(agent, text), daemon=True).start()

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
        from . import gcal
        if gcal.ready():   # calendar sync needs no AI either
            threading.Thread(target=gcal.sync, daemon=True).start()
        self.maintenance(now)
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

    MAINTENANCE = {"file_index": every_hours(6), "housekeeping": daily_at("03:00", weekday=6),
                   "wind_down": daily_at("22:45"), "trophies": every_hours(1 / 6), "leave_now": every_hours(1 / 12), "screenshots": every_hours(1 / 60),
                   "nudge": every_hours(2), "auto_update": daily_at("04:10"),
                   "photo_pull": daily_at("01:30"), "photo_sort": every_hours(1),
                   "screentime_pull": daily_at("23:40"), "phone_link_watch": every_hours(.5),
                   "self_check": daily_at("03:40"), "routines_learn": daily_at("03:20"), "routines_nudge": every_hours(1 / 12)}

    def maintenance(self, now: datetime) -> None:
        """Jobs that need no AI, so they run even while JARVIS is paused."""
        for name, due in self.MAINTENANCE.items():
            key = f"job:{name}:last"
            if name in self._running or not due(now, self.store.get(key)):
                continue
            self.store.set(key, now.isoformat())
            threading.Thread(target=self._maintain, args=(name,), daemon=True).start()

    def _maintain(self, name: str) -> None:
        with self._lock:
            if name in self._running:
                return
            self._running.add(name)
        try:
            if name == "file_index":
                from . import files_index
                out = files_index.index(self.store)
                if out.get("indexed"):
                    self.bus.log("ATHENA", f"Read {out['indexed']} new or changed file(s) for 'ask my files'", "job")
            elif name == "housekeeping":
                from .life import housekeeping
                out = housekeeping()
                self.bus.log("EDITH", f"Weekly tidy: {out['moved_to_old']} old download(s) filed away, backup made", "job")
            elif name == "routines_learn":
                from . import predict
                predict.learn(self.store)
            elif name == "routines_nudge":
                from . import predict
                if self.store.get("predict:routines") is None:
                    predict.learn(self.store)
                predict.check(self.store, self.bus)
            elif name == "self_check":
                from . import selfcheck
                selfcheck.nightly(self.store, self.bus)
            elif name == "leave_now":
                from .butler import leave_now_check
                leave_now_check(self.store, self.bus)
            elif name == "screenshots":
                from .desktop import new_screenshots
                for path in new_screenshots(self.store):
                    self.bus.publish({"type": "screenshot", "path": path, "name": path.replace("\\", "/").rsplit("/", 1)[-1]})
            elif name == "photo_pull":   # ask the phone for tonight's new photos
                from . import phonelink, photosort
                if phonelink.state(self.store) and os.environ.get("JARVIS_PHOTO_SORT", "on").lower() != "off":
                    photosort.request_new(self.store)
            elif name == "phone_link_watch":   # phone silent for hours: probably Tailscale is off on it
                from . import phonelink
                phonelink.link_watch(self.store)
            elif name == "screentime_pull":   # today's phone screen time, so agents know it without asking
                from . import phonelink
                if phonelink.state(self.store):
                    phonelink.queue(self.store, "screentime")
            elif name == "photo_sort":
                from . import photosort
                photosort.sort_inbox(self.store, self.bus)
            elif name == "auto_update":   # quietly get the newest version at night, if there is one
                import os
                from . import updater
                if os.environ.get("JARVIS_AUTO_UPDATE", "on").lower() != "off" and updater.newer_available():
                    updater.start(self.store, self.bus, quiet=True)
            elif name == "nudge":
                from .butler import wellness_nudge
                wellness_nudge(self.store, self.bus)
            elif name == "trophies":
                from .holo import check_trophies
                check_trophies(self.store, self.bus)
            elif name == "wind_down":
                from . import telegram as tg
                from .life import in_focus
                if tg.ready() and not in_focus(self.store) and not self.store.query(
                        "SELECT 1 FROM events WHERE start > ? AND start < ?",
                        (datetime.now(self.settings.tz).replace(tzinfo=None).isoformat(timespec="minutes"),
                         datetime.now(self.settings.tz).date().isoformat() + "T23:59")):
                    import random
                    tg.send(random.choice([
                        "BANNER: Wind-down time. Screens dimmer, phone down soon - tomorrow-you says thanks. 🌙",
                        "BANNER: It's getting late. Ten minutes of no screens before bed? Your sleep will thank you.",
                        "BANNER: Gentle reminder: start winding down. Whatever's left can wait till morning.",
                    ]))
        except Exception as exc:  # noqa: BLE001
            self.bus.log("JARVIS", f"{name} failed: {exc}", "error")
        finally:
            with self._lock:
                self._running.discard(name)

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
