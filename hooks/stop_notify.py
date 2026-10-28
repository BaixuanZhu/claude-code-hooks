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

AUTO_CLOSE_MS = 8000   # auto-close after 8 seconds
MAX_PREVIEW = 120      # cap the in-dialog preview length


def _truncate(text: str, max_len: int = MAX_PREVIEW) -> str:
    """Collapse whitespace and cap at max_len with an ellipsis."""
    text = re.sub(r"\s+", " ", text)
    if len(text) > max_len:
        text = text[:max_len].rstrip() + "\u2026"
    return text


def _build_message(data: dict) -> tuple[str, str]:
    """Return (title, body) for the event in the hook payload."""
    event = data.get("hook_event_name") or "Stop"

    if event == "StopFailure":
        error = data.get("error") or "unknown"
        details = _truncate((data.get("error_details") or "").strip(), 200)
        body = hook_common.tr("stop.failure_body", error=error)
        if details:
            body += f"\n\n{details}"
        return hook_common.tr("stop.failure_title"), body

    tasks = data.get("background_tasks") or []
    crons = data.get("session_crons") or []
    if tasks or crons:
        parts = []
        if tasks:
            key = "stop.task" if len(tasks) == 1 else "stop.tasks"
            parts.append(hook_common.tr(key, n=len(tasks)))
        if crons:
            key = "stop.cron" if len(crons) == 1 else "stop.crons"
            parts.append(hook_common.tr(key, n=len(crons)))
        joined = (
            hook_common.tr("stop.join", a=parts[0], b=parts[1])
            if len(parts) == 2 else parts[0]
        )
        body_key = (
            "stop.waiting_body_single"
            if len(tasks) + len(crons) == 1
            else "stop.waiting_body_many"
        )
        return hook_common.tr("stop.waiting_title"), hook_common.tr(body_key, parts=joined)

    msg = (data.get("last_assistant_message") or "").strip()
    if not msg:
        return hook_common.tr("stop.done_title"), hook_common.tr("stop.done_body")
    return hook_common.tr("stop.done_title"), _truncate(msg)


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
    if hook_common.gui_disabled():
        sys.exit(0)

    data = hook_common.read_stdin_json()
    title, message = _build_message(data)
    title = hook_common.with_project(title, data)

    # Notifications never queue: if a permission/question dialog is open, a
    # stale notification popping on top of it helps nobody.
    lock = hook_common.acquire_dialog_lock(0)
    if lock is None:
        sys.exit(0)

    try:
        show_notification(title, message)
    except tk.TclError:
        # No display available; a notification is never worth failing the turn.
        pass
    finally:
        lock.release()
    sys.exit(0)


if __name__ == "__main__":
    main()
