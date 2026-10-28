"""
Smoke and unit tests for the hook scripts.

Each smoke test invokes the script as a subprocess, pipes a fake Claude Code
event into stdin, and asserts the script exits cleanly.

Test mode contract: when env var CLAUDE_HOOK_TEST=1 is set, the scripts
skip the tkinter dialog and emit a default decision. This lets us run
the tests in headless CI / non-Windows environments.
"""

import json
import os
import string
import subprocess
import sys
import time
from pathlib import Path

import pytest

# Skip the entire module if tkinter isn't importable in the parent process —
# even test mode goes through `import tkinter` at script import time on some
# platforms, so we guard early.
pytest.importorskip("tkinter")

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "hooks"

PYTHON = sys.executable  # use the interpreter running pytest (so venv works)

sys.path.insert(0, str(HOOKS_DIR))
import hook_common  # noqa: E402


@pytest.fixture(autouse=True)
def _pin_test_language():
    """Pin UI language to English so assertions don't depend on host locale."""
    hook_common.set_language("en")
    yield
    hook_common.set_language(None)


def _run_hook(script_name: str, event: dict, timeout: int = 10,
              extra_env: dict | None = None, test_mode: bool = True):
    """Run a hook script with a fake JSON event on stdin."""
    script_path = HOOKS_DIR / script_name
    assert script_path.is_file(), f"Missing script: {script_path}"

    env = os.environ.copy()
    env.pop("CI", None)  # keep ambient CI from short-circuiting GUI hooks
    if test_mode:
        env["CLAUDE_HOOK_TEST"] = "1"
    else:
        env.pop("CLAUDE_HOOK_TEST", None)
    # PYTHONIOENCODING guards against CJK titles printing as ? on some configs.
    env.setdefault("PYTHONIOENCODING", "utf-8")
    if extra_env:
        env.update(extra_env)

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
    # Notification-only and async: the hook must stay silent on stdout.
    assert result.stdout.strip() == b""


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


def _import_stop_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "stop_notify", HOOKS_DIR / "stop_notify.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _import_notification_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "notification_notify", HOOKS_DIR / "notification_notify.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- Suggestion label tests ---

def test_suggestion_labels_cover_all_combinations():
    """Every (type, behavior/mode, destination) combo resolves to a real label."""
    perm = _import_permission_module()
    fallback = hook_common.tr("perm.suggestion.fallback")
    suggestions = []
    for dest in ("session", "localSettings", "projectSettings", "userSettings"):
        for behavior in ("allow", "deny", "ask"):
            suggestions.append({"type": "addRules", "behavior": behavior, "destination": dest})
        for mode in ("default", "manual", "auto", "acceptEdits", "dontAsk",
                     "bypassPermissions", "plan"):
            suggestions.append({"type": "setMode", "mode": mode, "destination": dest})
        for rule_type in ("replaceRules", "removeRules", "addDirectories", "removeDirectories"):
            suggestions.append({"type": rule_type, "destination": dest})
    for sug in suggestions:
        label = perm.get_suggestion_label(sug)
        assert label and label != fallback, f"unmapped suggestion: {sug}"


def test_suggestion_labels_chinese_scope_wording():
    perm = _import_permission_module()
    hook_common.set_language("zh")
    assert "本次会话" in perm.get_suggestion_label(
        {"type": "addRules", "behavior": "allow", "destination": "session"})
    assert "本地项目" in perm.get_suggestion_label(
        {"type": "addRules", "behavior": "deny", "destination": "localSettings"})
    assert "共享项目" in perm.get_suggestion_label(
        {"type": "addRules", "behavior": "allow", "destination": "projectSettings"})
    assert "全局" in perm.get_suggestion_label(
        {"type": "addRules", "behavior": "allow", "destination": "userSettings"})
    assert "始终允许" in perm.get_suggestion_label(
        {"type": "addRules", "behavior": "allow", "destination": "userSettings"})


def test_suggestion_labels_english():
    perm = _import_permission_module()
    assert perm.get_suggestion_label(
        {"type": "addRules", "behavior": "allow", "destination": "localSettings"}
    ) == "Always allow (local project)"
    assert perm.get_suggestion_label(
        {"type": "addRules", "behavior": "deny", "destination": "session"}
    ) == "Deny (this session)"
    assert perm.get_suggestion_label(
        {"type": "replaceRules", "destination": "userSettings"}
    ) == "Replace rules (global)"


# --- get_suggestion_label tests ---

