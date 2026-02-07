from __future__ import annotations

import subprocess
import sys
from typing import Optional


def _is_safe_system_events_script(script: str) -> bool:
    if not isinstance(script, str):
        return False
    if len(script) == 0 or len(script) > 4000:
        return False
    if "\n" in script or "\r" in script:
        return False
    if not script.startswith('tell application "System Events" to '):
        return False
    lowered = script.lower()
    if "do shell script" in lowered:
        return False
    if "tell application" in lowered and not lowered.startswith(
        'tell application "system events" to '
    ):
        return False
    return True


def run_system_events_script(
    script: str,
    *,
    mode: str = "auto",
    timeout_s: float = 10.0,
) -> str:
    """
    Run a single-line `tell application "System Events" to ...` AppleScript.

    Modes:
    - native: run in-process via NSAppleScript (TCC attribution is to this Python process / terminal)
    - osascript: run /usr/bin/osascript -e script
    - auto: prefer native; else -> osascript
    """
    if not _is_safe_system_events_script(script):
        raise ValueError("unsafe script (only single-line System Events scripts allowed)")

    mode = (mode or "auto").strip().lower()

    def try_native() -> Optional[str]:
        if sys.platform != "darwin":
            return None
        try:
            from Foundation import NSAppleScript  # type: ignore
        except Exception:
            return None
        try:
            a = NSAppleScript.alloc().initWithSource_(script)
            res, err = a.executeAndReturnError_(None)
            if err:
                # err is an NSDictionary-like mapping
                msg = None
                try:
                    msg = err.get("NSAppleScriptErrorMessage")
                except Exception:
                    msg = None
                raise RuntimeError(str(msg or err))
            if res is None:
                return ""
            try:
                s = res.stringValue()
                return "" if s is None else str(s)
            except Exception:
                return ""
        except Exception:
            raise

    if mode in ("native", "auto"):
        out = try_native()
        if out is not None:
            return out

    # osascript
    p = subprocess.run(
        ["/usr/bin/osascript", "-e", script],
        capture_output=True,
        text=True,
        timeout=timeout_s,
    )
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout or "").strip() or "osascript failed")
    return (p.stdout or "").strip()
