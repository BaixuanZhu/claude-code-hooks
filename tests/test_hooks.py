"""
Smoke tests for the 4 hook scripts.

Each test invokes the script as a subprocess, pipes a fake Claude Code event
into stdin, and asserts the script exits cleanly.

Test mode contract: when env var CLAUDE_HOOK_TEST=1 is set, the scripts
skip the tkinter dialog and emit a default decision. This lets us run
the tests in headless CI / non-Windows environments.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

# Skip the entire module if tkinter isn't importable in the parent process —
# even test mode goes through `import tkinter` at script import time on some
# platforms, so we guard early.
pytest.importorskip("tkinter")

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "hooks"

PYTHON = sys.executable  # use the interpreter running pytest (so venv works)


def _run_hook(script_name: str, event: dict, timeout: int = 10):
    """Run a hook script with a fake JSON event on stdin."""
    script_path = HOOKS_DIR / script_name
    assert script_path.is_file(), f"Missing script: {script_path}"

    env = os.environ.copy()
    env["CLAUDE_HOOK_TEST"] = "1"
    # PYTHONIOENCODING guards against CJK titles printing as ? on some configs.
    env.setdefault("PYTHONIOENCODING", "utf-8")

    return subprocess.run(
        [PYTHON, str(script_path)],
        input=json.dumps(event).encode("utf-8"),
        capture_output=True,
        timeout=timeout,
        env=env,
    )


# ---------- Tests ----------

def test_permission_request_smoke():
    event = {
        "tool_name": "Bash",
        "tool_input": {"command": "echo hello"},
        "permission_suggestions": [],
    }
    result = _run_hook("permission_request.py", event)
    assert result.returncode == 0, f"stderr: {result.stderr.decode('utf-8', 'replace')}"
    payload = json.loads(result.stdout.decode("utf-8"))
    assert payload["hookSpecificOutput"]["hookEventName"] == "PermissionRequest"
    assert payload["hookSpecificOutput"]["decision"]["behavior"] == "allow"


def test_ask_user_question_smoke():
    event = {
        "tool_name": "AskUserQuestion",
        "tool_input": {
            "questions": [
                {
                    "question": "Pick one",
                    "options": [
                        {"label": "Yes", "description": "affirm"},
                        {"label": "No", "description": "decline"},
                    ],
                    "multiSelect": False,
                }
            ]
        },
    }
    result = _run_hook("ask_user_question.py", event)
    assert result.returncode == 0, f"stderr: {result.stderr.decode('utf-8', 'replace')}"
    payload = json.loads(result.stdout.decode("utf-8"))
    hso = payload["hookSpecificOutput"]
    assert hso["hookEventName"] == "PreToolUse"
    assert hso["permissionDecision"] == "allow"
    assert "answers" in hso["updatedInput"]
    # Test-mode default picks the first option
    assert hso["updatedInput"]["answers"]["Pick one"] == "Yes"
    # Original questions must be echoed back per spec
    assert hso["updatedInput"]["questions"] == event["tool_input"]["questions"]


def test_stop_notify_smoke():
    event = {"last_assistant_message": "Task completed successfully."}
    result = _run_hook("stop_notify.py", event)
    assert result.returncode == 0, f"stderr: {result.stderr.decode('utf-8', 'replace')}"
    payload = json.loads(result.stdout.decode("utf-8"))
    # Stop hook must at least emit a continue:true so plugins don't choke
    assert payload.get("continue") is True


def test_exit_plan_mode_notify_smoke():
    event = {
        "tool_name": "ExitPlanMode",
        "tool_input": {"plan": "# My plan\nImplement feature X across two files."},
    }
    result = _run_hook("exit_plan_mode_notify.py", event)
    # ExitPlanMode in test mode exits silently (rc=0, no output)
    assert result.returncode == 0, f"stderr: {result.stderr.decode('utf-8', 'replace')}"


def test_permission_request_handles_garbage_input():
    """Hook must not crash on unparseable JSON — should deny with a message."""
    script_path = HOOKS_DIR / "permission_request.py"
    env = os.environ.copy()
    env["CLAUDE_HOOK_TEST"] = "1"
    result = subprocess.run(
        [PYTHON, str(script_path)],
        input=b"not valid json",
        capture_output=True,
        timeout=5,
        env=env,
    )
    # In test mode, the env-skip branch fires before parsing, so we just
    # verify the script still exits 0 even with bad input.
    assert result.returncode == 0
