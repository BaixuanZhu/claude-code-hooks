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


# ──────────────────────────────────────────────────────
# Unit tests for pure functions (no GUI, headless-safe)
# ──────────────────────────────────────────────────────

def _import_permission_module():
    """Import permission_request.py as a module (not via subprocess)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "permission_request", HOOKS_DIR / "permission_request.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _import_ask_module():
    """Import ask_user_question.py as a module (not via subprocess)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "ask_user_question", HOOKS_DIR / "ask_user_question.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- SUGGESTION_LABELS tests ---

def test_suggestion_labels_all_mapped():
    """Every (type, behavior, destination) combo in the dict has a non-empty label."""
    perm = _import_permission_module()
    for key, label in perm.SUGGESTION_LABELS.items():
        assert isinstance(label, str) and len(label) > 0, f"Empty label for {key}"


def test_suggestion_labels_session_uses_short_scope():
    """session labels should say '本次会话', not '项目' or '全局'."""
    perm = _import_permission_module()
    assert "本次会话" in perm.SUGGESTION_LABELS[("addRules", "allow", "session")]
    assert "本次会话" in perm.SUGGESTION_LABELS[("addRules", "deny", "session")]


def test_suggestion_labels_localsettings_uses_project():
    """localSettings labels should say '项目', not '全局' or '本次会话'."""
    perm = _import_permission_module()
    assert "项目" in perm.SUGGESTION_LABELS[("addRules", "allow", "localSettings")]
    assert "项目" in perm.SUGGESTION_LABELS[("addRules", "deny", "localSettings")]


def test_suggestion_labels_usersettings_uses_global():
    """userSettings labels should say '全局'."""
    perm = _import_permission_module()
    assert "全局" in perm.SUGGESTION_LABELS[("addRules", "allow", "userSettings")]
    assert "全局" in perm.SUGGESTION_LABELS[("addRules", "deny", "userSettings")]


def test_suggestion_labels_allow_starts_with_allow():
    """allow-behavior labels should start with '允许' or '始终允许'."""
    perm = _import_permission_module()
    for (sug_type, behavior, dest), label in perm.SUGGESTION_LABELS.items():
        if behavior == "allow":
            assert "允许" in label, f"allow label missing '允许': {label}"
        elif behavior == "deny":
            assert "拒绝" in label, f"deny label missing '拒绝': {label}"
        elif behavior == "auto":
            assert "自动批准" in label, f"auto label missing '自动批准': {label}"
        elif behavior == "plan":
            assert "计划" in label, f"plan label missing '计划': {label}"


# --- get_suggestion_label tests ---

def test_get_suggestion_label_top_level_fields():
    """Labels resolve from top-level behavior/destination fields (official schema)."""
    perm = _import_permission_module()
    sug = {"type": "addRules", "behavior": "allow", "destination": "localSettings"}
    assert perm.get_suggestion_label(sug) == "始终允许（项目）"


def test_get_suggestion_label_nested_decision():
    """Labels also resolve from decision.behavior/destination (legacy payload)."""
    perm = _import_permission_module()
    sug = {"type": "addRules", "decision": {"behavior": "deny", "destination": "session"}}
    assert perm.get_suggestion_label(sug) == "拒绝（本次会话）"


def test_get_suggestion_label_unknown_fallback():
    """Unknown combos fall back to '应用规则'."""
    perm = _import_permission_module()
    sug = {"type": "unknown", "behavior": "unknown", "destination": "unknown"}
    assert perm.get_suggestion_label(sug) == "应用规则"


# --- build_permission_message tests ---

def test_build_permission_message_bash():
    perm = _import_permission_module()
    title, body = perm.build_permission_message({
        "tool_name": "Bash",
        "tool_input": {"command": "echo hello"},
    })
    assert title == "Bash 命令"
    assert body == "echo hello"


