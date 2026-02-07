from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import List, Optional

from iphoneclaw.types import StatusEnum


@dataclass
class WorkerControl:
    status: StatusEnum = StatusEnum.INIT
    paused: bool = False
    stopped: bool = False
    injected: List[str] = field(default_factory=list)

    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def pause(self) -> None:
        with self._lock:
            self.paused = True
            if self.status == StatusEnum.RUNNING:
                self.status = StatusEnum.PAUSE

    def resume(self) -> None:
        with self._lock:
            self.paused = False
            if self.status in (StatusEnum.PAUSE, StatusEnum.HANG):
                self.status = StatusEnum.RUNNING

    def stop(self) -> None:
        with self._lock:
            self.stopped = True
            self.status = StatusEnum.USER_STOPPED

    def set_status(self, status: StatusEnum) -> None:
        with self._lock:
            # Do not override stopped state.
            if self.stopped:
                self.status = StatusEnum.USER_STOPPED
                return
            # If paused, keep PAUSE/HANG unless the caller explicitly sets ERROR/END.
            if self.paused and status == StatusEnum.RUNNING:
                return
            self.status = status

    def inject(self, text: str) -> None:
        with self._lock:
            self.injected.append(text)

    def pop_injected(self) -> Optional[str]:
        with self._lock:
            if not self.injected:
                return None
            return self.injected.pop(0)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "status": self.status.value,
                "paused": self.paused,
                "stopped": self.stopped,
                "pending_injected": len(self.injected),
            }
