#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Claude Code PreToolUse hook for AskUserQuestion.

Triggered via settings.json:
  PreToolUse -> matcher: "AskUserQuestion"

Reads JSON from stdin (UTF-8), shows question dialog with native
Checkbutton (single select with mutual exclusion) or Checkbutton (multi select).
Options whose label matches a "free-text" pattern (Other / 其他 / 自定义 / etc.)
automatically reveal an Entry widget when selected, so the user can type a
custom answer.  The typed text becomes the answer value instead of the label.

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
import re
import sys
import tkinter as tk

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

# Placeholder shown in free-text Entry widgets; referenced by both the focus
# in/out handlers and answer collection, so it must be a single source of truth.
_PLACEHOLDER = "Type your answer here..."

# Labels that should reveal a free-text Entry when selected.
# Case-insensitive substring match. \b on the English words prevents false
# positives like "customer" or "customary" matching "custom".
_FREE_TEXT_PATTERN = re.compile(
    r"(\bother\b|其他|自定义|\bcustom\b|自行|用户.*输入|自己.*说|输入.*内容|请.*输入|\bfill\s*in\b|\btype\s*your\b|手动)",
    re.IGNORECASE,
)


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
                    text = entry.get().strip()
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

    dialog = tk.Toplevel(root)
    dialog.title("Claude Code \u2014 Question")
    dialog.resizable(True, True)
    dialog.attributes("-topmost", True)

    result_cancelled = {"value": False}
    result_answers = {"value": None}   # filled in on_confirm before destroy

    # --- Bottom buttons (pack FIRST so they stay visible) ---
    btn_area = tk.Frame(dialog)
    btn_area.pack(fill="x", padx=20, pady=(10, 15), side="bottom")

    tk.Frame(btn_area, height=1, relief="sunken", bd=1).pack(fill="x", pady=(0, 10))

    action_frame = tk.Frame(btn_area)
    action_frame.pack(fill="x")

    tk.Frame(action_frame).pack(side="left", expand=True)

    def on_cancel():
        result_cancelled["value"] = True
        dialog.destroy()

    tk.Button(action_frame, text="\u2715  Cancel", command=on_cancel,
              padx=18, pady=6).pack(side="right", padx=(8, 0))

    def on_confirm():
        # Collect answers BEFORE destroying the dialog, so we can still
        # read Entry widgets that may be inside the scrollable frame.
        result_answers["value"] = _collect_answers(question_vars)
        dialog.destroy()

    confirm_btn = tk.Button(action_frame, text="\u2713  Confirm", command=on_confirm,
                            padx=18, pady=6)
    confirm_btn.pack(side="right")

    confirm_btn.focus_set()
    dialog.bind("<Return>", lambda e: on_confirm())
    dialog.bind("<Escape>", lambda e: on_cancel())
    dialog.protocol("WM_DELETE_WINDOW", on_cancel)

    # --- Title ---
    tk.Label(dialog, text="Claude is asking a question",
             anchor="w").pack(fill="x", padx=20, pady=(15, 8))

    tk.Frame(dialog, height=1, relief="sunken", bd=1).pack(fill="x", padx=20)

    # --- Scrollable content ---
    scroll_container = tk.Frame(dialog)
    scroll_container.pack(fill="both", expand=True)

    canvas = tk.Canvas(scroll_container, highlightthickness=0)
    scrollbar = tk.Scrollbar(scroll_container, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scrollbar.set)

    scroll_frame = tk.Frame(canvas)
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
    #              "options": list[dict], "entries": list[tk.Entry|None]}
    # entries[i] is an Entry widget if the option at index i is a free-text option,
    # else None.
    question_vars: list[dict] = []

    for q_idx, q in enumerate(questions):
        q_frame = tk.Frame(scroll_frame)
        q_frame.pack(fill="x", padx=20, pady=(12, 4))

        # Header chip
        header = q.get("header", "")
        if header:
            tk.Label(q_frame, text=header, relief="groove", bd=1,
                     padx=6, pady=2).pack(anchor="w", pady=(0, 6))

        # Question text
        question_text = q.get("question", "")
        tk.Label(q_frame, text=question_text, wraplength=520,
                 justify="left", anchor="w").pack(fill="x", anchor="w", pady=(0, 8))

        options = q.get("options", [])
        multi = q.get("multiSelect", False)

        cb_vars: list[tk.BooleanVar] = []
        entry_widgets: list[tk.Entry | None] = []

        def _build_option(opt, parent_frame, vars_list, entries_list):
            """Build one option row: checkbox + optional free-text entry."""
            label_text = opt.get("label", "")
            is_free = _is_free_text_option(label_text)

            var = tk.BooleanVar(value=False)
            vars_list.append(var)

            opt_frame = tk.Frame(parent_frame)
            opt_frame.pack(fill="x", pady=(0, 2))

            cb = tk.Checkbutton(
                opt_frame, text=label_text, variable=var,
                anchor="w", wraplength=520,
            )
            cb.pack(anchor="w", padx=4)

            # Clicking anywhere on the option row toggles the checkbox,
            # so define the handler up front and reuse it for the frame,
            # the checkbutton label, and the description label below.
            def _make_frame_toggle(v):
                def onClick(event):
                    v.set(not v.get())
                return onClick
            _toggle = _make_frame_toggle(var)
            opt_frame.bind("<Button-1>", _toggle)
            cb.bind("<Button-1>", lambda e, fn=_toggle: fn(e))

            # Description label
            desc = opt.get("description", "")
            if desc:
                desc_lbl = tk.Label(opt_frame, text=desc, wraplength=500,
                                    justify="left", anchor="w")
                desc_lbl.pack(anchor="w", padx=28, pady=(0, 2))
                desc_lbl.bind("<Button-1>", _toggle)

            # Free-text entry (hidden until the option is selected)
            if is_free:
                entry_frame = tk.Frame(opt_frame)
                entry = tk.Entry(entry_frame, width=46)
                entry.pack(side="left", padx=(0, 4))

                # Placeholder hint
                entry.insert(0, _PLACEHOLDER)
                entry.config(fg="grey")

                def _on_focus_in(e, ent=entry, ph=_PLACEHOLDER):
                    if ent.get() == ph:
                        ent.delete(0, tk.END)
                        ent.config(fg="black")

                def _on_focus_out(e, ent=entry, ph=_PLACEHOLDER):
                    if not ent.get():
                        ent.insert(0, ph)
                        ent.config(fg="grey")

                entry.bind("<FocusIn>", _on_focus_in)
                entry.bind("<FocusOut>", _on_focus_out)

                # Show/hide based on checkbox state
                def _update_entry_visibility(v=var, ef=entry_frame, ent=entry, ph=_PLACEHOLDER):
                    if v.get():
                        ef.pack(anchor="w", padx=28, pady=(2, 4))
                        # Focus the entry so user can type right away
                        ent.after(50, lambda: ent.focus_set())
                        if ent.get() == ph:
                            ent.delete(0, tk.END)
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
            tk.Frame(scroll_frame, height=1, relief="sunken", bd=1).pack(
                fill="x", padx=20, pady=(8, 0))

    _center_dialog(dialog, width=MAX_WIDTH, height=MAX_HEIGHT)
    dialog.wait_window()
    root.destroy()

    if result_cancelled["value"]:
        return None

    return result_answers["value"]


def main():
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
