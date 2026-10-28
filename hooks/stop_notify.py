#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Claude Code Stop / StopFailure hook.

Stop fires when Claude finishes a turn; StopFailure fires instead when the turn
ends due to an API error (rate limit, auth failure, ...). Both pop a topmost
tkinter message box so the end of a turn is noticeable, and both run async so
they never delay Claude.

No JSON output: notification-only hooks cannot control the turn.
"""

import ctypes
import json
import os
import re
import sys
import tkinter as tk
from tkinter import messagebox

AUTO_CLOSE_MS = 8000   # auto-close after 8 seconds
MAX_PREVIEW = 120      # cap the in-dialog preview length

# High-DPI awareness so dialogs aren't blurry on scaled displays.
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)  # per-monitor V2 (Win 8.1+)
except (AttributeError, OSError):
    try:
        ctypes.windll.user32.SetProcessDPIAware()  # legacy fallback (Vista+)
    except (AttributeError, OSError):
        pass


def _read_stdin_json() -> dict:
    """Best-effort UTF-8 JSON read from stdin. Returns {} on any failure."""
    try:
        raw = sys.stdin.buffer.read()
        if not raw:
            return {}
        data = json.loads(raw.decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _truncate(text: str, max_len: int = MAX_PREVIEW) -> str:
    """Collapse whitespace and cap at max_len with an ellipsis."""
    text = re.sub(r"\s+", " ", text)
    if len(text) > max_len:
        text = text[:max_len].rstrip() + "\u2026"
    return text


def _gui_disabled() -> bool:
    """True in CI or when the user opted out."""
    return os.environ.get("CLAUDE_GUI_HOOKS_DISABLE") == "1" or bool(os.environ.get("CI"))


def _build_message(data: dict) -> tuple[str, str]:
    """Return (title, body) for the event in the hook payload."""
    event = data.get("hook_event_name") or "Stop"

    if event == "StopFailure":
        error = data.get("error") or "unknown"
        details = _truncate((data.get("error_details") or "").strip(), 200)
        body = f"The turn ended due to an API error: {error}."
        if details:
            body += f"\n\n{details}"
        return "Claude Code - API Error", body

    tasks = data.get("background_tasks") or []
    crons = data.get("session_crons") or []
    if tasks or crons:
        parts = []
        if tasks:
            parts.append(f"{len(tasks)} background task" + ("" if len(tasks) == 1 else "s"))
        if crons:
            parts.append(f"{len(crons)} scheduled wakeup" + ("" if len(crons) == 1 else "s"))
        return (
            "Claude Code - Waiting",
            "Claude is paused while " + " and ".join(parts) + " are still running.",
        )

    msg = (data.get("last_assistant_message") or "").strip()
    if not msg:
        return "Claude Code - Done", "Claude finished. Waiting for your input."
    return "Claude Code - Done", _truncate(msg)


def show_notification(title: str, message: str):
    root = tk.Tk()
    root.withdraw()  # hide root window
    root.attributes("-topmost", True)

    # Auto-close so the box doesn't pile up if you're away.
    # This is the ONLY place we destroy root. We intentionally do NOT call
    # root.destroy() after showinfo() returns: in Python 3.14 root.destroy()
    # tears down the whole Tcl interpreter, so any later Tk call (even
    # winfo_exists) raises "can't invoke ... : application has been destroyed".
    # When the user clicks OK, showinfo returns and main() does sys.exit(0),
    # which cleans up the process — no explicit destroy needed.
    root.after(AUTO_CLOSE_MS, root.destroy)

    messagebox.showinfo(title, message, parent=root)


def main():
    if os.environ.get("CLAUDE_HOOK_TEST") == "1":
        sys.exit(0)
    if _gui_disabled():
        sys.exit(0)

    data = _read_stdin_json()
    title, message = _build_message(data)
    try:
        show_notification(title, message)
    except tk.TclError:
        # No display available; a notification is never worth failing the turn.
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
