#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Claude Code PreToolUse hook for AskUserQuestion.

Triggered via settings.json:
  PreToolUse -> matcher: "AskUserQuestion"

Reads JSON from stdin (UTF-8), shows question dialog with ttk-themed
Checkbutton (single select with mutual exclusion) or Checkbutton (multi select).
Options whose label matches a "free-text" pattern (Other / 其他 / 自定义 / etc.)
automatically reveal a multi-line ScrolledText widget when selected, so the
user can type a custom answer.  The typed text becomes the answer value
instead of the label.

Output format (per docs):
  hookSpecificOutput:
    hookEventName: "PreToolUse"
    permissionDecision: "allow"
    updatedInput:
      questions: [...]       # echo back original
      answers: {"question text": "selected label or custom text"}
"""

import ctypes
import json
import os
import re
import sys
import tkinter as tk
from tkinter import scrolledtext, ttk

# Ensure UTF-8 output for CJK content in the JSON decision. stdin is read via
# sys.stdin.buffer.read() and decoded manually, so only stdout needs reconfiguring.
sys.stdout.reconfigure(encoding="utf-8")

# High-DPI awareness so dialogs aren't blurry on scaled displays.
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)  # per-monitor V2 (Win 8.1+)
except (AttributeError, OSError):
    try:
        ctypes.windll.user32.SetProcessDPIAware()  # legacy fallback (Vista+)
    except (AttributeError, OSError):
        pass

MAX_WIDTH = 580
MAX_HEIGHT = 560
MIN_HEIGHT = 200

# Placeholder shown in free-text Text widgets; referenced by both the focus
# in/out handlers and answer collection, so it must be a single source of truth.
_PLACEHOLDER = "\u8bf7\u8f93\u5165\u4f60\u7684\u56de\u7b54..."

# Labels that should reveal a free-text Text widget when selected.
# Case-insensitive substring match. \b on the English words prevents false
# positives like "customer" or "customary" matching "custom".
_FREE_TEXT_PATTERN = re.compile(
    r"(\bother\b|其他|自定义|\bcustom\b|自行|用户.*输入|自己.*说|输入.*内容|请.*输入|\bfill\s*in\b|\btype\s*your\b|手动)",
    re.IGNORECASE,
)


def _setup_style(root: tk.Tk):
    """Configure ttk styles for a modern, clean look."""
    style = ttk.Style(root)
    for theme in ("vista", "winnative", "clam", "default"):
        try:
            style.theme_use(theme)
            break
        except tk.TclError:
            continue

    font_main = ("Microsoft YaHei UI", 10)
    font_bold = ("Microsoft YaHei UI", 12, "bold")
    font_btn = ("Microsoft YaHei UI", 10)

    style.configure("Title.TLabel", font=font_bold, foreground="#1a1a1a")
    style.configure("Body.TLabel", font=font_main, foreground="#333333")
    style.configure("TButton", font=font_btn, padding=(16, 8))
    style.configure("Accent.TButton", font=font_btn, padding=(16, 8))
    style.configure("TCheckbutton", font=font_main)


def _is_free_text_option(label: str) -> bool:
    """Return True if this option label implies the user should type a custom value."""
    return bool(_FREE_TEXT_PATTERN.search(label))


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


def _get_text_content(widget) -> str:
    """Read text from a tk.Entry or tk.Text/ScrolledText widget, handling both APIs."""
    if isinstance(widget, tk.Text):
        return widget.get("1.0", "end-1c")
    return widget.get()


def _clear_text(widget):
    """Clear text from a tk.Entry or tk.Text/ScrolledText widget."""
    if isinstance(widget, tk.Text):
        widget.delete("1.0", tk.END)
    else:
        widget.delete(0, tk.END)


def _insert_text(widget, text: str):
    """Insert text into a tk.Entry or tk.Text/ScrolledText widget."""
    if isinstance(widget, tk.Text):
        widget.insert("1.0", text)
    else:
        widget.insert(0, text)


def _collect_answers(question_vars: list[dict]) -> dict:
    """Read answers from the live widgets. Must be called BEFORE dialog.destroy()."""
    answers = {}
    for qv in question_vars:
        entries = qv["entries"]
        options = qv["options"]
        vars_ = qv["vars"]
        multi = qv["multi"]

        def _resolve_value(i):
            entry = entries[i]
            label = options[i].get("label", "")
            if entry is not None:
                try:
                    text = _get_text_content(entry).strip()
                    if text and text != _PLACEHOLDER:
                        return text
                except Exception:
                    pass
            return label

        selected_indices = [i for i, v in enumerate(vars_) if v.get()]

        if multi:
            if selected_indices:
                answers[qv["question"]] = ", ".join(
                    _resolve_value(i) for i in selected_indices
                )
            else:
                answers[qv["question"]] = ""
        else:
            if selected_indices:
                answers[qv["question"]] = _resolve_value(selected_indices[0])
            else:
                answers[qv["question"]] = options[0].get("label", "") if options else ""
    return answers


def _deny(reason: str):
    """Emit a PreToolUse deny decision with the given reason and exit."""
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }, ensure_ascii=False))
    sys.exit(0)


def show_question_dialog(questions: list[dict]) -> dict | None:
    """
    Show dialog for AskUserQuestion format.
    Returns answers dict {question_text: label_or_custom_text} or None if cancelled.
    """
    root = tk.Tk()
    root.withdraw()
    _setup_style(root)

    dialog = tk.Toplevel(root)
    dialog.title("Claude Code \u2014 Question")
    dialog.resizable(True, True)
    dialog.attributes("-topmost", True)

    result_cancelled = {"value": False}
    result_answers = {"value": None}   # filled in on_confirm before destroy

    # --- Bottom buttons (pack FIRST so they stay visible) ---
    btn_area = ttk.Frame(dialog)
    btn_area.pack(fill="x", padx=20, pady=(10, 15), side="bottom")

    ttk.Separator(btn_area, orient="horizontal").pack(fill="x", pady=(0, 10))

    action_frame = ttk.Frame(btn_area)
    action_frame.pack(fill="x")

    ttk.Frame(action_frame).pack(side="left", expand=True)

    def on_cancel():
        result_cancelled["value"] = True
        dialog.destroy()

    ttk.Button(action_frame, text="\u2715  \u53d6\u6d88", command=on_cancel,
               ).pack(side="right", padx=(8, 0))

    def on_confirm():
        # Collect answers BEFORE destroying the dialog, so we can still
        # read Text widgets that may be inside the scrollable frame.
        result_answers["value"] = _collect_answers(question_vars)
        dialog.destroy()

    confirm_btn = ttk.Button(action_frame, text="\u2713  \u786e\u8ba4", command=on_confirm,
                             style="Accent.TButton")
    confirm_btn.pack(side="right")

    confirm_btn.focus_set()
    dialog.bind("<Return>", lambda e: on_confirm())
    dialog.bind("<Escape>", lambda e: on_cancel())
    dialog.protocol("WM_DELETE_WINDOW", on_cancel)

    # --- Title ---
    ttk.Label(dialog, text="Claude \u6709\u4e00\u4e2a\u95ee\u9898\u8981\u95ee\u4f60",
              style="Title.TLabel", anchor="w").pack(fill="x", padx=20, pady=(15, 8))

    ttk.Separator(dialog, orient="horizontal").pack(fill="x", padx=20)

    # --- Scrollable content ---
    scroll_container = ttk.Frame(dialog)
    scroll_container.pack(fill="both", expand=True)

    canvas = tk.Canvas(scroll_container, highlightthickness=0, bg="#ffffff")
    scrollbar = ttk.Scrollbar(scroll_container, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)

    scroll_frame = ttk.Frame(canvas)
    scroll_window = canvas.create_window((0, 0), window=scroll_frame, anchor="nw")

    def on_frame_configure(event):
        canvas.configure(scrollregion=canvas.bbox("all"))

    def on_canvas_configure(event):
        canvas.itemconfig(scroll_window, width=event.width)

    scroll_frame.bind("<Configure>", on_frame_configure)
    canvas.bind("<Configure>", on_canvas_configure)

    def on_mousewheel(event):
        canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    canvas.bind_all("<MouseWheel>", on_mousewheel)

    scrollbar.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)

    # --- Build questions ---
    # Each entry: {"question": str, "multi": bool, "vars": list[BooleanVar],
    #              "options": list[dict], "entries": list[tk.Text|None]}
    # entries[i] is a Text widget if the option at index i is a free-text option,
    # else None.
    question_vars: list[dict] = []

    for q_idx, q in enumerate(questions):
        q_frame = ttk.Frame(scroll_frame)
        q_frame.pack(fill="x", padx=20, pady=(12, 4))

        # Header chip — keep tk.Label for relief="groove" (ttk.Label lacks relief)
        header = q.get("header", "")
        if header:
            tk.Label(q_frame, text=header, relief="groove", bd=1,
                     padx=6, pady=2, font=("Microsoft YaHei UI", 9),
                     fg="#555555").pack(anchor="w", pady=(0, 6))

        # Question text — keep tk.Label for wraplength (ttk.Label lacks it)
        question_text = q.get("question", "")
        tk.Label(q_frame, text=question_text, wraplength=520,
                 justify="left", anchor="w",
                 font=("Microsoft YaHei UI", 10),
                 fg="#1a1a1a").pack(fill="x", anchor="w", pady=(0, 8))

        options = q.get("options", [])
        multi = q.get("multiSelect", False)

        cb_vars: list[tk.BooleanVar] = []
        entry_widgets: list[scrolledtext.ScrolledText | None] = []

        def _build_option(opt, parent_frame, vars_list, entries_list):
            """Build one option row: checkbox + optional free-text area."""
            label_text = opt.get("label", "")
            is_free = _is_free_text_option(label_text)

            var = tk.BooleanVar(value=False)
            vars_list.append(var)

            opt_frame = ttk.Frame(parent_frame)
            opt_frame.pack(fill="x", pady=(0, 2))

            cb = ttk.Checkbutton(
                opt_frame, text=label_text, variable=var,
            )
            cb.pack(anchor="w", padx=4)

            # Clicking the frame background (outside the Checkbutton widget itself)
            # should also toggle the variable.  We bind to opt_frame but ONLY act
            # when the click lands directly on opt_frame (not on a child widget like
            # the Checkbutton), to avoid double-toggling via event bubbling.
            def _make_frame_toggle(v, frame):
                def onClick(event):
                    if event.widget is frame:
                        v.set(not v.get())
                return onClick
            _toggle = _make_frame_toggle(var, opt_frame)
            opt_frame.bind("<Button-1>", _toggle)

            # Description label — keep tk.Label for wraplength
            desc = opt.get("description", "")
            if desc:
                desc_lbl = tk.Label(opt_frame, text=desc, wraplength=500,
                                    justify="left", anchor="w",
                                    font=("Microsoft YaHei UI", 9),
                                    fg="#666666")
                desc_lbl.pack(anchor="w", padx=28, pady=(0, 2))
                desc_lbl.bind("<Button-1>", lambda e, v=var: v.set(not v.get()))

            # Free-text area (hidden until the option is selected)
            if is_free:
                entry_frame = ttk.Frame(opt_frame)
                entry = scrolledtext.ScrolledText(
                    entry_frame, wrap="word", height=4, width=50,
                    font=("Microsoft YaHei UI", 10),
                    relief="flat", highlightthickness=1,
                    highlightbackground="#cccccc",
                )
                entry.pack(fill="x", padx=(0, 4))

                # Placeholder hint
                _insert_text(entry, _PLACEHOLDER)
                entry.config(fg="grey")

                def _on_focus_in(e, ent=entry, ph=_PLACEHOLDER):
                    if _get_text_content(ent) == ph:
                        _clear_text(ent)
                        ent.config(fg="black")

                def _on_focus_out(e, ent=entry, ph=_PLACEHOLDER):
                    if not _get_text_content(ent).strip():
                        _clear_text(ent)
                        _insert_text(ent, ph)
                        ent.config(fg="grey")

                entry.bind("<FocusIn>", _on_focus_in)
                entry.bind("<FocusOut>", _on_focus_out)

                # Ctrl+Enter to confirm while typing in the text area
                entry.bind("<Control-Return>", lambda e: on_confirm())

                # Show/hide based on checkbox state
                def _update_entry_visibility(v=var, ef=entry_frame, ent=entry, ph=_PLACEHOLDER):
                    if v.get():
                        ef.pack(fill="x", padx=28, pady=(2, 4))
                        # Focus the entry so user can type right away
                        ent.after(50, lambda: ent.focus_set())
                        if _get_text_content(ent) == ph:
                            _clear_text(ent)
                            ent.config(fg="black")
                    else:
                        ef.pack_forget()

                var.trace_add("write", lambda *args, fn=_update_entry_visibility: fn())
                entries_list.append(entry)
            else:
                entries_list.append(None)

        for opt in options:
            _build_option(opt, q_frame, cb_vars, entry_widgets)

        # Single-select: add mutual-exclusion traces now that all vars exist
        if not multi:
            def _make_exclusive_trace(idx, v, all_vars):
                def on_change(*args):
                    if v.get():
                        for j, v2 in enumerate(all_vars):
                            if j != idx:
                                v2.set(False)
                return on_change

            for i, var in enumerate(cb_vars):
                var.trace_add("write", _make_exclusive_trace(i, var, cb_vars))

        question_vars.append({
            "question": question_text,
            "multi": multi,
            "vars": cb_vars,
            "options": options,
            "entries": entry_widgets,
        })

        # Separator between questions
        if q_idx < len(questions) - 1:
            ttk.Separator(scroll_frame, orient="horizontal").pack(
                fill="x", padx=20, pady=(8, 0))

    _center_dialog(dialog, width=MAX_WIDTH, height=MAX_HEIGHT)
    dialog.wait_window()
    root.destroy()

    if result_cancelled["value"]:
        return None

    return result_answers["value"]


def main():
    # Test mode: skip dialog, return first option as default answer.
    if os.environ.get("CLAUDE_HOOK_TEST") == "1":
        try:
            raw = sys.stdin.buffer.read()
            data = json.loads(raw.decode("utf-8")) if raw else {}
        except Exception:
            data = {}
        tool_input = data.get("tool_input", {}) if isinstance(data, dict) else {}
        questions = tool_input.get("questions", [])
        answers = {q.get("question", ""): (q.get("options", [{}])[0].get("label", "") if q.get("options") else "") for q in questions}
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow",
                "updatedInput": {
                    "questions": questions,
                    "answers": answers,
                }
            }
        }, ensure_ascii=False))
        sys.exit(0)

    try:
        raw = sys.stdin.buffer.read()
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        _deny("Failed to parse hook input")

    if not isinstance(data, dict):
        _deny("Invalid hook input")

    tool_input = data.get("tool_input", {})
    questions = tool_input.get("questions", [])

    if not questions:
        _deny("No questions found in input")

    answers = show_question_dialog(questions)

    if answers is None:
        _deny("User cancelled the question dialog")

    # Per docs: echo back original questions + add answers
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "updatedInput": {
                "questions": questions,
                "answers": answers,
            }
        }
    }, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
