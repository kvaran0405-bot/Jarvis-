"""Clap or snap to summon JARVIS (two finger snaps work too): two sharp claps near the laptop and he answers ("Yes Sir?") and listens.
The first double clap after you've been away for a while gets the full welcome-home instead.

Runs on the laptop's microphone (needs `sounddevice`). Turn off with JARVIS_CLAP=off.
Detection is deliberately strict: exactly two short, loud bursts 0.15-0.8 s apart, with quiet around them,
so talking, music and typing don't set it off.
"""
from __future__ import annotations

import os
import threading
import time
from typing import Callable

RATE = 16000
BLOCK = 320                    # 20 ms
MIN_GAP, MAX_GAP = 0.15, 1.0   # seconds between the two claps / snaps
SNAP_SHARP = 0.75              # how "crisp" a sound must be to count as a snap (voices and music are far below)
SETTLE = 0.8                   # no third burst within this time after the second clap
COOLDOWN = 4.0


def enabled() -> bool:
    return os.environ.get("JARVIS_CLAP", "on").strip().lower() != "off"


class ClapDetector:
    """Feed it 20 ms blocks (peak and rms of float audio in -1..1); it calls `on_double` on a double clap."""

    def __init__(self, on_double: Callable[[], None], sensitivity: float = 1.0):
        self.on_double = on_double
        self.noise = 0.01                         # running background loudness (rms)
        self.threshold = max(0.1, 0.3 / max(sensitivity, 0.1))
        self.snap_threshold = max(0.03, 0.09 / max(sensitivity, 0.1))   # snaps are quieter, but very crisp
        self.cur_start, self.cur_len = 0.0, 0     # the loud burst in progress
        self.events: list[tuple[float, bool]] = []  # finished bursts: (start time, short enough to be a clap)
        self.last_fire = -COOLDOWN

    def feed(self, t: float, peak: float, rms: float, sharp: float = 0.0) -> None:
        clap = peak > self.threshold and peak > 8 * self.noise
        snap = peak > self.snap_threshold and sharp > SNAP_SHARP and peak > 6 * self.noise
        loud = clap or snap
        if loud:
            if self.cur_len == 0:
                self.cur_start = t
            self.cur_len += 1
            return
        if self.cur_len:
            self.events.append((self.cur_start, self.cur_len <= 4))   # a clap lasts under ~80 ms
            self.cur_len = 0
        self.noise = max(0.002, 0.98 * self.noise + 0.02 * rms)
        if self.events and t - self.events[-1][0] >= SETTLE:
            ev, self.events = self.events, []
            if (len(ev) == 2 and ev[0][1] and ev[1][1] and MIN_GAP <= ev[1][0] - ev[0][0] <= MAX_GAP
                    and t - self.last_fire > COOLDOWN):
                self.last_fire = t
                self.on_double()


def features(x) -> tuple[float, float, float]:
    """(peak, rms, sharpness) of a 20 ms block. Sharpness = how much of the sound is fast, high-pitched change:
    a finger snap or clap is ~1, a voice or music is well under 0.5."""
    import numpy as np
    a = np.abs(x)
    sharp = float(np.abs(np.diff(x)).mean() / (a.mean() + 1e-6)) if len(x) > 1 else 0.0
    return float(a.max()), float(np.sqrt((x ** 2).mean())), sharp


_thread: threading.Thread | None = None
_stop = threading.Event()
_paused = threading.Event()   # set while the lecture recorder uses the microphone


def pause(on: bool) -> None:
    (_paused.set if on else _paused.clear)()


def start(on_double: Callable[[], None]) -> str:
    """Start listening for claps in the background. Returns a status line."""
    global _thread
    if not enabled():
        return "clap: off"
    try:
        import numpy as np
        import sounddevice as sd
    except Exception:  # noqa: BLE001
        return "clap: needs sounddevice + numpy"
    sens = float(os.environ.get("JARVIS_CLAP_SENSITIVITY", "1") or 1)
    det = ClapDetector(on_double, sens)

    def run():
        t0 = time.monotonic()
        while not _stop.is_set():
            try:
                with sd.InputStream(samplerate=RATE, channels=1, dtype="float32", blocksize=BLOCK) as stream:
                    while not _stop.is_set():
                        if _paused.is_set():
                            break
                        data, _ = stream.read(BLOCK)
                        det.feed(time.monotonic() - t0, *features(data[:, 0]))
            except Exception:  # noqa: BLE001 - mic busy or unplugged: try again shortly
                pass
            _stop.wait(5 if not _paused.is_set() else 2)

    _thread = threading.Thread(target=run, daemon=True, name="jarvis-clap")
    _thread.start()
    return "clap: listening"


def stop() -> None:
    _stop.set()
