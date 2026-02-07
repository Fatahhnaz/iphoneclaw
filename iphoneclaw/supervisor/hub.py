from __future__ import annotations

import queue
import threading
import time
from typing import Any, Dict, List, Optional

from iphoneclaw.types import SupervisorEvent


class SupervisorHub:
    """Thread-safe pub/sub for text-only events."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subs: List["queue.Queue[SupervisorEvent]"] = []
        self._last_status: Dict[str, Any] = {"status": "init"}

    def set_status(self, status: str, **extra: Any) -> None:
        self._last_status = {"status": status, **extra}
        self.publish("status", self._last_status)

    def get_status(self) -> Dict[str, Any]:
        return dict(self._last_status)

    def subscribe(self) -> "queue.Queue[SupervisorEvent]":
        q: "queue.Queue[SupervisorEvent]" = queue.Queue(maxsize=1000)
        with self._lock:
            self._subs.append(q)
        return q

    def unsubscribe(self, q: "queue.Queue[SupervisorEvent]") -> None:
        with self._lock:
            self._subs = [x for x in self._subs if x is not q]

    def publish(self, type_: str, data: Optional[Dict[str, Any]] = None) -> None:
        evt = SupervisorEvent(type=type_, data=data or {}, ts=time.time())
        with self._lock:
            subs = list(self._subs)
        for q in subs:
            try:
                q.put_nowait(evt)
            except Exception:
                # Drop events on slow consumers.
                pass

