"""Control of the laptop JARVIS runs on, and (optionally) an Android phone over ADB."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import webbrowser
from datetime import datetime
from pathlib import Path

from .config import ROOT

SYSTEM = platform.system()  # 'Darwin' (Mac) | 'Windows' | 'Linux'
HOME = Path.home()
WORKSPACE = Path(os.environ.get("JARVIS_WORKSPACE", HOME / "JARVIS"))
SHOTS = ROOT / "data" / "screenshots"


# ---------------------------------------------------------------- laptop
def status() -> dict:
    total, used, free = shutil.disk_usage(HOME)
    info = {"os": f"{SYSTEM} {platform.release()}", "machine": platform.node(),
            "disk_free_gb": round(free / 1e9, 1), "disk_used_pct": round(used / total * 100)}
    try:
        import psutil
        info["cpu_pct"] = psutil.cpu_percent(interval=0.5)
        info["ram_used_pct"] = psutil.virtual_memory().percent
        bat = psutil.sensors_battery()
        if bat:
            info["battery_pct"] = round(bat.percent)
            info["charging"] = bool(bat.power_plugged)
    except Exception:  # noqa: BLE001 - psutil optional
        pass
    return info


def open_url(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    webbrowser.open(url)
    return f"opened {url}"


def open_app(name: str) -> str:
    if SYSTEM == "Darwin":
        subprocess.run(["open", "-a", name], check=True, timeout=20)
    elif SYSTEM == "Windows":
        subprocess.run(["cmd", "/c", "start", "", name], check=True, timeout=20)
    else:
        subprocess.Popen([name], start_new_session=True)
    return f"opened {name}"


def screenshot() -> str:
    SHOTS.mkdir(parents=True, exist_ok=True)
    path = SHOTS / f"screen-{datetime.now():%Y%m%d-%H%M%S}.png"
    if SYSTEM == "Darwin":
        subprocess.run(["screencapture", "-x", str(path)], check=True, timeout=20)
    else:
        from PIL import ImageGrab  # pillow
        ImageGrab.grab().save(path)
    return str(path)


def lock_screen() -> str:
    if SYSTEM == "Darwin":
        subprocess.run(["pmset", "displaysleepnow"], check=True, timeout=10)
    elif SYSTEM == "Windows":
        subprocess.run(["rundll32.exe", "user32.dll,LockWorkStation"], check=True, timeout=10)
    else:
        subprocess.run(["loginctl", "lock-session"], check=True, timeout=10)
    return "screen locked"


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def inside_home(path: Path) -> bool:
    return _inside(path, HOME)


def find_files(query: str, folder: str = "", limit: int = 30) -> list[str]:
    base = (HOME / folder).expanduser() if folder else HOME
    if not _inside(base, HOME):
        raise ValueError("Only folders inside your home folder can be searched")
    q, hits, seen = query.lower(), [], 0
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in
                       {"node_modules", "Library", "AppData", "__pycache__", ".venv"}]
        for f in filenames:
            seen += 1
            if q in f.lower():
                hits.append(str(Path(dirpath) / f))
                if len(hits) >= limit:
                    return hits
        if seen > 200_000:
            break
    return hits


def read_file(path: str, max_chars: int = 20000) -> str:
    p = Path(path).expanduser()
    if not _inside(p, HOME):
        raise ValueError("Only files inside your home folder can be read")
    if p.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader
            return "\n".join((pg.extract_text() or "") for pg in PdfReader(str(p)).pages)[:max_chars]
        except ImportError:
            raise ValueError("Install pypdf to read PDFs: pip install pypdf") from None
    return p.read_text(encoding="utf-8", errors="replace")[:max_chars]


def write_file(name: str, content: str) -> str:
    """Agents may only create files inside the JARVIS workspace folder (~/JARVIS)."""
    p = (WORKSPACE / name).expanduser()
    if not _inside(p, WORKSPACE):
        raise ValueError("Files can only be written inside the JARVIS workspace folder")
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return str(p)


def run_command(command: str, timeout: int = 120) -> str:
    """Only ever called after the owner approved the command."""
    if SYSTEM == "Windows":   # PowerShell: what agents write, and it understands most old cmd commands too
        args = ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", command]
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout, cwd=HOME,
                              creationflags=0x08000000)   # no console window popping up
    else:
        proc = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=timeout, cwd=HOME)
    out = (proc.stdout + ("\n" + proc.stderr if proc.stderr else "")).strip()
    return f"exit code {proc.returncode}\n{out[-4000:]}"


# ---------------------------------------------------------------- Android phone (ADB over Wi-Fi)
def adb_path() -> str | None:
    """ADB from JARVIS_ADB (e.g. C:\\platform-tools\\adb.exe) or from PATH."""
    custom = os.environ.get("JARVIS_ADB", "").strip()
    return custom if custom and Path(custom).exists() else shutil.which("adb")


def _adb(*args: str, timeout: int = 20, binary: bool = False):
    adb = adb_path()
    if not adb:
        raise RuntimeError("ADB is not installed - see README 'Phone control'")
    target = ["-s", settings_phone()] if settings_phone() else []
    proc = subprocess.run([adb, *target, *args], capture_output=True, timeout=timeout, text=not binary)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or b"").strip() if not binary else "adb command failed")
    return proc.stdout


def settings_phone() -> str:
    return os.environ.get("JARVIS_PHONE_ADB", "").strip()


def phone_ready() -> bool:
    return bool(settings_phone()) and adb_path() is not None


def phone_connect() -> str:
    adb = adb_path()
    if not adb or not settings_phone():
        raise RuntimeError("Set JARVIS_PHONE_ADB=<phone-ip>:<port> and install ADB")
    return subprocess.run([adb, "connect", settings_phone()], capture_output=True, text=True, timeout=15).stdout


def phone_status() -> dict:
    phone_connect()
    raw = _adb("shell", "dumpsys", "battery")
    info = {}
    for line in raw.splitlines():
        k, _, v = line.strip().partition(":")
        if k in ("level", "AC powered", "USB powered", "temperature"):
            info[k] = v.strip()
    info["model"] = _adb("shell", "getprop", "ro.product.model").strip()
    return info


def phone_open_url(url: str) -> str:
    phone_connect()
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    _adb("shell", "am", "start", "-a", "android.intent.action.VIEW", "-d", url)
    return f"opened {url} on phone"


def phone_open_app(package: str) -> str:
    phone_connect()
    _adb("shell", "monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1")
    return f"launched {package} on phone"


def phone_screenshot() -> str:
    phone_connect()
    SHOTS.mkdir(parents=True, exist_ok=True)
    path = SHOTS / f"phone-{datetime.now():%Y%m%d-%H%M%S}.png"
    path.write_bytes(_adb("exec-out", "screencap", "-p", binary=True))
    return str(path)


def phone_apps(query: str = "") -> list[str]:
    phone_connect()
    pkgs = [ln.replace("package:", "").strip() for ln in _adb("shell", "pm", "list", "packages", "-3").splitlines()]
    return [p for p in pkgs if query.lower() in p.lower()][:50]
