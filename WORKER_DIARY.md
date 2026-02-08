# iphoneclaw Worker Diary

This is a lightweight, text-only "lessons learned" log written by the supervisor agent (Claude Code/Codex).
Goal: make the worker more reliable over time by recording recurring failure modes and the fixes.

Rules:
- Do NOT paste screenshots or base64.
- Do NOT paste secrets (API keys, tokens).
- Keep entries short and actionable.
- Prefer: symptom -> cause -> fix -> how to prevent.

## Common Lessons

- Scrolling:
  - Prefer `scroll(direction='down'|'up', ...)` (wheel), not vertical `drag(...)`.
  - Avoid "click to focus" before scrolling. Clicking may open a video/item under the cursor.
  - On iPhone Home/App Library, scroll/swipe slightly above the bottom nav/dock, not mid-screen.

- Typing:
  - `type(content=...)` must be ASCII only. For Chinese, type pinyin (ASCII) and click IME candidates.
  - Avoid iPhone Home Screen search/Spotlight for launching apps; typing there is often unreliable.

- iPhone gestures:
  - Long-press-like drags can trigger icon rearrange; keep swipe gestures fast (no long hold).

## Entry Template

Date: YYYY-MM-DD
Task: <short>
Symptom: <what went wrong>
Cause: <why>
Fix: <what to do next time>
Prevention: <prompt/guideline/config change>