def test_get_suggestion_label_top_level_fields():
    """Labels resolve from top-level behavior/destination fields (official schema)."""
    perm = _import_permission_module()
    hook_common.set_language("zh")
    sug = {"type": "addRules", "behavior": "allow", "destination": "localSettings"}
    assert perm.get_suggestion_label(sug) == "始终允许（本地项目）"


def test_get_suggestion_label_nested_decision():
    """Labels also resolve from decision.behavior/destination (legacy payload)."""
    perm = _import_permission_module()
    hook_common.set_language("zh")
    sug = {"type": "addRules", "decision": {"behavior": "deny", "destination": "session"}}
    assert perm.get_suggestion_label(sug) == "拒绝（本次会话）"


def test_get_suggestion_label_unknown_fallback():
    """Unknown combos fall back to '应用规则'."""
    perm = _import_permission_module()
    hook_common.set_language("zh")
    sug = {"type": "unknown", "behavior": "unknown", "destination": "unknown"}
    assert perm.get_suggestion_label(sug) == "应用规则"


# --- build_permission_message tests ---

def test_build_permission_message_bash():
    perm = _import_permission_module()
    title, body = perm.build_permission_message({
        "tool_name": "Bash",
        "tool_input": {"command": "echo hello"},
    })
    assert title == "Bash command"
    assert body == "echo hello"


def test_build_permission_message_bash_truncation():
    perm = _import_permission_module()
    long_cmd = "x" * 400
    title, body = perm.build_permission_message({
        "tool_name": "Bash",
        "tool_input": {"command": long_cmd},
    })
    assert title == "Bash command"
    assert "truncated" in body
    assert len(body) < 400


def test_build_permission_message_edit():
    perm = _import_permission_module()
    title, body = perm.build_permission_message({
        "tool_name": "Edit",
        "tool_input": {"file_path": "src/app.py"},
    })
    assert title == "Edit file"
    assert "app.py" in body


def test_build_permission_message_write():
    perm = _import_permission_module()
    title, body = perm.build_permission_message({
        "tool_name": "Write",
        "tool_input": {"file_path": "output.txt"},
    })
    assert title == "Write file"
    assert "output.txt" in body


def test_build_permission_message_read():
    perm = _import_permission_module()
    title, body = perm.build_permission_message({
        "tool_name": "Read",
        "tool_input": {"file_path": "config.yaml"},
    })
    assert title == "Read file"
    assert "config.yaml" in body


def test_build_permission_message_unknown_tool():
    perm = _import_permission_module()
    title, body = perm.build_permission_message({
        "tool_name": "WebFetch",
        "tool_input": {"url": "https://example.com"},
    })
    assert "WebFetch" in title
    assert "Permission" in title
    assert "url" in body


def test_build_permission_message_chinese():
    perm = _import_permission_module()
    hook_common.set_language("zh")
    title, body = perm.build_permission_message({
        "tool_name": "Bash",
        "tool_input": {"command": "x" * 400},
    })
    assert title == "Bash 命令"
    assert "已截断" in body
    title, _ = perm.build_permission_message({
        "tool_name": "Edit",
        "tool_input": {"file_path": "src/app.py"},
    })
    assert title == "编辑文件"


# --- shorten_path tests ---

def test_shorten_path_short():
    perm = _import_permission_module()
    assert perm.shorten_path("src/app.py") == os.path.join("src", "app.py")


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

def _make_tk_root():
    """Create a hidden Tk root, skipping when no display is available."""
    import tkinter as tk
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display available for Tk widgets")
    root.withdraw()
    return root


def test_text_helpers_with_entry():
    """Text helper functions work with tk.Entry widgets."""
    import tkinter as tk
    ask = _import_ask_module()
    root = _make_tk_root()
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
    root = _make_tk_root()
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
    assert answers["Pick features"] == ["Dark mode"]


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
    assert answers["Q2"] == ["X"]
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


# --- Suggestion schema coverage ---

def test_get_suggestion_label_setmode_uses_mode_field():
    perm = _import_permission_module()
    hook_common.set_language("zh")
    assert perm.get_suggestion_label(
        {"type": "setMode", "mode": "auto", "destination": "session"}
    ) == "自动批准（本次会话）"
    assert perm.get_suggestion_label(
        {"type": "setMode", "mode": "acceptEdits", "destination": "projectSettings"}
    ) == "自动接受编辑（共享项目）"


def test_suggestion_labels_project_settings_and_new_types():
    perm = _import_permission_module()
    hook_common.set_language("zh")
    assert "共享项目" in perm.get_suggestion_label(
        {"type": "addRules", "behavior": "allow", "destination": "projectSettings"})
    for entry_type, label in (
        ("replaceRules", "替换规则"),
        ("removeRules", "移除规则"),
        ("addDirectories", "添加目录"),
        ("removeDirectories", "移除目录"),
    ):
        assert label in perm.get_suggestion_label(
            {"type": entry_type, "destination": "session"})


