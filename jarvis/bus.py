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
