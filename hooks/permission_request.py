#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Claude Code PermissionRequest hook.

Reads JSON from stdin (UTF-8), shows Allow/Deny dialog,
outputs JSON decision to stdout.
"""

import json
import os
import sys
import tkinter as tk
from tkinter import font as tkfont, scrolledtext, ttk

_HOOKS_DIR = os.path.dirname(os.path.abspath(__file__))
if _HOOKS_DIR not in sys.path:
    sys.path.insert(0, _HOOKS_DIR)
import hook_common

# Ensure UTF-8 output for CJK content in the JSON decision. stdin is read via
# sys.stdin.buffer.read() and decoded manually, so only stdout needs reconfiguring.
sys.stdout.reconfigure(encoding="utf-8")

hook_common.enable_high_dpi()

MAX_WIDTH = 600
MAX_HEIGHT = 520
MIN_HEIGHT = 160

# How long a second permission dialog waits for the open one to close before
# showing anyway. Keeps parallel tool calls from stacking windows.
LOCK_WAIT_SECONDS = 60

_VALID_BEHAVIORS = ("allow", "deny", "ask")
_VALID_RULE_TYPES = ("replaceRules", "removeRules", "addDirectories", "removeDirectories")


def _setup_style(root: tk.Tk):
    """Configure ttk styles for a modern, clean look."""
    style = ttk.Style(root)
    hook_common.apply_theme(style)

    font_main = hook_common.ui_font(10)
    font_bold = hook_common.ui_font(12, bold=True)
    font_btn = hook_common.ui_font(10)

    style.configure("Title.TLabel", font=font_bold, foreground="#1a1a1a")
    style.configure("Body.TLabel", font=font_main, foreground="#333333")
    style.configure("TButton", font=font_btn, padding=(16, 8))
    style.configure("Accent.TButton", font=font_btn, padding=(16, 8))
    style.configure("Suggestion.TButton", font=font_main, padding=(12, 6))


def _combo(name: str, dest: str) -> str:
    return hook_common.tr("perm.suggestion.combo", name=name, dest=dest)


def get_suggestion_label(suggestion: dict) -> str:
    # Official PermissionRequest input schema puts behavior/destination at the
    # TOP LEVEL of each permission_suggestions entry:
    #   {"type": "addRules", "rules": [...], "behavior": "allow", "destination": "session"}
    # setMode entries carry "mode" instead of "behavior".
    # Older/internal payloads may nest them under "decision"; tolerate both.
    sug_type = suggestion.get("type", "")
    dest = suggestion.get("destination") or suggestion.get("decision", {}).get("destination", "")
    dest_label = hook_common.tr(f"perm.dest.{dest}", default="")
    fallback = hook_common.tr("perm.suggestion.fallback")
    if not dest_label:
        return fallback

    if sug_type == "setMode":
        mode = suggestion.get("mode") or suggestion.get("decision", {}).get("mode", "")
        mode_label = hook_common.tr(f"perm.mode.{mode}", default="")
        return _combo(mode_label, dest_label) if mode_label else fallback

    if sug_type in _VALID_RULE_TYPES:
        return _combo(hook_common.tr(f"perm.rule.{sug_type}"), dest_label)

    behavior = suggestion.get("behavior") or suggestion.get("decision", {}).get("behavior", "")
    if behavior not in _VALID_BEHAVIORS:
        return fallback
    if behavior == "ask":
        prefix = hook_common.tr("perm.prefix.ask")
    else:
        scope = "session" if dest == "session" else "always"
        prefix = hook_common.tr(f"perm.prefix.{behavior}_{scope}")
    return _combo(prefix, dest_label)


def get_suggestion_behavior(suggestion: dict) -> str:
    if suggestion.get("type") == "setMode":
        return "allow"
    return (
        suggestion.get("behavior")
        or suggestion.get("decision", {}).get("behavior", "")
        or "allow"
    )


def shorten_path(path: str) -> str:
    path = path.replace("\\", os.sep).replace("/", os.sep)
    parts = path.rstrip(os.sep).rsplit(os.sep, 1)
    if len(parts) == 2:
        return f"...{os.sep}{parts[1]}" if len(parts[0]) > 30 else path
    return path


def build_permission_message(data: dict) -> tuple[str, str]:
    tool_name = data.get("tool_name", "Unknown")
    tool_input = data.get("tool_input", {})

    if tool_name in ("Bash", "PowerShell"):
        cmd = tool_input.get("command", "")
        title = hook_common.tr("perm.title.command", tool=tool_name)
        body = cmd if cmd else hook_common.tr("perm.body.empty")
        if len(body) > 300:
            body = body[:300] + hook_common.tr("perm.body.truncated")
    elif tool_name == "Edit":
        title = hook_common.tr("perm.title.edit")
        body = shorten_path(tool_input.get("file_path", "Unknown"))
    elif tool_name == "Write":
        title = hook_common.tr("perm.title.write")
        body = shorten_path(tool_input.get("file_path", "Unknown"))
    elif tool_name == "Read":
        title = hook_common.tr("perm.title.read")
        body = shorten_path(tool_input.get("file_path", "Unknown"))
    else:
        title = hook_common.tr("perm.title.generic", tool=tool_name)
        display = {}
        for k, v in list(tool_input.items())[:5]:
            s = str(v)
            display[k] = s[:80] + "..." if len(s) > 80 else s
        body = json.dumps(display, ensure_ascii=False, indent=2)
        if len(body) > 200:
            body = body[:200] + hook_common.tr("perm.body.truncated")

    return title, body


def _deny(message: str):
    """Emit a PermissionRequest deny decision with the given reason and exit."""
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PermissionRequest",
            "decision": {"behavior": "deny", "message": message},
        }
    }, ensure_ascii=False))
    sys.exit(0)


def _center_dialog(dialog: tk.Toplevel, width: int = None, height: int = None):
    dialog.update_idletasks()
    screen_w = dialog.winfo_screenwidth()
    screen_h = dialog.winfo_screenheight()
    w = min(max(width or dialog.winfo_reqwidth(), 440), MAX_WIDTH)
    h = min(max(height or dialog.winfo_reqheight(), MIN_HEIGHT), MAX_HEIGHT)
    x = (screen_w - w) // 2
    y = (screen_h - h) // 2
    dialog.geometry(f"{w}x{h}+{x}+{y}")
    dialog.minsize(400, MIN_HEIGHT)


def show_permission_dialog(title: str, body: str, suggestions: list[dict]) -> tuple[str, dict | None]:
    root = tk.Tk()
    root.withdraw()
    _setup_style(root)

    dialog = tk.Toplevel(root)
    dialog.title(hook_common.tr("perm.window_title"))
    dialog.resizable(True, False)
    dialog.attributes("-topmost", True)

    # --- Title ---
    ttk.Label(dialog, text=title, style="Title.TLabel",
              anchor="w").pack(fill="x", padx=20, pady=(15, 8))

    ttk.Separator(dialog, orient="horizontal").pack(fill="x", padx=20)

    # --- Scrollable content ---
    content_frame = ttk.Frame(dialog)
    content_frame.pack(fill="both", expand=True, padx=10, pady=8)

    text_widget = scrolledtext.ScrolledText(
        content_frame, wrap="word", height=6,
        padx=10, pady=8, state="normal",
        font=hook_common.ui_font(10),
        relief="flat", highlightthickness=1,
        highlightbackground="#cccccc",
    )
    text_widget.pack(fill="both", expand=True)
    text_widget.insert("1.0", body)
    text_widget.configure(state="disabled")

    ttk.Separator(dialog, orient="horizontal").pack(fill="x", padx=20)

    # --- Bottom: Allow/Deny (pack FIRST with side=bottom) ---
    action_frame = ttk.Frame(dialog)
    action_frame.pack(fill="x", padx=20, pady=(10, 15), side="bottom")

    ttk.Frame(action_frame).pack(side="left", expand=True)

    result = {"behavior": None, "suggestion": None}

    def make_decision(behavior: str, suggestion: dict | None):
        result["behavior"] = behavior
        result["suggestion"] = suggestion
        dialog.destroy()

    def on_deny():
        make_decision("deny", None)

    ttk.Button(action_frame, text=hook_common.tr("perm.button.deny"), command=on_deny,
               ).pack(side="right", padx=(8, 0))

    def on_allow():
        make_decision("allow", None)

    allow_btn = ttk.Button(action_frame, text=hook_common.tr("perm.button.allow"), command=on_allow,
                           style="Accent.TButton")
    allow_btn.pack(side="right")

    allow_btn.focus_set()
    dialog.bind("<Return>", lambda e: on_allow())
    dialog.bind("<Escape>", lambda e: on_deny())
    dialog.protocol("WM_DELETE_WINDOW", on_deny)

    # --- Suggestion buttons (pack SECOND with side=bottom, above Allow/Deny) ---
    if suggestions:
        sug_frame = ttk.Frame(dialog)
        sug_frame.pack(fill="x", padx=20, side="bottom")

        ttk.Separator(sug_frame, orient="horizontal").pack(fill="x", pady=(0, 8))

        sug_inner = ttk.Frame(sug_frame)
        sug_inner.pack(anchor="w")

        labels = []
        for i, sug in enumerate(suggestions):
            sug_behavior = get_suggestion_behavior(sug)
            label = get_suggestion_label(sug)
            if sug_behavior == "deny":
                # updatedPermissions is allow-only, so a deny suggestion applies
                # to this request only. Say so instead of implying persistence.
                label += hook_common.tr("perm.suggestion.deny_note")
            labels.append((f"{i + 1}. {label}", sug_behavior, sug))

        # Fit buttons to their text instead of a fixed character width (English
        # labels are longer than Chinese ones). Drop to one column when two
        # would not fit, so nothing gets clipped.
        label_px = max(
            tkfont.Font(font=hook_common.ui_font(10)).measure(text)
            for text, _, _ in labels
        ) + 28
        max_cols = 2 if label_px * 2 + 8 <= MAX_WIDTH - 40 else 1

        for col, (text, sug_behavior, sug) in enumerate(labels):
            def on_suggestion(s=sug, b=sug_behavior):
                make_decision(b, s)

            ttk.Button(
                sug_inner, text=text, command=on_suggestion,
                style="Suggestion.TButton",
            ).grid(row=col // max_cols, column=col % max_cols,
                   padx=(0, 8), pady=(0, 4), sticky="w")

            if col + 1 <= 9:
                dialog.bind(str(col + 1), lambda e, fn=on_suggestion: fn())

    _center_dialog(dialog)
    dialog.wait_window()
    root.destroy()

    return result.get("behavior", "deny"), result.get("suggestion")


def main():
    # Test mode: skip dialog, return default allow decision.
    if os.environ.get("CLAUDE_HOOK_TEST") == "1":
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PermissionRequest",
                "decision": {"behavior": "allow"},
            }
        }, ensure_ascii=False))
        sys.exit(0)

    if hook_common.gui_disabled():
        # Leave the request to Claude Code's normal permission flow.
        sys.exit(0)

    try:
        raw = sys.stdin.buffer.read()
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        _deny("Failed to parse hook input")

    if not isinstance(data, dict):
        _deny("Invalid hook input")

    title, body = build_permission_message(data)
    raw_suggestions = data.get("permission_suggestions", [])
    # "ask" suggestions cannot be expressed as an allow/deny decision, so they
    # are dropped rather than being silently treated as allow.
    suggestions = [
        s for s in raw_suggestions
        if get_suggestion_behavior(s) in ("allow", "deny")
    ]
    try:
        lock = hook_common.acquire_dialog_lock(LOCK_WAIT_SECONDS)
        try:
            behavior, selected_suggestion = show_permission_dialog(title, body, suggestions)
        finally:
            if lock is not None:
                lock.release()
    except tk.TclError:
        # No display (headless Linux, SSH, CI): leave the flow unchanged.
        sys.exit(0)

    if behavior == "allow" and selected_suggestion:
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PermissionRequest",
                "decision": {
                    "behavior": "allow",
                    "updatedPermissions": [selected_suggestion],
                }
            }
        }
    elif behavior == "allow":
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PermissionRequest",
                "decision": {"behavior": "allow"},
            }
        }
    else:
        # updatedPermissions is allow-only per the hooks spec; a Deny never
        # applies a suggestion's rule, even if the user picked one.
        output = {
            "hookSpecificOutput": {
                "hookEventName": "PermissionRequest",
                "decision": {"behavior": "deny", "message": "Denied by user via GUI dialog"},
            }
        }

    print(json.dumps(output, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
