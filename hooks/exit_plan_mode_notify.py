#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Claude Code PermissionRequest hook — ExitPlanMode event.

Shows a topmost tkinter message box when ExitPlanMode fires.
No third-party dependencies required.

Auto-closes after ~25 seconds (configurable via AUTO_CLOSE_MS).

Claude Code injects the on-disk `plan` content into `tool_input.plan` before
handing it to hooks, so we read stdin to surface a one-line preview of what the
plan is about (falling back to a generic prompt when no plan is available).
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

AUTO_CLOSE_MS = 25000  # 25 seconds
MAX_PREVIEW = 120      # cap the in-dialog plan preview length


def _truncate(text: str, max_len: int = MAX_PREVIEW) -> str:
    """Collapse whitespace and cap at max_len with an ellipsis."""
    text = re.sub(r"\s+", " ", text)
    if len(text) > max_len:
        text = text[:max_len].rstrip() + "\u2026"
    return text


def _build_message(data: dict) -> str:
    """Build the dialog body, including a short plan preview when available."""
    base = hook_common.tr("plan.body")
    plan = ""
    tool_input = data.get("tool_input") or {}
    if isinstance(tool_input, dict):
        plan = (tool_input.get("plan") or "").strip()

    if plan:
        # Prefer the first content line (headings say less); fall back to the
        # first heading, then to raw text, when the plan has nothing else.
        heading_line = ""
        for line in plan.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            text = stripped.lstrip("#").lstrip("*").strip()
            if not text:
                continue
            if stripped.startswith("#"):
                heading_line = heading_line or text
                continue
            return f"{base}\n\n{_truncate(text)}"
        if heading_line:
            return f"{base}\n\n{_truncate(heading_line)}"
        return f"{base}\n\n{_truncate(plan)}"

    return base


def show_notification(message: str, title: str):
    root = tk.Tk()
    root.withdraw()  # hide root window
    root.attributes("-topmost", True)

    # Auto-close: this is the ONLY place we destroy root. We intentionally do
    # NOT call root.destroy() after showinfo() returns: in Python 3.14
    # root.destroy() tears down the whole Tcl interpreter, so any later Tk call
    # (even winfo_exists) raises "can't invoke ... : application has been destroyed".
    # When the user clicks OK, showinfo returns and main() does sys.exit(0),
    # which cleans up the process — no explicit destroy needed.
    root.after(AUTO_CLOSE_MS, root.destroy)

    messagebox.showinfo(
        title,
        message,
        parent=root,
    )


def main():
    # Test mode: skip dialog, exit cleanly.
    if os.environ.get("CLAUDE_HOOK_TEST") == "1":
        sys.exit(0)
    if hook_common.gui_disabled():
        sys.exit(0)

    data = hook_common.read_stdin_json()
    message = _build_message(data)
    title = hook_common.with_project(hook_common.tr("plan.window_title"), data)

    lock = hook_common.acquire_dialog_lock(0)
    if lock is None:
        sys.exit(0)

    try:
        show_notification(message, title)
    except tk.TclError:
        # No display available; never delay the plan approval prompt.
        pass
    finally:
        lock.release()

    # No decision output needed
    sys.exit(0)


if __name__ == "__main__":
    main()
