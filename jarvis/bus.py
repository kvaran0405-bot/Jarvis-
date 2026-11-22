"""In-process event bus: agents publish activity, the dashboard subscribes over SSE."""
from __future__ import annotations

import queue
import threading
from typing import Any

from .store import Store


class Bus:
    def __init__(self, store: Store):
        self.store = store
        self._subs: list[queue.Queue] = []
        self._lock = threading.Lock()
        self.last_voice: tuple[str, float, int] = ("JARVIS", 0.0, 0)
        self.last_text = ""

    def subscribe(self) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=500)
        with self._lock:
            self._subs.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            if q in self._subs:
                self._subs.remove(q)

    def publish(self, event: dict[str, Any]) -> None:
        import time
        if event.get("type") in ("delta", "say", "ask"):   # the floating orb pulses while someone is talking
            words = str(event.get("say") or event.get("text") or "")
            if event.get("type") == "delta" and self.last_voice[0] == (event.get("agent") or "JARVIS") \
                    and time.time() - self.last_voice[1] < 8:
                words = (self.last_text + words)[-240:]   # streamed reply: keep the running sentence
            self.last_text = words
            self.last_voice = (event.get("agent") or "JARVIS", time.time(), len(words))
        with self._lock:
            subs = list(self._subs)
        for q in subs:
            try:
                q.put_nowait(event)
            except queue.Full:
                pass

    def log(self, agent: str, message: str, kind: str = "log") -> None:
        """Persist an activity line and push it to live dashboards."""
        row = self.store.log_activity(agent, message, kind)
        self.publish({"type": "activity", **row})

    def status(self, agent: str, state: str) -> None:
        """Agent state for the dashboard grid: online | working | reporting."""
        self.publish({"type": "status", "agent": agent, "state": state})

    @property
    def screens(self) -> int:
        """How many dashboards / apps are connected right now."""
        with self._lock:
            return len(self._subs)
