#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Interactive preview script — pops up REAL hook dialogs with realistic data.

Usage:
    python tests/interactive_preview.py

No CLAUDE_HOOK_TEST env var is set, so the hooks show actual tkinter/ttk UIs.
After each dialog, the script prints the JSON the hook would return to Claude Code.

Press Ctrl+C to quit early.
"""

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "hooks"
PYTHON = sys.executable


def run_hook_interactive(script_name: str, event: dict, timeout: int = 120):
    """Run a hook script WITHOUT test mode — real dialog will pop up."""
    script_path = HOOKS_DIR / script_name
    env = {
        "PATH": __import__("os").environ.get("PATH", ""),
        "PYTHONIOENCODING": "utf-8",
        # Intentionally NOT setting CLAUDE_HOOK_TEST
    }
    # Copy over minimal env for tkinter to work
    for key in ("SYSTEMROOT", "TEMP", "TMP", "HOME", "USERPROFILE", "APPDATA"):
        val = __import__("os").environ.get(key)
        if val:
            env[key] = val

    print(f"\n{'='*60}")
    print(f"  Launching: {script_name}")
    print(f"  Event: {json.dumps(event, ensure_ascii=False, indent=2)[:500]}")
    print(f"  >>> A dialog should pop up. Interact with it. <<<")
    print(f"{'='*60}\n")

    result = subprocess.run(
        [PYTHON, str(script_path)],
        input=json.dumps(event).encode("utf-8"),
        capture_output=True,
        timeout=timeout,
        env=env,
    )

    stdout = result.stdout.decode("utf-8", "replace")
    stderr = result.stderr.decode("utf-8", "replace")

    if stdout:
        try:
            payload = json.loads(stdout)
            print(f"  OUTPUT JSON:")
            print(f"  {json.dumps(payload, ensure_ascii=False, indent=2)}")
        except json.JSONDecodeError:
            print(f"  RAW STDOUT: {stdout}")
    if stderr:
        print(f"  STDERR: {stderr}")
    print(f"  Return code: {result.returncode}")
    print()

    return result


# ──────────────────────────────────────────────────────
# Scenario 1: Bash command, no suggestions (basic Allow/Deny)
# ──────────────────────────────────────────────────────
SCENARIO_1 = {
    "tool_name": "Bash",
    "tool_input": {"command": "git add -A && git commit -m 'feat: upgrade hooks to ttk'"},
    "permission_suggestions": [],
}

# ──────────────────────────────────────────────────────
# Scenario 2: Bash command with ALL suggestion types
#   Tests: session / localSettings / userSettings labels
# ──────────────────────────────────────────────────────
SCENARIO_2 = {
    "tool_name": "Bash",
    "tool_input": {"command": "npm install"},
    "permission_suggestions": [
        {"type": "addRules", "behavior": "allow", "destination": "session",
         "rules": [{"tool": "Bash", "command": "npm *"}]},
        {"type": "addRules", "behavior": "allow", "destination": "localSettings",
         "rules": [{"tool": "Bash", "command": "npm *"}]},
        {"type": "addRules", "behavior": "allow", "destination": "userSettings",
         "rules": [{"tool": "Bash", "command": "npm *"}]},
        {"type": "addRules", "behavior": "deny", "destination": "session",
         "rules": [{"tool": "Bash", "command": "npm *"}]},
    ],
}

# ──────────────────────────────────────────────────────
# Scenario 3: Edit file (truncated path display)
# ──────────────────────────────────────────────────────
SCENARIO_3 = {
    "tool_name": "Edit",
    "tool_input": {"file_path": "src/components/UserProfile/SettingsPanel.tsx"},
    "permission_suggestions": [
        {"type": "addRules", "behavior": "allow", "destination": "session"},
        {"type": "addRules", "behavior": "allow", "destination": "localSettings"},
    ],
}

# ──────────────────────────────────────────────────────
# Scenario 4: Write file with long path
# ──────────────────────────────────────────────────────
SCENARIO_4 = {
    "tool_name": "Write",
    "tool_input": {"file_path": "/very/long/path/to/some/deeply/nested/module/output.ts"},
    "permission_suggestions": [
        {"type": "setMode", "behavior": "auto", "destination": "session"},
        {"type": "setMode", "behavior": "plan", "destination": "session"},
    ],
}

# ──────────────────────────────────────────────────────
# Scenario 5: AskUserQuestion — single select, no free text
# ──────────────────────────────────────────────────────
SCENARIO_5 = {
    "tool_name": "AskUserQuestion",
    "tool_input": {
        "questions": [
            {
                "question": "Which testing framework should we use?",
                "header": "Framework",
                "options": [
                    {"label": "pytest", "description": "Python standard, great fixtures"},
                    {"label": "unittest", "description": "Built-in, no dependencies"},
                    {"label": "nox", "description": "Session-based testing across environments"},
                ],
                "multiSelect": False,
            }
        ]
    },
}

# ──────────────────────────────────────────────────────
# Scenario 6: AskUserQuestion — multi select + free text option
#   Tests: multi-select checkboxes + ScrolledText for "Other"
# ──────────────────────────────────────────────────────
SCENARIO_6 = {
    "tool_name": "AskUserQuestion",
    "tool_input": {
        "questions": [
            {
                "question": "Which features do you want to enable?",
                "header": "Features",
                "multiSelect": True,
                "options": [
                    {"label": "Dark mode", "description": "Auto-switch based on system theme"},
                    {"label": "Notifications", "description": "Desktop notifications on task completion"},
                    {"label": "Auto-save", "description": "Save every 30 seconds"},
                    {"label": "其他 (Other)", "description": "Type your own answer"},
                ],
            }
        ]
    },
}

# ──────────────────────────────────────────────────────
# Scenario 7: AskUserQuestion — two questions in one dialog
# ──────────────────────────────────────────────────────
SCENARIO_7 = {
    "tool_name": "AskUserQuestion",
    "tool_input": {
        "questions": [
            {
                "question": "Which library should we use for HTTP?",
                "header": "HTTP Lib",
                "multiSelect": False,
                "options": [
                    {"label": "requests", "description": "Most popular, easy to use"},
                    {"label": "httpx", "description": "Async support, HTTP/2"},
                    {"label": "aiohttp", "description": "Async-first, server + client"},
                ],
            },
            {
                "question": "What's the target Python version?",
                "header": "Python Ver",
                "multiSelect": False,
                "options": [
                    {"label": "3.10", "description": "Minimum for modern type hints"},
                    {"label": "3.12", "description": "Latest stable, perf improvements"},
                    {"label": "自定义", "description": "Enter your own version"},
                ],
            }
        ]
    },
}


SCENARIOS = [
    ("PermissionRequest — Bash, no suggestions (basic Allow/Deny)", "permission_request.py", SCENARIO_1),
    ("PermissionRequest — Bash, ALL suggestion types (label check)", "permission_request.py", SCENARIO_2),
    ("PermissionRequest — Edit file (path display)", "permission_request.py", SCENARIO_3),
    ("PermissionRequest — Write file + setMode suggestions", "permission_request.py", SCENARIO_4),
    ("AskUserQuestion — single select, 3 options", "ask_user_question.py", SCENARIO_5),
    ("AskUserQuestion — multi select + free text (Other)", "ask_user_question.py", SCENARIO_6),
    ("AskUserQuestion — two questions, one with free text", "ask_user_question.py", SCENARIO_7),
]


def main():
    print("=" * 60)
    print("  Claude Code Hooks — Interactive Preview")
    print("  Each scenario pops up a REAL dialog. Click buttons to see")
    print("  the JSON output the hook returns to Claude Code.")
    print("  Press Ctrl+C at any time to stop.")
    print("=" * 60)

    for i, (desc, script, event) in enumerate(SCENARIOS, 1):
        print(f"\n{'─'*60}")
        print(f"  Scenario {i}/{len(SCENARIOS)}: {desc}")
        print(f"{'─'*60}")

        try:
            run_hook_interactive(script, event)
        except subprocess.TimeoutExpired:
            print(f"  ⏱  Timed out after 120s — skipping to next scenario.")
        except KeyboardInterrupt:
            print(f"\n  Stopped by user.")
            break

        if i < len(SCENARIOS):
            print(f"  Press Enter for next scenario, or Ctrl+C to stop...")
            try:
                input()
            except KeyboardInterrupt:
                print(f"\n  Stopped by user.")
                break

    print(f"\n{'='*60}")
    print("  All scenarios complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
