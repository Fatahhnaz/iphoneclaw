"""Permission pre-checks for Screen Recording and Accessibility."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def check_automation_system_events() -> bool:
    """
    Check Automation permission (Terminal/Python -> System Events) by running a minimal AppleScript.
    This may trigger a permission prompt the first time.
    """
    try:
        from iphoneclaw.macos.applescript_runner import run_system_events_script

        run_system_events_script(
            'tell application "System Events" to get the name of every process',
            mode="auto",
            timeout_s=5.0,
        )
        return True
    except Exception:
        return False


def check_screen_recording() -> bool:
    """Check Screen Recording permission by attempting a window list capture."""
    try:
        import Quartz

        window_list = Quartz.CGWindowListCopyWindowInfo(
            Quartz.kCGWindowListOptionOnScreenOnly, Quartz.kCGNullWindowID
        )
        # If we get None or empty with no error, permission may be denied.
        # A non-None list (even empty) usually means permission is granted.
        if window_list is None:
            return False
        # Try to actually capture an image — this is the definitive test.
        img = Quartz.CGWindowListCreateImage(
            Quartz.CGRectInfinite,
            Quartz.kCGWindowListOptionOnScreenOnly,
            Quartz.kCGNullWindowID,
            Quartz.kCGWindowImageDefault,
        )
        return img is not None
    except Exception:
        return False


def check_accessibility() -> bool:
    """Check Accessibility permission via AXIsProcessTrustedWithOptions."""
    try:
        from ApplicationServices import AXIsProcessTrustedWithOptions
        from Foundation import NSDictionary

        options = NSDictionary.dictionaryWithObject_forKey_(
            False, "AXTrustedCheckOptionPrompt"
        )
        return bool(AXIsProcessTrustedWithOptions(options))
    except Exception:
        return False


def run_doctor() -> bool:
    """Run permission diagnostics. Returns True if all checks pass."""
    print("iphoneclaw doctor — Permission Check")
    print("=" * 40)

    ok = True

    sr = check_screen_recording()
    print(f"  Screen Recording: {'OK' if sr else 'MISSING'}")
    if not sr:
        print("    -> System Settings > Privacy & Security > Screen Recording")
        print("    -> Enable for your terminal app (Terminal / iTerm2 / etc.)")
        ok = False

    ax = check_accessibility()
    print(f"  Accessibility:    {'OK' if ax else 'MISSING'}")
    if not ax:
        print("    -> System Settings > Privacy & Security > Accessibility")
        print("    -> Enable for your terminal app")
        ok = False

    au = check_automation_system_events()
    print(f"  Automation:       {'OK' if au else 'MISSING'} (System Events)")
    if not au:
        print("    -> System Settings > Privacy & Security > Automation")
        print("    -> Allow your terminal app to control 'System Events'")
        ok = False

    print()
    if ok:
        print("All permissions granted.")
    else:
        print("Please grant the missing permissions and re-run `iphoneclaw doctor`.")

    return ok