def test_get_suggestion_behavior():
    perm = _import_permission_module()
    assert perm.get_suggestion_behavior({"type": "addRules", "behavior": "ask"}) == "ask"
    assert perm.get_suggestion_behavior({"type": "setMode", "mode": "auto"}) == "allow"
    assert perm.get_suggestion_behavior(
        {"type": "addRules", "decision": {"behavior": "deny"}}
    ) == "deny"


# --- Headless / opt-out guards ---

def test_permission_request_headless_exits_silently():
    event = {"tool_name": "Bash", "tool_input": {"command": "echo hi"}}
    result = _run_hook("permission_request.py", event, test_mode=False,
                       extra_env={"CI": "1"})
    assert result.returncode == 0
    assert result.stdout.strip() == b""


def test_ask_user_question_headless_exits_silently():
    event = {
        "tool_name": "AskUserQuestion",
        "tool_input": {"questions": [{"question": "Q", "options": []}]},
    }
    result = _run_hook("ask_user_question.py", event, test_mode=False,
                       extra_env={"CI": "1"})
    assert result.returncode == 0
    assert result.stdout.strip() == b""


def test_permission_request_opt_out_env():
    event = {"tool_name": "Bash", "tool_input": {"command": "echo hi"}}
    result = _run_hook(
        "permission_request.py", event, test_mode=False,
        extra_env={"CLAUDE_GUI_HOOKS_DISABLE": "1"},
    )
    assert result.returncode == 0
    assert result.stdout.strip() == b""


# --- Stop / StopFailure ---

def test_stop_failure_smoke():
    event = {"hook_event_name": "StopFailure", "error": "rate_limit"}
    result = _run_hook("stop_notify.py", event)
    assert result.returncode == 0
    assert result.stdout.strip() == b""


def test_stop_failure_message():
    stop = _import_stop_module()
    title, body = stop._build_message({
        "hook_event_name": "StopFailure",
        "error": "rate_limit",
        "error_details": "429 Too Many Requests",
    })
    assert "rate_limit" in body
    assert "429" in body
    assert "Error" in title


def test_stop_background_tasks_message():
    stop = _import_stop_module()
    title, body = stop._build_message({
        "hook_event_name": "Stop",
        "background_tasks": [{"id": "t1", "type": "shell"}],
        "session_crons": [{"id": "c1", "schedule": "0 9 * * *"}],
    })
    assert "background task" in body
    assert "scheduled wakeup" in body
    assert "Waiting" in title


def test_stop_plain_message():
    stop = _import_stop_module()
    _, body = stop._build_message({"last_assistant_message": "All done."})
    assert body == "All done."


# --- Notification ---

def test_notification_smoke():
    event = {"notification_type": "agent_completed", "message": "Agent finished."}
    result = _run_hook("notification_notify.py", event)
    assert result.returncode == 0
    assert result.stdout.strip() == b""


def test_notification_build_message():
    notif = _import_notification_module()
    title, body = notif._build_message({
        "notification_type": "agent_needs_input",
        "message": "Pick a file",
    })
    assert "Needs Input" in title
    assert body == "Pick a file"


def test_notification_ignores_unhandled_type():
    notif = _import_notification_module()
    assert notif._build_message({"notification_type": "idle_prompt"}) is None


def _import_plan_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "exit_plan_mode_notify", HOOKS_DIR / "exit_plan_mode_notify.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_plan_preview_skips_heading():
    plan = _import_plan_module()
    body = plan._build_message({
        "tool_input": {"plan": "# 计划\n重构登录流程并补充测试。"},
    })
    assert body.startswith(hook_common.tr("plan.body"))
    assert body.endswith("重构登录流程并补充测试。")


def test_plan_preview_heading_only_falls_back():
    plan = _import_plan_module()
    body = plan._build_message({"tool_input": {"plan": "# 只有标题"}})
    assert body.endswith("只有标题")


# --- i18n ---

def test_language_override_beats_locale():
    assert hook_common.resolve_language(
        {"CLAUDE_GUI_HOOKS_LANG": "en", "LANG": "zh_CN.UTF-8"}) == "en"
    assert hook_common.resolve_language(
        {"CLAUDE_GUI_HOOKS_LANG": "zh", "LANG": "en_US.UTF-8"}) == "zh"


