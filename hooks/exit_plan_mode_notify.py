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

import ctypes
import json
import os
import re
import sys
import tkinter as tk
from tkinter import messagebox

AUTO_CLOSE_MS = 25000  # 25 seconds
MAX_PREVIEW = 120      # cap the in-dialog plan preview length

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


def _build_message(data: dict) -> str:
    """Build the dialog body, including a short plan preview when available."""
    plan = ""
    tool_input = data.get("tool_input") or {}
    if isinstance(tool_input, dict):
        plan = (tool_input.get("plan") or "").strip()

    if plan:
        # Take the first meaningful (non-empty, non-heading) line as the gist.
        for line in plan.splitlines():
            line = line.strip().lstrip("#").lstrip("*").strip()
            if line:
                preview = _truncate(line)
                return f"Plan is ready. Please review and approve.\n\n{preview}"
        # Plan had content but no usable line — show truncated raw text.
        preview = _truncate(plan)
        return f"Plan is ready. Please review and approve.\n\n{preview}"

    return "Plan is ready. Please review and approve."


def show_notification(message: str):
    root = tk.Tk()
    root.withdraw()  # hide root window
    root.attributes("-topmost", True)

    # Auto-close: this is the ONLY place we destroy root. We intentionally do
    # NOT call root.destroy() after showinfo() returns: in Python 3.14
    # root.destroy() tears down the whole Tcl interpreter, so any later Tk call
    # (even winfo_exists) raises "can't invoke ... : application has been
    # destroyed". When the user clicks OK, showinfo returns and main() does
    # sys.exit(0), which cleans up the process — no explicit destroy needed.
    root.after(AUTO_CLOSE_MS, root.destroy)

    messagebox.showinfo(
        "Claude Code",
        message,
        parent=root,
    )


def main():
    # Test mode: skip dialog, exit cleanly.
    if os.environ.get("CLAUDE_HOOK_TEST") == "1":
        sys.exit(0)

    data = _read_stdin_json()
    message = _build_message(data)
    show_notification(message)

    # No decision output needed
    sys.exit(0)


if __name__ == "__main__":
    main()
