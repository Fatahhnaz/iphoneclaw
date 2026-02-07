from __future__ import annotations

import subprocess
import time
from typing import List, Tuple

from iphoneclaw.macos.applescript_runner import run_system_events_script


def _to_applescript_string_literal(s: str) -> str:
    escaped = s.replace("\\", "\\\\").replace('"', '\\"')
    return '"' + escaped + '"'


def _expand_app_aliases_best_effort(app_name: str) -> List[str]:
    # Reuse the same iPhone Mirroring alias list as WindowFinder.
    try:
        from iphoneclaw.macos.window import expand_app_aliases

        return expand_app_aliases(app_name)
    except Exception:
        return [app_name] if app_name else []


def _activate_app_best_effort(app_name: str) -> List[str]:
    """
    Try to activate the target app.

    Important: On some macOS locales the visible window owner/process name may differ
    from the Finder app name. We try common aliases and do not assume open -a works
    for the exact string provided.
    """
    aliases = _expand_app_aliases_best_effort(app_name)
    for alias in aliases:
        if not alias:
            continue
        try:
            p = subprocess.run(["open", "-a", alias], capture_output=True)
            if p.returncode == 0:
                time.sleep(0.2)
                break
        except Exception:
            continue
    return aliases


def _focus_process_best_effort(process_names: List[str], *, mode: str) -> str:
    """
    Best-effort: make the process frontmost so System Events keystrokes land correctly.
    Returns the chosen process name (may be empty).
    """
    for name in process_names:
        if not name:
            continue
        try:
            # "set frontmost of process ..." is the most direct focusing primitive.
            run_system_events_script(
                'tell application "System Events" to set frontmost of process '
                + _to_applescript_string_literal(name)
                + " to true",
                mode=mode,
            )
            time.sleep(0.1)
            return name
        except Exception:
            continue
    return ""


def type_text_macos_applescript(
    *,
    app_name: str,
    content: str,
    mode: str = "auto",
) -> Tuple[bool, str]:
    """
    Type text via `System Events` keystroke + Return key code 36.

    Matches UI-TARS-desktop behavior:
    - trailing '\\n' or newline indicates "submit" (press Return after typing)
    - '\\n' inside content becomes line breaks
    - type line-by-line; press Return between lines
    """
    if content is None:
        content = ""

    trimmed = content.strip()
    submit_after = (
        trimmed.endswith("\\n") or trimmed.endswith("\n") or trimmed.endswith("\r\n")
    )

    strip_once = trimmed[:-2] if trimmed.endswith("\\n") else trimmed.rstrip("\r\n")
    normalized = strip_once.replace("\\n", "\n")
    lines: List[str] = normalized.splitlines() if normalized else [""]

    aliases = _activate_app_best_effort(app_name)
    proc = _focus_process_best_effort(aliases, mode=mode)

    def run_keystroke(line: str) -> None:
        lit = _to_applescript_string_literal(line)
        if proc:
            run_system_events_script(
                'tell application "System Events" to tell process '
                + _to_applescript_string_literal(proc)
                + " to keystroke "
                + lit,
                mode=mode,
            )
        else:
            run_system_events_script(
                'tell application "System Events" to keystroke ' + lit,
                mode=mode,
            )

    def run_return() -> None:
        if proc:
            run_system_events_script(
                'tell application "System Events" to tell process '
                + _to_applescript_string_literal(proc)
                + " to key code 36",
                mode=mode,
            )
        else:
            run_system_events_script(
                'tell application "System Events" to key code 36',
                mode=mode,
            )

    for i, line in enumerate(lines):
        if line:
            run_keystroke(line)
        if i != len(lines) - 1:
            run_return()

    if submit_after:
        run_return()

    return submit_after, normalized
