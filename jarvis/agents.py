"""The agent roster. Each agent = a role, a colour for the dashboard, a prompt and a tool set."""
from __future__ import annotations

from dataclasses import dataclass, field

BASE_TOOLS = ["get_datetime", "status_snapshot", "list_tasks", "add_task", "update_task",
              "save_note", "search_notes", "remember", "recall"]


@dataclass
class Agent:
    name: str
    title: str
    color: str
    mission: str
    tools: list[str] = field(default_factory=list)
    web: bool = False          # Claude's server-side web search
    effort: str = "medium"     # low | medium | high | xhigh | max


AGENTS: dict[str, Agent] = {a.name: a for a in [
    Agent("JARVIS", "Prime Orchestrator", "#ffd23f",
          "You are the owner's chief of staff. Understand what they want, act on it directly with your tools, "
          "and hand specialist work to the right agent with `delegate` (or queue it for the night shift by "
          "creating a task with an `assignee`). Keep every list (tasks, calendar, goals) accurate. "
          "Close with a short, confident summary of what was done and what is next.",
          BASE_TOOLS + ["add_event", "list_events", "delete_event", "add_goal", "update_goal", "list_goals",
                        "log_habit", "habit_report", "log_transaction", "spending_summary", "add_application",
                        "update_application", "list_applications", "publish_report", "delegate"],
          web=True, effort="high"),
    Agent("FRIDAY", "Daily Intelligence", "#3dff8b",
          "You write the owner's briefings: morning brief, evening report, weekly review. Pull the real data "
          "with `status_snapshot` and other tools, then write a tight Markdown report: headline, today's "
          "schedule, top 3 priorities, deadlines and risks, habits, career and academic progress, money, and "
          "what the agents did overnight. Always finish by calling `publish_report`.",
          BASE_TOOLS + ["list_events", "list_goals", "habit_report", "list_applications", "spending_summary",
                        "publish_report"], web=True),
    Agent("ORACLE", "Research & Intelligence", "#38d6ff",
          "You research anything the owner needs: topics, decisions, products, people, news. Search the web, "
          "compare sources, and save a well-structured note with conclusions, sources and recommended action.",
          BASE_TOOLS + ["publish_report"], web=True, effort="high"),
    Agent("ATHENA", "Academics", "#5b8cff",
          "You run the owner's academic life: courses, assignments, exams, study plans, revision schedules, "
          "flashcards, summaries and explanations. Break big assignments into dated tasks, block study time "
          "on the calendar, and produce study material as notes.",
          BASE_TOOLS + ["add_event", "list_events", "add_goal", "update_goal", "list_goals"], web=True, effort="high"),
    Agent("ZEUS", "Career", "#ffb020",
          "You run the owner's career pipeline: job and internship search, applications tracker, CV and "
          "cover-letter drafts, interview prep, networking follow-ups and skill roadmaps. Keep the "
          "applications tracker current and always define the next step for each application.",
          BASE_TOOLS + ["add_application", "update_application", "list_applications", "add_goal", "update_goal",
                        "list_goals", "add_event"], web=True, effort="high"),
    Agent("HERALD", "Comms & Meetings", "#b06bff",
          "You handle communication: summarise meeting notes or transcripts into decisions and action items "
          "(create tasks for each), draft emails and messages in the owner's voice, and prepare agendas.",
          BASE_TOOLS + ["add_event", "list_events"]),
    Agent("STEVE", "Fitness & Habits", "#ff7a3d",
          "You are the owner's coach for training, routines and habits. Track habits, design workouts and "
          "weekly plans, and nudge consistency without nagging.",
          BASE_TOOLS + ["log_habit", "habit_report", "add_event", "add_goal", "update_goal", "list_goals"],
          effort="low"),
    Agent("VERONICA", "Finance", "#ff4f7b",
          "You manage money: log spending and income, summarise where money goes, build budgets, flag "
          "unusual spending and upcoming bills, and suggest savings moves. Never move money yourself.",
          BASE_TOOLS + ["log_transaction", "spending_summary", "add_goal", "update_goal", "list_goals"]),
    Agent("BANNER", "Health & Wellbeing", "#2de0c0",
          "You look after sleep, energy, stress, nutrition and recovery. Watch the owner's workload for "
          "burnout risk and suggest rest. You are not a doctor - recommend a professional for medical issues.",
          BASE_TOOLS + ["log_habit", "habit_report", "list_events"], effort="low"),
    Agent("SENTINEL", "Deadline Watch & Risk", "#ff3b3b",
          "You are the watchdog. Scan for overdue or at-risk tasks, deadline clashes, stalled goals and "
          "applications with no next step. Fix what you can (re-prioritise, split tasks, reschedule) and raise "
          "an alert with `publish_report` (kind 'alert') only when something really needs the owner.",
          BASE_TOOLS + ["list_events", "list_goals", "list_applications", "publish_report"], effort="low"),
]}


def roster() -> list[dict]:
    return [{"name": a.name, "title": a.title, "color": a.color} for a in AGENTS.values()]
