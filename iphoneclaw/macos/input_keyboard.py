"""Keyboard input via Quartz CGEvent.

Design goal: avoid AppleScript keystrokes; prefer clipboard paste for text.
This is intentionally minimal at first (only keys we need early).
"""

from __future__ import annotations

import time
from typing import Dict, Iterable, List, Optional

import Quartz


# Key codes are hardware-dependent; these are standard for US keyboard layouts.
KEYCODES: Dict[str, int] = {
    # Letters
    "a": 0,
    "s": 1,
    "d": 2,
    "f": 3,
    "h": 4,
    "g": 5,
    "z": 6,
    "x": 7,
    "c": 8,
    "v": 9,
    "b": 11,
    "q": 12,
    "w": 13,
    "e": 14,
    "r": 15,
    "y": 16,
    "t": 17,
    "o": 31,
    "u": 32,
    "i": 34,
    "p": 35,
    "l": 37,
    "j": 38,
    "k": 40,
    "n": 45,
    "m": 46,

    # Numbers (top row)
    "0": 29,
    "1": 18,
    "2": 19,
    "3": 20,
    "4": 21,
    "5": 23,
    "6": 22,
    "7": 26,
    "8": 28,
    "9": 25,

    # Common keys
    "return": 36,
    "enter": 36,
    "tab": 48,
    "space": 49,
    "escape": 53,
    "delete": 51,  # backspace

    # Arrow keys
    "left": 123,
    "right": 124,
    "down": 125,
    "up": 126,
}

MOD_FLAGS: Dict[str, int] = {
    "cmd": Quartz.kCGEventFlagMaskCommand,
    "command": Quartz.kCGEventFlagMaskCommand,
    "ctrl": Quartz.kCGEventFlagMaskControl,
    "control": Quartz.kCGEventFlagMaskControl,
    "alt": Quartz.kCGEventFlagMaskAlternate,
    "option": Quartz.kCGEventFlagMaskAlternate,
    "shift": Quartz.kCGEventFlagMaskShift,
}


def _post(event) -> None:
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)


def _flags_for(mods: Iterable[str]) -> int:
    flags = 0
    for m in mods:
        flags |= MOD_FLAGS.get(m.lower().strip(), 0)
    return flags


def press(key: str, modifiers: Optional[List[str]] = None, delay_s: float = 0.02) -> None:
    k = key.lower().strip()
    if k not in KEYCODES:
        raise ValueError(f"Unsupported key: {key!r}")

    flags = _flags_for(modifiers or [])
    keycode = KEYCODES[k]

    down = Quartz.CGEventCreateKeyboardEvent(None, keycode, True)
    Quartz.CGEventSetFlags(down, flags)
    up = Quartz.CGEventCreateKeyboardEvent(None, keycode, False)
    Quartz.CGEventSetFlags(up, flags)

    _post(down)
    time.sleep(delay_s)
    _post(up)


def paste_text(text: str, *, press_enter: bool = False) -> None:
    """Paste text via clipboard and Cmd+V."""
    from AppKit import NSPasteboard  # type: ignore
    try:
        from AppKit import NSPasteboardTypeString  # type: ignore
        ptype = NSPasteboardTypeString
    except Exception:
        # Older PyObjC names
        from AppKit import NSStringPboardType  # type: ignore

        ptype = NSStringPboardType

    pb = NSPasteboard.generalPasteboard()
    # Save and restore clipboard (best-effort).
    old = None
    try:
        old = pb.stringForType_(ptype)
    except Exception:
        old = None

    try:
        pb.clearContents()
        pb.setString_forType_(text, ptype)

        time.sleep(0.05)
        press("v", modifiers=["cmd"])
        time.sleep(0.05)
        if press_enter:
            press("return")
        # Allow the target app to finish reading the clipboard before restoring.
        time.sleep(0.3)
    finally:
        if old is not None:
            try:
                pb.clearContents()
                pb.setString_forType_(old, ptype)
            except Exception:
                pass