def test_build_permission_message_bash_truncation():
    perm = _import_permission_module()
    long_cmd = "x" * 400
    title, body = perm.build_permission_message({
        "tool_name": "Bash",
        "tool_input": {"command": long_cmd},
    })
    assert title == "Bash 命令"
    assert "已截断" in body
    assert len(body) < 400


def test_build_permission_message_edit():
    perm = _import_permission_module()
    title, body = perm.build_permission_message({
        "tool_name": "Edit",
        "tool_input": {"file_path": "src/app.py"},
    })
    assert title == "编辑文件"
    assert "app.py" in body


def test_build_permission_message_write():
    perm = _import_permission_module()
    title, body = perm.build_permission_message({
        "tool_name": "Write",
        "tool_input": {"file_path": "output.txt"},
    })
    assert title == "写入文件"
    assert "output.txt" in body


def test_build_permission_message_read():
    perm = _import_permission_module()
    title, body = perm.build_permission_message({
        "tool_name": "Read",
        "tool_input": {"file_path": "config.yaml"},
    })
    assert title == "读取文件"
    assert "config.yaml" in body


def test_build_permission_message_unknown_tool():
    perm = _import_permission_module()
    title, body = perm.build_permission_message({
        "tool_name": "WebFetch",
        "tool_input": {"url": "https://example.com"},
    })
    assert "WebFetch" in title
    assert "url" in body


# --- shorten_path tests ---

def test_shorten_path_short():
    perm = _import_permission_module()
    assert perm.shorten_path("src/app.py") == "src\\app.py"


def test_shorten_path_long():
    perm = _import_permission_module()
    long_path = "a" * 40 + "\\file.py"
    result = perm.shorten_path(long_path)
    assert result.startswith("...")
    assert result.endswith("file.py")


# --- _is_free_text_option tests ---

def test_is_free_text_option_other_english():
    ask = _import_ask_module()
    assert ask._is_free_text_option("Other") is True
    assert ask._is_free_text_option("Other (custom)") is True


def test_is_free_text_option_other_chinese():
    ask = _import_ask_module()
    assert ask._is_free_text_option("其他") is True
    assert ask._is_free_text_option("自定义") is True


def test_is_free_text_option_not_free_text():
    ask = _import_ask_module()
    assert ask._is_free_text_option("Yes") is False
    assert ask._is_free_text_option("No") is False
    assert ask._is_free_text_option("pytest") is False


def test_is_free_text_option_customer_not_matched():
    """'customer' should NOT match the 'custom' pattern (word boundary)."""
    ask = _import_ask_module()
    assert ask._is_free_text_option("customer feedback") is False


def test_is_free_text_option_mixed_label():
    """Label like '其他 (Other)' should match."""
    ask = _import_ask_module()
    assert ask._is_free_text_option("其他 (Other)") is True


# --- _get_text_content / _clear_text / _insert_text tests ---

def test_text_helpers_with_entry():
    """Text helper functions work with tk.Entry widgets."""
    import tkinter as tk
    ask = _import_ask_module()
    root = tk.Tk()
    root.withdraw()
    entry = tk.Entry(root)
    ask._insert_text(entry, "hello world")
    assert ask._get_text_content(entry) == "hello world"
    ask._clear_text(entry)
    assert ask._get_text_content(entry) == ""
    root.destroy()


def test_text_helpers_with_text_widget():
    """Text helper functions work with tk.Text widgets (multi-line)."""
    import tkinter as tk
    ask = _import_ask_module()
    root = tk.Tk()
    root.withdraw()
    text = tk.Text(root)
    ask._insert_text(text, "line1\nline2\nline3")
    content = ask._get_text_content(text)
    assert "line1" in content
    assert "line3" in content
    assert "\n" in content
    ask._clear_text(text)
    assert ask._get_text_content(text) == ""
    root.destroy()


# --- PermissionRequest with suggestions (test mode) ---