def test_language_from_locale_env():
    assert hook_common.resolve_language({"LANG": "zh_CN.UTF-8"}) == "zh"
    assert hook_common.resolve_language({"LC_ALL": "zh_TW.UTF-8"}) == "zh"
    assert hook_common.resolve_language({"LC_MESSAGES": "zh_CN"}) == "zh"
    assert hook_common.resolve_language({"LANG": "de_DE.UTF-8"}) == "en"


def test_c_locale_defers_to_platform_language(monkeypatch):
    """Git Bash leaves LANG=LC_ALL=C.UTF-8 behind; that must not force English."""
    monkeypatch.setattr(hook_common, "_platform_language", lambda: "zh")
    assert hook_common.resolve_language(
        {"LC_ALL": "C.UTF-8", "LANG": "C.UTF-8"}) == "zh"
    assert hook_common.resolve_language({"LANG": "C", "LC_MESSAGES": "POSIX"}) == "zh"


def test_meaningful_locale_beats_platform_language(monkeypatch):
    monkeypatch.setattr(hook_common, "_platform_language", lambda: "zh")
    assert hook_common.resolve_language({"LANG": "en_US.UTF-8"}) == "en"


@pytest.mark.skipif(sys.platform == "win32",
                    reason="Windows falls back to the OS UI language")
def test_language_default_is_english():
    assert hook_common.resolve_language({}) == "en"


def test_tr_formats_and_falls_back():
    hook_common.set_language("zh")
    assert hook_common.tr("perm.title.command", tool="Bash") == "Bash 命令"
    hook_common.set_language("en")
    assert hook_common.tr("perm.title.command", tool="Bash") == "Bash command"
    assert hook_common.tr("missing.key", default="x") == "x"


def test_with_project_appends_cwd_basename():
    title = "Claude Code - Done"
    assert hook_common.with_project(
        title, {"cwd": "G:\\CodeBuddy-workspace\\my-app"}) == f"{title} \u00b7 my-app"
    assert hook_common.with_project(
        title, {"cwd": "/home/me/my-app/"}) == f"{title} \u00b7 my-app"
    assert hook_common.with_project(title, {}) == title
    assert hook_common.with_project(title, {"cwd": ""}) == title


def _placeholders(template: str) -> set:
    return {field for _, field, _, _ in string.Formatter().parse(template) if field}


def test_string_tables_complete():
    en = hook_common.STRINGS["en"]
    zh = hook_common.STRINGS["zh"]
    assert set(en) == set(zh)
    for key in en:
        assert en[key], key
        assert zh[key], key
        assert _placeholders(en[key]) == _placeholders(zh[key]), key


def test_stop_waiting_singular_grammar():
    stop = _import_stop_module()
    _, body = stop._build_message({
        "hook_event_name": "Stop",
        "background_tasks": [{"id": "t1"}],
    })
    assert "1 background task is still running" in body


def test_stop_background_tasks_message_chinese():
    hook_common.set_language("zh")
    stop = _import_stop_module()
    title, body = stop._build_message({
        "hook_event_name": "Stop",
        "background_tasks": [{"id": "t1"}],
        "session_crons": [{"id": "c1"}, {"id": "c2"}],
    })
    assert "等待" in title
    assert "1 个后台任务" in body
    assert "2 个定时唤醒" in body


# --- Dialog lock ---

def _lock_probe(wait_seconds):
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); import hook_common; "
        "lock = hook_common.acquire_dialog_lock(float(sys.argv[2])); "
        "print('locked' if lock is not None else 'busy'); "
        "lock.release() if lock is not None else None"
    )
    return subprocess.run(
        [PYTHON, "-c", code, str(HOOKS_DIR), str(wait_seconds)],
        capture_output=True, text=True, timeout=30,
    )


def test_dialog_lock_roundtrip():
    lock = hook_common.acquire_dialog_lock(0)
    assert lock is not None
    lock.release()
    lock.release()  # release is idempotent


def test_dialog_lock_blocks_second_process():
    lock = hook_common.acquire_dialog_lock(0)
    assert lock is not None
    try:
        result = _lock_probe(0)
        assert result.stdout.strip() == "busy", result.stderr
    finally:
        lock.release()
    result = _lock_probe(0)
    assert result.stdout.strip() == "locked", result.stderr


def test_dialog_lock_wait_times_out():
    lock = hook_common.acquire_dialog_lock(0)
    assert lock is not None
    try:
        start = time.monotonic()
        result = _lock_probe(0.3)
        elapsed = time.monotonic() - start
        assert result.stdout.strip() == "busy", result.stderr
        assert elapsed >= 0.25
    finally:
        lock.release()
