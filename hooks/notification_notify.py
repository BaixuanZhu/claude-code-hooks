#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Claude Code Notification hook for agent lifecycle events.

Shows a topmost message box when a subagent needs input or finishes. Handled
types are matched in hooks.json; other notification types (idle_prompt,
permission_prompt, ...) are intentionally ignored because the Stop and
PermissionRequest dialogs already cover them.

Notification-only hook: runs async and prints nothing.
"""

import ctypes
import json
import os
import re
import sys
import tkinter as tk
from tkinter import messagebox

AUTO_CLOSE_MS = 10000  # auto-close after 10 seconds
MAX_PREVIEW = 200      # cap the in-dialog message length

# notification_type -> (dialog title, fallback body)
SHOWN_TYPES = {
    "agent_needs_input": ("Claude Code - Agent Needs Input", "An agent needs your input."),
    "agent_completed": ("Claude Code - Agent Done", "An agent finished its work."),
}

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


def _gui_disabled() -> bool:
    """True in CI or when the user opted out."""
    return os.environ.get("CLAUDE_GUI_HOOKS_DISABLE") == "1" or bool(os.environ.get("CI"))


def _build_message(data: dict) -> tuple[str, str] | None:
    """Return (title, body), or None for notification types we do not show."""
    notification_type = data.get("notification_type") or ""
    entry = SHOWN_TYPES.get(notification_type)
    if entry is None:
        return None
    title, fallback = entry
    message = re.sub(r"\s+", " ", (data.get("message") or "").strip()) or fallback
    if len(message) > MAX_PREVIEW:
        message = message[:MAX_PREVIEW].rstrip() + "\u2026"
    return title, message


def show_notification(title: str, message: str):
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    root.after(AUTO_CLOSE_MS, root.destroy)
    messagebox.showinfo(title, message, parent=root)


def main():
    if os.environ.get("CLAUDE_HOOK_TEST") == "1":
        sys.exit(0)
    if _gui_disabled():
        sys.exit(0)

    data = _read_stdin_json()
    payload = _build_message(data)
    if payload is None:
        sys.exit(0)
    try:
        show_notification(*payload)
    except tk.TclError:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
