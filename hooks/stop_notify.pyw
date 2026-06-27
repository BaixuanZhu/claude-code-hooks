#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Claude Code Stop hook.

When Claude finishes responding and waits for user input, pops up a
topmost tkinter message box so you notice it's done. No JSON output,
no terminal escape sequences, no third-party dependencies.

Reads JSON from stdin (UTF-8) only to grab a short preview of the
last assistant message for the dialog body. Falls back to a generic
"Task completed" message when there's nothing to show.
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


def _build_message(data: dict) -> str:
    """Build the dialog body. Shows a short preview of the last reply if any."""
    msg = (data.get("last_assistant_message") or "").strip()
    if not msg:
        return "Claude finished. Waiting for your input."

    # Collapse whitespace/newlines so the preview fits on one clean line.
    msg = re.sub(r"\s+", " ", msg)
    if len(msg) > MAX_PREVIEW:
        msg = msg[:MAX_PREVIEW].rstrip() + "..."
    return msg


def show_notification(message: str):
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

    messagebox.showinfo("Claude Code - Done", message, parent=root)


def main():
    # Test mode: skip dialog, emit continue=true and exit.
    if os.environ.get("CLAUDE_HOOK_TEST") == "1":
        print(json.dumps({"continue": True}))
        sys.exit(0)

    data = _read_stdin_json()
    message = _build_message(data)
    show_notification(message)

    # Hookify plugin requires valid JSON on stdout even when the
    # native Stop hook spec allows empty output. Emit a minimal
    # "continue": true so the plugin doesn't choke.
    print(json.dumps({"continue": True}))


if __name__ == "__main__":
    main()
