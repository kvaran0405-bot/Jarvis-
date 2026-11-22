"""Command line: python -m jarvis [serve | ask | job | agents]"""
from __future__ import annotations

import argparse
import sys
import webbrowser


def open_jarvis_window(url: str) -> bool:
    """The always-on JARVIS window: its own Edge/Chrome app window (no tabs or address bar), allowed to speak
    without a click, with its own profile so the microphone permission is remembered. False if no browser found."""
    import os
    import shutil
    import subprocess
    from pathlib import Path
    from .config import ROOT
    candidates = [shutil.which(n) for n in ("msedge", "chrome", "google-chrome", "chromium", "chromium-browser")]
    for base in (os.environ.get("PROGRAMFILES(X86)", ""), os.environ.get("PROGRAMFILES", ""),
                 os.environ.get("LOCALAPPDATA", "")):
        if base:
            candidates += [str(Path(base) / "Microsoft/Edge/Application/msedge.exe"),
                           str(Path(base) / "Google/Chrome/Application/chrome.exe")]
    exe = next((c for c in candidates if c and Path(c).exists()), None)
    if not exe:
        return False
    profile = ROOT / "data" / "jarvis-window"
    profile.mkdir(parents=True, exist_ok=True)
    subprocess.Popen([exe, f"--app={url}", f"--user-data-dir={profile}", "--autoplay-policy=no-user-gesture-required",
                      "--no-first-run", "--window-size=1440,900"])
    return True


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
                                    "night_shift", "inbox_sweep", "money_weekly"])

    sub.add_parser("agents", help="list the agents")

    args = p.parse_args(argv)
    cmd = args.cmd or "serve"

    if cmd == "serve":
        import uvicorn
        from .config import settings
        url = f"http://{settings.host}:{settings.port}/command-centre.html?autostart=true"
        import os
        from .config import ROOT
        (ROOT / "data").mkdir(exist_ok=True)
        (ROOT / "data" / "jarvis.pid").write_text(str(os.getpid()))   # lets update.bat restart JARVIS
        print(f"JARVIS OS online -> {url}")
        if getattr(args, "open", False):  # open the browser once the server is actually up
            import threading
            import time
            import urllib.request

            def open_when_ready():
                for _ in range(60):
                    try:
                        urllib.request.urlopen(f"http://{settings.host}:{settings.port}/api/agents", timeout=1)
                        if not open_jarvis_window(f"http://127.0.0.1:{settings.port}/command-centre.html?kiosk=1"):
                            webbrowser.open(url)
                        return
                    except Exception:  # noqa: BLE001 - not up yet
                        time.sleep(0.5)
            threading.Thread(target=open_when_ready, daemon=True).start()
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
