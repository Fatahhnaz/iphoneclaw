from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional, Tuple

import Quartz


# Tag all agent-injected CGEvents so the event tap can ignore them.
IPHONECLAW_EVENT_TAG = 0x1C10_55A  # arbitrary non-zero marker


@dataclass
class UserActivity:
    kind: str  # mouse|keyboard|scroll
    event_type: int
    at: float
    pos: Optional[Tuple[float, float]] = None


class UserInputMonitor:
    """
    Monitor local user input via CGEventTap and invoke a callback.

    Design goals:
    - Trigger quickly when the user starts interacting (so we can pause the worker).
    - Avoid false positives from agent-injected CGEvents (tagged in our _post()).
    - Debounce to avoid event storms.
    """

    def __init__(
        self,
        *,
        on_activity: Callable[[UserActivity], None],
        debounce_s: float = 0.8,
    ) -> None:
        self._on_activity = on_activity
        self._debounce_s = float(debounce_s)
        self._last_fire = 0.0
        self._suppressed_until = 0.0
        self._lock = threading.Lock()

        self._thread: Optional[threading.Thread] = None
        self._run_loop = None
        self._tap = None
        self._tap_source = None
        self._cb_ref = None  # prevent GC
        self._stopping = False
        self._last_mouse_pos: Optional[Tuple[float, float]] = None

    def suppress_for(self, seconds: float) -> None:
        until = time.time() + max(0.0, float(seconds))
        with self._lock:
            if until > self._suppressed_until:
                self._suppressed_until = until

    def start(self) -> None:
        if self._thread is not None:
            return
        if os.name != "posix":
            return
        self._thread = threading.Thread(target=self._run, name="iphoneclaw-user-input", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stopping = True
        try:
            if self._run_loop is not None:
                Quartz.CFRunLoopStop(self._run_loop)
        except Exception:
            pass
        t = self._thread
        if t is not None:
            t.join(timeout=1.5)
        self._thread = None

    def _should_ignore(self, event) -> bool:
        now = time.time()
        with self._lock:
            if now < self._suppressed_until:
                return True
            last_fire = self._last_fire

        # Debounce globally.
        if now - last_fire < self._debounce_s:
            return True

        # Ignore our own injected CGEvents (mouse/keyboard).
        try:
            tag = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGEventSourceUserData)
            if int(tag) == int(IPHONECLAW_EVENT_TAG):
                return True
        except Exception:
            pass

        # Also ignore events whose source pid is our own process.
        try:
            pid = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGEventSourceUnixProcessID)
            if int(pid) == int(os.getpid()):
                return True
        except Exception:
            pass

        return False

    def _fire(self, activity: UserActivity) -> None:
        with self._lock:
            self._last_fire = activity.at
        try:
            self._on_activity(activity)
        except Exception:
            # Never let the event tap crash the worker.
            pass

    def _run(self) -> None:
        # Listen for common user actions; mouseMoved is throttled further below.
        mask = 0
        for t in (
            Quartz.kCGEventMouseMoved,
            Quartz.kCGEventLeftMouseDown,
            Quartz.kCGEventRightMouseDown,
            Quartz.kCGEventOtherMouseDown,
            Quartz.kCGEventScrollWheel,
            Quartz.kCGEventKeyDown,
            Quartz.kCGEventFlagsChanged,
        ):
            mask |= Quartz.CGEventMaskBit(t)

        def cb(_proxy, type_, event, _refcon):  # noqa: ANN001
            if self._stopping:
                return event
            if self._should_ignore(event):
                return event

            now = time.time()
            kind = "mouse"
            pos: Optional[Tuple[float, float]] = None

            try:
                pt = Quartz.CGEventGetLocation(event)
                pos = (float(pt.x), float(pt.y))
            except Exception:
                pos = None

            if type_ == Quartz.kCGEventScrollWheel:
                kind = "scroll"
            elif type_ in (Quartz.kCGEventKeyDown, Quartz.kCGEventFlagsChanged):
                kind = "keyboard"
            else:
                kind = "mouse"

            if type_ == Quartz.kCGEventMouseMoved and pos is not None:
                # Ignore tiny jitters to reduce accidental pauses.
                last = self._last_mouse_pos
                self._last_mouse_pos = pos
                if last is not None:
                    dx = pos[0] - last[0]
                    dy = pos[1] - last[1]
                    if (dx * dx + dy * dy) < 16.0:  # < 4 px
                        return event

            self._fire(UserActivity(kind=kind, event_type=int(type_), at=now, pos=pos))
            return event

        self._cb_ref = cb
        tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionListenOnly,
            mask,
            cb,
            None,
        )
        self._tap = tap
        if tap is None:
            # Usually means Accessibility permission missing.
            return

        source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
        self._tap_source = source
        rl = Quartz.CFRunLoopGetCurrent()
        self._run_loop = rl
        Quartz.CFRunLoopAddSource(rl, source, Quartz.kCFRunLoopCommonModes)
        try:
            Quartz.CGEventTapEnable(tap, True)
        except Exception:
            pass
        Quartz.CFRunLoopRun()

