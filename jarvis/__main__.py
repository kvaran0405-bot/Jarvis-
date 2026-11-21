"""Command line: python -m jarvis [serve | ask | job | agents]"""
from __future__ import annotations

import argparse
import sys
import webbrowser


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="jarvis", description="JARVIS OS - your personal multi-agent system")
    sub = p.add_subparsers(dest="cmd")

    s = sub.add_parser("serve", help="start the command centre + autopilot (default)")
    s.add_argument("--open", action="store_true", help="open the dashboard in a browser")

    a = sub.add_parser("ask", help="give an order to an agent from the terminal")
    a.add_argument("text", nargs="+")
    a.add_argument("--agent", default="JARVIS")

    j = sub.add_parser("job", help="run a scheduled job now")
    j.add_argument("name", choices=["morning_brief", "evening_report", "weekly_review", "deadline_watch",
                                    "night_shift", "inbox_sweep"])

    sub.add_parser("agents", help="list the agents")

    args = p.parse_args(argv)
    cmd = args.cmd or "serve"

    if cmd == "serve":
        import uvicorn
        from .config import settings
        url = f"http://{settings.host}:{settings.port}/command-centre.html?autostart=true"
        print(f"JARVIS OS online -> {url}")
        if getattr(args, "open", False):
            webbrowser.open(url)
        uvicorn.run("jarvis.server:app", host=settings.host, port=settings.port, log_level="warning")
        return 0

    from .server import engine, scheduler  # builds store/bus/engine without starting HTTP

    if cmd == "agents":
        from .agents import AGENTS
        for agent in AGENTS.values():
            print(f"{agent.name:<9} {agent.title}")
    elif cmd == "ask":
        print(engine.run(args.agent, " ".join(args.text)))
    elif cmd == "job":
        print(scheduler.run_job(args.name))
    return 0


if __name__ == "__main__":
    sys.exit(main())