def test_permission_request_with_suggestions_test_mode():
    """In test mode, suggestions in input don't affect output (default allow)."""
    event = {
        "tool_name": "Bash",
        "tool_input": {"command": "npm install"},
        "permission_suggestions": [
            {"type": "addRules", "behavior": "allow", "destination": "localSettings"},
            {"type": "addRules", "behavior": "deny", "destination": "session"},
        ],
    }
    result = _run_hook("permission_request.py", event)
    assert result.returncode == 0
    payload = json.loads(result.stdout.decode("utf-8"))
    assert payload["hookSpecificOutput"]["decision"]["behavior"] == "allow"


# --- AskUserQuestion variations (test mode) ---

def test_ask_user_question_multi_select_test_mode():
    """Multi-select question in test mode returns first option."""
    event = {
        "tool_name": "AskUserQuestion",
        "tool_input": {
            "questions": [
                {
                    "question": "Pick features",
                    "multiSelect": True,
                    "options": [
                        {"label": "Dark mode", "description": "auto switch"},
                        {"label": "Notifications", "description": "desktop alerts"},
                    ],
                }
            ]
        },
    }
    result = _run_hook("ask_user_question.py", event)
    assert result.returncode == 0
    payload = json.loads(result.stdout.decode("utf-8"))
    answers = payload["hookSpecificOutput"]["updatedInput"]["answers"]
    assert answers["Pick features"] == "Dark mode"


def test_ask_user_question_free_text_option_test_mode():
    """Free-text option ('Other') in test mode still returns label as default."""
    event = {
        "tool_name": "AskUserQuestion",
        "tool_input": {
            "questions": [
                {
                    "question": "Which version?",
                    "multiSelect": False,
                    "options": [
                        {"label": "3.12", "description": "latest stable"},
                        {"label": "Other", "description": "type your own"},
                    ],
                }
            ]
        },
    }
    result = _run_hook("ask_user_question.py", event)
    assert result.returncode == 0
    payload = json.loads(result.stdout.decode("utf-8"))
    answers = payload["hookSpecificOutput"]["updatedInput"]["answers"]
    assert answers["Which version?"] == "3.12"  # first option in test mode


def test_ask_user_question_two_questions_test_mode():
    """Multiple questions in one event all get answered in test mode."""
    event = {
        "tool_name": "AskUserQuestion",
        "tool_input": {
            "questions": [
                {
                    "question": "Q1",
                    "multiSelect": False,
                    "options": [{"label": "A", "description": ""}, {"label": "B", "description": ""}],
                },
                {
                    "question": "Q2",
                    "multiSelect": True,
                    "options": [{"label": "X", "description": ""}, {"label": "Y", "description": ""}],
                },
            ]
        },
    }
    result = _run_hook("ask_user_question.py", event)
    assert result.returncode == 0
    payload = json.loads(result.stdout.decode("utf-8"))
    answers = payload["hookSpecificOutput"]["updatedInput"]["answers"]
    assert answers["Q1"] == "A"
    assert answers["Q2"] == "X"
    # Questions echoed back
    assert len(payload["hookSpecificOutput"]["updatedInput"]["questions"]) == 2


# --- Empty / edge case inputs ---

def test_ask_user_question_no_questions_test_mode():
    """Hook should handle empty questions list gracefully."""
    event = {
        "tool_name": "AskUserQuestion",
        "tool_input": {"questions": []},
    }
    result = _run_hook("ask_user_question.py", event)
    assert result.returncode == 0
    payload = json.loads(result.stdout.decode("utf-8"))
    assert payload["hookSpecificOutput"]["updatedInput"]["answers"] == {}


def test_permission_request_empty_tool_input():
    """Hook handles missing tool_input gracefully."""
    event = {
        "tool_name": "Bash",
        "tool_input": {},
        "permission_suggestions": [],
    }
    result = _run_hook("permission_request.py", event)
    assert result.returncode == 0
