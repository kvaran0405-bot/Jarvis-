"""Laptop command (Phase 4): windows, media keys, volume, brightness, saved workspaces, file chores, real Office
files (PowerPoint, Excel) and looking at the screen. Window and media control use Windows' own APIs (ctypes);
on other systems those tools explain they're Windows-only."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from . import devices
from .guard import REFUSAL, blocked
from .tools import I, S, ToolContext, tool

B = {"type": "boolean"}
WIN = devices.SYSTEM == "Windows"


# ================================================================== Windows plumbing
def _user32():
    import ctypes
    return ctypes.windll.user32


def windows() -> list[dict]:
    """Visible top-level windows: [{hwnd, title}]."""
    if not WIN:
        return []
    import ctypes
    from ctypes import wintypes
    u = _user32()
    out = []
    proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def cb(hwnd, _):
        if u.IsWindowVisible(hwnd):
            n = u.GetWindowTextLengthW(hwnd)
            if n:
                buf = ctypes.create_unicode_buffer(n + 1)
                u.GetWindowTextW(hwnd, buf, n + 1)
                t = buf.value.strip()
                if t and t not in ("Program Manager", "Settings", "Windows Input Experience"):
                    out.append({"hwnd": hwnd, "title": t})
        return True
    u.EnumWindows(proc(cb), 0)
    return out


def foreground_title() -> str:
    if not WIN:
        return ""
    import ctypes
    u = _user32()
    h = u.GetForegroundWindow()
    n = u.GetWindowTextLengthW(h)
    buf = ctypes.create_unicode_buffer(n + 1)
    u.GetWindowTextW(h, buf, n + 1)
    return buf.value


def _find(title: str) -> dict | None:
    t = title.lower().strip()
    ws = windows()
    return next((w for w in ws if w["title"].lower() == t), None) or next((w for w in ws if t in w["title"].lower()), None)


def _press(vk: int, times: int = 1) -> None:
    u = _user32()
    for _ in range(max(1, times)):
        u.keybd_event(vk, 0, 0, 0)
        u.keybd_event(vk, 0, 2, 0)


def _not_windows() -> dict:
    return {"error": "Window and media control works on the Windows laptop only."}


# ================================================================== windows & media
@tool("list_windows", "The windows open on the laptop right now (titles).")
def list_windows(ctx: ToolContext) -> dict:
    if not WIN:
        return _not_windows()
    return {"windows": [w["title"] for w in windows()][:40], "active": foreground_title()}


@tool("window_action", "Control a laptop window by (part of) its title: focus | close | minimize | maximize. "
      "Closing asks the app to close normally (unsaved work prompts still appear).",
      {"title": S, "action": {"type": "string", "enum": ["focus", "close", "minimize", "maximize"]}}, ["title", "action"])
def window_action(ctx: ToolContext, title: str, action: str) -> dict:
    if not WIN:
        return _not_windows()
    w = _find(title)
    if not w:
        return {"error": f"No open window matches '{title}'.", "open": [x["title"] for x in windows()][:20]}
    u = _user32()
    if action == "focus":
        u.ShowWindow(w["hwnd"], 9)
        u.SetForegroundWindow(w["hwnd"])
    elif action == "close":
        u.PostMessageW(w["hwnd"], 0x0010, 0, 0)
    elif action == "minimize":
        u.ShowWindow(w["hwnd"], 6)
    elif action == "maximize":
        u.ShowWindow(w["hwnd"], 3)
    return {"done": action, "window": w["title"]}


@tool("snap_windows", "Put two windows side by side (left and right halves of the screen), e.g. notes and a lecture.",
      {"left": S, "right": S}, ["left", "right"])
def snap_windows(ctx: ToolContext, left: str, right: str) -> dict:
    if not WIN:
        return _not_windows()
    import ctypes
    from ctypes import wintypes
    u = _user32()
    rect = wintypes.RECT()
    u.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)   # SPI_GETWORKAREA
    w, h = rect.right - rect.left, rect.bottom - rect.top
    done = []
    for title, x in ((left, rect.left), (right, rect.left + w // 2)):
        win = _find(title)
        if win:
            u.ShowWindow(win["hwnd"], 9)
            u.MoveWindow(win["hwnd"], x, rect.top, w // 2, h, True)
            done.append(win["title"])
    return {"snapped": done} if done else {"error": "Couldn't find those windows."}


@tool("show_desktop", "Minimize every window (show the desktop).")
def show_desktop(ctx: ToolContext) -> dict:
    if not WIN:
        return _not_windows()
    u = _user32()
    u.keybd_event(0x5B, 0, 0, 0)
    _press(0x44)
    u.keybd_event(0x5B, 0, 2, 0)
    return {"done": True}


MEDIA = {"play": 0xB3, "pause": 0xB3, "play_pause": 0xB3, "next": 0xB0, "previous": 0xB1, "stop": 0xB2, "mute": 0xAD}


@tool("media_control", "Control music and video on the laptop: play_pause | next | previous | stop | mute | "
      "volume_up | volume_down (steps = how many notches, 2% each).",
      {"action": {"type": "string", "enum": ["play_pause", "next", "previous", "stop", "mute", "volume_up", "volume_down"]},
       "steps": I}, ["action"])
def media_control(ctx: ToolContext, action: str, steps: int = 5) -> dict:
    if not WIN:
        return _not_windows()
    if action == "volume_up":
        _press(0xAF, steps)
    elif action == "volume_down":
        _press(0xAE, steps)
    else:
        _press(MEDIA[action])
    return {"done": action}


@tool("set_brightness", "Set the laptop screen brightness (0-100).", {"level": I}, ["level"])
def set_brightness(ctx: ToolContext, level: int) -> dict:
    if not WIN:
        return _not_windows()
    level = max(0, min(100, int(level)))
    cmd = f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,{level})"
    r = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, timeout=20)
    return {"brightness": level} if r.returncode == 0 else {"error": "This screen doesn't allow brightness control from apps."}


# ================================================================== workspaces
def _workspaces(store) -> dict:
    try:
        return json.loads(store.get("desk:workspaces") or "{}")
    except ValueError:
        return {}


@tool("save_workspace", "Save a named laptop setup to open in one go later, e.g. 'exam mode' = notes folder + lecture "
      "slides + a focus playlist. items: websites (https://...), apps (e.g. 'notepad', 'spotify') or files/folders.",
      {"name": S, "items": {"type": "array", "items": S}}, ["name", "items"])
def save_workspace(ctx: ToolContext, name: str, items: list) -> dict:
    if any(blocked(i) for i in items):
        return {"error": REFUSAL}
    ws = _workspaces(ctx.store)
    ws[name.strip().lower()] = [str(i) for i in items][:12]
    ctx.store.set("desk:workspaces", json.dumps(ws))
    return {"saved": name, "items": ws[name.strip().lower()], "all": list(ws)}


@tool("open_workspace", "Open a saved laptop setup by name (everything in it at once). No name = list them.", {"name": S})
def open_workspace(ctx: ToolContext, name: str = "") -> dict:
    ws = _workspaces(ctx.store)
    if not name:
        return {"workspaces": ws}
    items = ws.get(name.strip().lower())
    if items is None:
        return {"error": f"No workspace called '{name}'.", "workspaces": list(ws)}
    opened = []
    for it in items:
        try:
            if it.startswith(("http://", "https://")) or re.match(r"^[\w.-]+\.(com|sg|org|net|io|edu)(/|$)", it):
                devices.open_url(it)
            elif _home_path(it).exists():
                p = _home_path(it)
                if not devices._inside(p, devices.HOME):
                    continue
                os.startfile(str(p)) if WIN else subprocess.Popen(["xdg-open", str(p)])  # noqa: S606
            else:
                devices.open_app(it)
            opened.append(it)
        except Exception as exc:  # noqa: BLE001
            opened.append(f"{it} (failed: {exc})")
    return {"opened": opened}


# ================================================================== file chores (preview first, then the owner's yes)
FOLDERS = {"Documents": {".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".pages", ".md"},
           "Slides": {".ppt", ".pptx", ".key"}, "Spreadsheets": {".xls", ".xlsx", ".csv", ".numbers"},
           "Images": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".bmp", ".svg"},
           "Videos": {".mp4", ".mov", ".avi", ".mkv", ".webm"}, "Audio": {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"},
           "Archives": {".zip", ".rar", ".7z", ".tar", ".gz"}, "Installers": {".exe", ".msi", ".dmg", ".pkg", ".apk"}}


def _home_path(path: str) -> Path:
    path = (path or "").strip()
    if path.startswith("~"):
        return devices.HOME / path[1:].lstrip("/\\")
    return Path(path)


def _folder(path: str) -> Path:
    p = _home_path(path or "~/Downloads")
    if not p.is_absolute():
        p = devices.HOME / p
    if not devices._inside(p, devices.HOME) or not p.is_dir():
        raise ValueError("Only existing folders inside your home folder")
    if blocked(str(p)):
        raise ValueError(REFUSAL)
    return p


def _needs_yes(ctx: ToolContext, preview: dict, what: str) -> dict:
    return {**preview, "status": "preview only - nothing changed yet",
            "next": f"Show the owner this preview and `propose` it ('{what}'). It runs for real once they say yes."}


@tool("organise_folder", "Sort a folder's loose files into subfolders by type (Documents, Slides, Spreadsheets, Images, "
      "Videos, Audio, Archives, Installers). Nothing is deleted. Shows a preview first; it only moves files as part of "
      "a plan the owner approved.", {"folder": S}, ["folder"])
def organise_folder(ctx: ToolContext, folder: str) -> dict:
    try:
        p = _folder(folder)
    except ValueError as exc:
        return {"error": str(exc)}
    moves = []
    for f in p.iterdir():
        if f.is_file() and not f.name.startswith((".", "~$")) and not f.name.endswith((".crdownload", ".part")):
            dest = next((k for k, exts in FOLDERS.items() if f.suffix.lower() in exts), None)
            if dest:
                moves.append((f, p / dest / f.name))
    preview = {"folder": str(p), "moves": len(moves), "examples": [f"{a.name} -> {b.parent.name}/" for a, b in moves[:15]]}
    if not ctx.approved:
        return _needs_yes(ctx, preview, f"Tidy {p.name}: sort {len(moves)} files into folders")
    done = 0
    for a, b in moves:
        b.parent.mkdir(exist_ok=True)
        if not b.exists():
            shutil.move(str(a), str(b))
            done += 1
    return {**preview, "moved": done}


@tool("rename_files", "Rename many files in a folder at once: replace text in their names (find -> replace), optionally "
      "only files containing 'match'. Shows a preview first; renames only as part of a plan the owner approved.",
      {"folder": S, "find": S, "replace": S, "match": S}, ["folder", "find"])
def rename_files(ctx: ToolContext, folder: str, find: str, replace: str = "", match: str = "") -> dict:
    try:
        p = _folder(folder)
    except ValueError as exc:
        return {"error": str(exc)}
    pairs = []
    for f in sorted(p.iterdir()):
        if f.is_file() and find in f.name and (not match or match.lower() in f.name.lower()):
            new = f.name.replace(find, replace).strip()
            if new and new != f.name and not (p / new).exists():
                pairs.append((f, p / new))
    preview = {"folder": str(p), "renames": len(pairs), "examples": [f"{a.name} -> {b.name}" for a, b in pairs[:15]]}
    if not ctx.approved:
        return _needs_yes(ctx, preview, f"Rename {len(pairs)} files in {p.name}")
    for a, b in pairs:
        a.rename(b)
    return {**preview, "renamed": len(pairs)}


# ================================================================== real Office files
@tool("make_slides", "Make a real PowerPoint (.pptx) deck from content, e.g. from lecture notes or a pitch. "
      "slides: [{title, bullets: [..], notes}]. Saved in ~/JARVIS/Slides and sent to the owner's phone.",
      {"title": S, "subtitle": S, "slides": {"type": "array", "items": {"type": "object", "properties": {
          "title": S, "bullets": {"type": "array", "items": S}, "notes": S}, "required": ["title"]}},
       "send_to_phone": B}, ["title", "slides"])
def make_slides(ctx: ToolContext, title: str, slides: list, subtitle: str = "", send_to_phone: bool = True) -> dict:
    try:
        from pptx import Presentation
        from pptx.dml.color import RGBColor
        from pptx.util import Pt
    except ImportError:
        return {"error": "PowerPoint support isn't installed yet (it comes with the next JARVIS update)."}
    prs = Presentation()
    dark, gold, light = RGBColor(0x0C, 0x10, 0x16), RGBColor(0xFF, 0xC4, 0x3D), RGBColor(0xE6, 0xEC, 0xF2)

    def paint(slide):
        bg = slide.background.fill
        bg.solid()
        bg.fore_color.rgb = dark
    s0 = prs.slides.add_slide(prs.slide_layouts[0])
    paint(s0)
    s0.shapes.title.text = title
    s0.shapes.title.text_frame.paragraphs[0].runs[0].font.color.rgb = gold
    if len(s0.placeholders) > 1:
        s0.placeholders[1].text = subtitle or ctx.now().strftime("%d %B %Y")
        s0.placeholders[1].text_frame.paragraphs[0].runs[0].font.color.rgb = light
    for sd in slides[:40]:
        s = prs.slides.add_slide(prs.slide_layouts[1])
        paint(s)
        s.shapes.title.text = sd["title"]
        s.shapes.title.text_frame.paragraphs[0].runs[0].font.color.rgb = gold
        body = s.placeholders[1].text_frame
        body.clear()
        for i, b in enumerate(sd.get("bullets") or []):
            para = body.paragraphs[0] if i == 0 else body.add_paragraph()
            para.text = str(b)
            for r in para.runs:
                r.font.color.rgb = light
                r.font.size = Pt(22)
        if sd.get("notes"):
            s.notes_slide.notes_text_frame.text = sd["notes"]
    safe = re.sub(r"[^A-Za-z0-9 _-]+", "", title).strip()[:50] or "Deck"
    path = devices.WORKSPACE / "Slides" / f"{safe}.pptx"
    path.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(path))
    return {"pptx": str(path), "slides": len(slides) + 1, **_to_phone(path, send_to_phone, f"🖥 {title} ({len(slides) + 1} slides)")}


def _cell(v):
    """Numbers written as text ("12.50", "1,200") become real numbers, so totals and charts work."""
    if isinstance(v, str):
        t = v.strip().replace(",", "")
        try:
            return int(t) if t.lstrip("-").isdigit() else float(t)
        except ValueError:
            return v
    return v


@tool("make_spreadsheet", "Make a real Excel (.xlsx) file: sheets: [{name, columns: [..], rows: [[..]], "
      "totals: [column names to total]}]. Formulas like '=B2*C2' work in cells. Saved in ~/JARVIS/Sheets.",
      {"name": S, "sheets": {"type": "array", "items": {"type": "object", "properties": {
          "name": S, "columns": {"type": "array", "items": S}, "rows": {"type": "array", "items": {"type": "array", "items": {"type": "string"}}},
          "totals": {"type": "array", "items": S}}, "required": ["name", "columns", "rows"]}}, "send_to_phone": B},
      ["name", "sheets"])
def make_spreadsheet(ctx: ToolContext, name: str, sheets: list, send_to_phone: bool = True) -> dict:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError:
        return {"error": "Excel support isn't installed yet (it comes with the next JARVIS update)."}
    wb = Workbook()
    wb.remove(wb.active)
    for sh in sheets[:10]:
        ws = wb.create_sheet(str(sh["name"])[:30] or "Sheet")
        cols = [str(c) for c in sh["columns"]]
        ws.append(cols)
        for c in ws[1]:
            c.font = Font(bold=True, color="FFFFFF")
            c.fill = PatternFill("solid", fgColor="1A2A3A")
        for r in sh["rows"][:5000]:
            ws.append([_cell(v) for v in r])
        n = len(sh["rows"]) + 1
        if sh.get("totals") and n > 1:
            row = ["TOTAL"] + [""] * (len(cols) - 1)
            for t in sh["totals"]:
                if t in cols:
                    L = get_column_letter(cols.index(t) + 1)
                    row[cols.index(t)] = f"=SUM({L}2:{L}{n})"
            ws.append(row)
            for c in ws[ws.max_row]:
                c.font = Font(bold=True)
        for i, c in enumerate(cols, start=1):
            ws.column_dimensions[get_column_letter(i)].width = max(10, min(45, len(c) + 4))
        ws.freeze_panes = "A2"
    safe = re.sub(r"[^A-Za-z0-9 _-]+", "", name).strip()[:50] or "Sheet"
    path = devices.WORKSPACE / "Sheets" / f"{safe}.xlsx"
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(path))
    return {"xlsx": str(path), **_to_phone(path, send_to_phone, f"📊 {name}")}


def _to_phone(path: Path, send: bool, caption: str) -> dict:
    if not send:
        return {}
    from . import telegram as tg
    if tg.ready():
        try:
            tg.send_file(str(path), caption=caption)
            return {"phone": "sent"}
        except Exception as exc:  # noqa: BLE001
            return {"phone": f"not sent: {exc}"}
    return {}


# ================================================================== screen awareness
@tool("look_at_screen", "Look at the laptop screen right now and answer about it: 'what's this error?', 'summarise "
      "this page', 'reply to this email', 'what am I looking at?'. Never used on banking screens.",
      {"question": S}, ["question"])
def look_at_screen(ctx: ToolContext, question: str) -> dict:
    title = foreground_title()
    if blocked(title):
        return {"error": REFUSAL}
    from . import vision
    try:
        path = devices.screenshot()
    except Exception as exc:  # noqa: BLE001
        return {"error": f"Couldn't capture the screen: {exc}"}
    try:
        answer = vision.describe(path, f"This is the owner's laptop screen (active window: {title or 'unknown'}). "
                                       f"Their question: {question}")
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}
    finally:
        try:
            Path(path).unlink()
        except OSError:
            pass
    if "private document" in answer.lower()[:80]:
        return {"error": "That screen shows something private, so I've ignored it."}
    return {"active_window": title, "what_i_see": answer}


# ================================================================== new screenshots (no AI: just offers help)
def screenshot_folders() -> list[Path]:
    h = devices.HOME
    return [p for p in (h / "Pictures" / "Screenshots", h / "OneDrive" / "Pictures" / "Screenshots",
                        h / "OneDrive" / "Pictures" / "Screenshots 1", h / "Desktop") if p.exists()]


def new_screenshots(store) -> list[str]:
    import time
    since = float(store.get("desk:shots_since") or 0) or time.time() - 60
    newest, found = since, []
    for folder in screenshot_folders():
        for f in folder.glob("*.png"):
            try:
                m = f.stat().st_mtime
            except OSError:
                continue
            if m > since and ("screenshot" in f.name.lower() or folder.name.startswith("Screenshots")):
                found.append(str(f))
                newest = max(newest, m)
    store.set("desk:shots_since", str(max(newest, since)))
    return found[:3]
