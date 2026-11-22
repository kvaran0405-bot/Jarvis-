"""The floating JARVIS orb for the laptop: a small glowing reactor that stays on top of every app.

  • Drag it anywhere (it remembers where).        • Click: JARVIS listens (the JARVIS window opens if it isn't).
  • Right-click: Talk · Call · Focus · Record · Brief me · Dashboard · Hide for an hour · Close orb.
  • It pulses in the speaking agent's colour and shows what they're saying in a small bubble.

Started automatically with JARVIS (turn off with JARVIS_ORB=off). Runs as its own small process:  python -m jarvis orb
Uses only Python's built-in tkinter, so nothing extra to install.
"""
from __future__ import annotations

import json
import math
import random
import threading
import time
import urllib.request
from pathlib import Path

from .config import ROOT, settings

SIZE = 92
KEY = "#010203"            # this exact colour is made see-through on Windows
POS_FILE = ROOT / "data" / "orb.json"


def _api(path: str, body: dict | None = None, timeout: float = 4) -> dict:
    url = f"http://127.0.0.1:{settings.port}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if body is not None else "GET",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def _mix(hex1: str, hex2: str, k: float) -> str:
    a = [int(hex1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(hex2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(int(x + (y - x) * k) for x, y in zip(a, b))


class Orb:
    def __init__(self):
        import tkinter as tk
        self.tk = tk
        self.root = root = tk.Tk()
        root.title("JARVIS")
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        try:
            root.attributes("-transparentcolor", KEY)   # Windows: everything in KEY colour is see-through
            bg = KEY
        except tk.TclError:
            bg = "#05080d"
        self.bg = bg
        x, y = self._load_pos(root)
        root.geometry(f"{SIZE}x{SIZE}+{x}+{y}")
        self.c = tk.Canvas(root, width=SIZE, height=SIZE, bg=bg, highlightthickness=0, bd=0)
        self.c.pack()
        self.state = {"color": "#ffd23f", "speaking": False, "mode": "on", "text": "", "screens": 1, "agent": "JARVIS"}
        self.t0 = time.time()
        self.drag = None
        self.moved = False
        self.hidden_until = 0.0
        self.bubble = None
        self.c.bind("<ButtonPress-1>", self._press)
        self.c.bind("<B1-Motion>", self._motion)
        self.c.bind("<ButtonRelease-1>", self._release)
        self.c.bind("<Double-Button-1>", lambda e: self._open("/command-centre.html?kiosk=1"))
        self.c.bind("<Button-3>", self._menu)
        self.c.bind("<Enter>", lambda e: self._tip(True))
        self.c.bind("<Leave>", lambda e: self._tip(False))
        threading.Thread(target=self._poll, daemon=True).start()
        self._draw()

    # ------------------------------------------------------------ position
    def _load_pos(self, root) -> tuple[int, int]:
        try:
            p = json.loads(POS_FILE.read_text())
            return int(p["x"]), int(p["y"])
        except Exception:  # noqa: BLE001 - first run: bottom-right corner
            return root.winfo_screenwidth() - SIZE - 40, root.winfo_screenheight() - SIZE - 120

    def _save_pos(self):
        POS_FILE.parent.mkdir(parents=True, exist_ok=True)
        POS_FILE.write_text(json.dumps({"x": self.root.winfo_x(), "y": self.root.winfo_y()}))

    # ------------------------------------------------------------ mouse
    def _press(self, e):
        self.drag = (e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y())
        self.moved = False

    def _motion(self, e):
        if self.drag:
            self.moved = True
            self.root.geometry(f"+{e.x_root - self.drag[0]}+{e.y_root - self.drag[1]}")

    def _release(self, e):
        if self.moved:
            self._save_pos()
        else:
            self._talk()
        self.drag = None

    def _talk(self):
        def go():
            try:
                if not self.state.get("screens"):
                    self._open("/command-centre.html?kiosk=1&listen=1")
                else:
                    _api("/api/orb/action", {"action": "talk"})
            except Exception:  # noqa: BLE001
                self._say("I can't reach the JARVIS server, Sir.")
        threading.Thread(target=go, daemon=True).start()

    def _open(self, path: str):
        from .__main__ import open_jarvis_window
        url = f"http://127.0.0.1:{settings.port}{path}"
        if not open_jarvis_window(url):
            import webbrowser
            webbrowser.open(url)

    def _action(self, name: str):
        def go():
            try:
                out = _api("/api/orb/action", {"action": name}, timeout=30)
                if out.get("say"):
                    self._say(out["say"])
            except Exception as exc:  # noqa: BLE001
                self._say(f"That didn't work: {exc}")
        threading.Thread(target=go, daemon=True).start()

    def _menu(self, e):
        tk = self.tk
        m = tk.Menu(self.root, tearoff=0, bg="#0a111a", fg="#dce7f2", activebackground="#1a2a3a",
                    activeforeground="#ffcc3d", bd=0, font=("Segoe UI", 10))
        m.add_command(label="🎙  Talk", command=self._talk)
        m.add_command(label="📞  Call JARVIS", command=lambda: self._open("/call.html"))
        m.add_command(label="🛡  Focus 50 min", command=lambda: self._action("focus"))
        m.add_command(label="🔴  Record / stop lecture", command=lambda: self._action("record"))
        m.add_command(label="📋  Brief me", command=lambda: self._action("brief"))
        m.add_separator()
        m.add_command(label="🖥  Open dashboard", command=lambda: self._open("/command-centre.html?kiosk=1"))
        m.add_command(label="🙈  Hide for 1 hour", command=self._hide)
        m.add_command(label="✖  Close orb", command=self.root.destroy)
        m.tk_popup(e.x_root, e.y_root)

    def _hide(self):
        self.root.withdraw()
        self.root.after(3600 * 1000, self.root.deiconify)

    # ------------------------------------------------------------ bubble + tooltip
    def _say(self, text: str, secs: float = 6):
        self.root.after(0, lambda: self._show_bubble(text, secs))

    def _show_bubble(self, text: str, secs: float):
        tk = self.tk
        if self.bubble is not None:
            self.bubble.destroy()
        b = tk.Toplevel(self.root)
        b.overrideredirect(True)
        b.attributes("-topmost", True)
        color = self.state.get("color", "#ffd23f")
        f = tk.Frame(b, bg="#0a111a", highlightbackground=color, highlightthickness=1)
        f.pack()
        tk.Label(f, text=self.state.get("agent", "JARVIS"), bg="#0a111a", fg=color,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=8, pady=(6, 0))
        tk.Label(f, text=text, bg="#0a111a", fg="#dce7f2", wraplength=260, justify="left",
                 font=("Segoe UI", 10)).pack(anchor="w", padx=8, pady=(0, 7))
        b.update_idletasks()
        bx = self.root.winfo_x() - b.winfo_width() - 8
        if bx < 0:
            bx = self.root.winfo_x() + SIZE + 8
        b.geometry(f"+{bx}+{self.root.winfo_y() + 10}")
        self.bubble = b
        b.after(int(secs * 1000), lambda: (b.destroy(), setattr(self, "bubble", None) if self.bubble is b else None))

    def _tip(self, on: bool):
        if on and not self.state.get("speaking"):
            mode = self.state.get("mode")
            self._say("Paused. Say resume to wake me." if mode == "paused" else
                      "Click to talk · drag to move · right-click for more", 2.5)

    # ------------------------------------------------------------ live state
    def _poll(self):
        last_text = ""
        while True:
            try:
                st = _api("/api/orb", timeout=2)
                self.state.update(st)
                if st.get("text") and st["text"] != last_text and not st.get("screens"):
                    # nobody has the JARVIS window open: show what he's saying next to the orb
                    last_text = st["text"]
                    self._say(st["text"][-200:], 6)
            except Exception:  # noqa: BLE001 - server restarting
                self.state["mode"] = "offline"
            time.sleep(.35)

    # ------------------------------------------------------------ drawing
    def _draw(self):
        c, t, st = self.c, time.time() - self.t0, self.state
        c.delete("all")
        col = st.get("color") or "#ffd23f"
        if st.get("mode") in ("paused", "offline"):
            col = "#56606e"
        speaking = st.get("speaking")
        m = SIZE / 2
        amp = (0.5 + 0.5 * math.sin(t * 9) * random.uniform(.6, 1)) if speaking else (0.5 + 0.5 * math.sin(t * 2.4)) * .35
        # dark puck so the neon reads on any wallpaper
        c.create_oval(4, 4, SIZE - 4, SIZE - 4, fill="#05080d", outline=_mix(col, "#05080d", .55), width=1)
        # glow core (concentric discs fading into the puck)
        r_core = 13 + amp * 7
        for i in range(8, 0, -1):
            k = i / 8
            c.create_oval(m - r_core * k * 1.9, m - r_core * k * 1.9, m + r_core * k * 1.9, m + r_core * k * 1.9,
                          fill=_mix("#05080d", col, (1 - k) ** 1.4 * .9), outline="")
        c.create_oval(m - r_core * .45, m - r_core * .45, m + r_core * .45, m + r_core * .45, fill="#ffffff", outline="")
        # rings
        spin = t * (220 if speaking else 70)
        for r, w, sp, ext, k in ((26, 3, 1, 150, 0), (33, 2, -1.4, 110, .35), (39, 2, .7, 70, .55)):
            c.create_arc(m - r, m - r, m + r, m + r, start=(spin * sp) % 360, extent=ext, style="arc",
                         outline=_mix(col, "#05080d", k), width=w)
        # reactor segments
        for i in range(8):
            a = math.radians(i * 45 + spin * .3)
            c.create_line(m + math.cos(a) * 17, m + math.sin(a) * 17, m + math.cos(a) * 21, m + math.sin(a) * 21,
                          fill=_mix(col, "#ffffff", .3), width=2)
        if st.get("focus"):
            c.create_oval(2, 2, SIZE - 2, SIZE - 2, outline="#38d6ff", width=2, dash=(3, 4))
        self.root.after(33, self._draw)

    def run(self):
        self.root.mainloop()


def main() -> int:
    try:
        Orb().run()
    except Exception as exc:  # noqa: BLE001 - no screen (e.g. a server without a desktop)
        print(f"The floating orb couldn't start: {exc}")
        return 1
    return 0
