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

import os
import re
import sys
import tkinter as tk
from tkinter import messagebox

_HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
import hook_common

hook_common.enable_high_dpi()

AUTO_CLOSE_MS = 10000  # auto-close after 10 seconds
MAX_PREVIEW = 200      # cap the in-dialog message length

# Notification types we show; their title/body strings live in hook_common.
SHOWN_TYPES = ("agent_needs_input", "agent_completed")


def _build_message(data: dict) -> tuple[str, str] | None:
    """Return (title, body), or None for notification types we do not show."""
    notification_type = data.get("notification_type") or ""
    if notification_type not in SHOWN_TYPES:
        return None
    title = hook_common.tr(f"notif.{notification_type}.title")
    fallback = hook_common.tr(f"notif.{notification_type}.body")
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
    if hook_common.gui_disabled():
        sys.exit(0)

    data = hook_common.read_stdin_json()
    payload = _build_message(data)
    if payload is None:
        sys.exit(0)
    title, message = payload
    title = hook_common.with_project(title, data)

    lock = hook_common.acquire_dialog_lock(0)
    if lock is None:
        sys.exit(0)

    try:
        show_notification(title, message)
    except tk.TclError:
        pass
    finally:
        lock.release()
    sys.exit(0)


if __name__ == "__main__":
    main()
