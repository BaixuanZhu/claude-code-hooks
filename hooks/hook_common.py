#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared helpers for the Claude Code Notify hook scripts.

Stdlib only. Every hook script imports this module as a sibling file: Claude
Code starts scripts by absolute path, so the hooks directory is already first
on sys.path.

Contents:
  - UI language detection + zh/en string tables
  - platform-aware fonts and ttk themes
  - cross-process dialog lock (only one dialog window at a time)
  - headless/opt-out guard, stdin JSON reader, Windows DPI awareness
"""

import json
import os
import sys
import tempfile
import time

DEFAULT_LANG = "en"
LOCK_POLL_SECONDS = 0.1

# ---------------------------------------------------------------------------
# i18n
# ---------------------------------------------------------------------------

STRINGS = {
    "en": {
        "perm.window_title": "Claude Code",
        "perm.title.command": "{tool} command",
        "perm.title.edit": "Edit file",
        "perm.title.write": "Write file",
        "perm.title.read": "Read file",
        "perm.title.generic": "Permission \u2014 {tool}",
        "perm.body.empty": "(empty command)",
        "perm.body.truncated": "\n... (truncated)",
        "perm.button.allow": "\u2713  Allow",
        "perm.button.deny": "\u2715  Deny",
        "perm.suggestion.fallback": "Apply rule",
        "perm.suggestion.combo": "{name} ({dest})",
        "perm.suggestion.deny_note": " \u00b7 this time only",
        "perm.dest.session": "this session",
        "perm.dest.localSettings": "local project",
        "perm.dest.projectSettings": "shared project",
        "perm.dest.userSettings": "global",
        "perm.mode.default": "Default mode",
        "perm.mode.manual": "Default mode",
        "perm.mode.auto": "Auto approve",
        "perm.mode.acceptEdits": "Accept edits",
        "perm.mode.dontAsk": "Don't ask",
        "perm.mode.bypassPermissions": "Bypass permissions",
        "perm.mode.plan": "Plan mode",
        "perm.rule.replaceRules": "Replace rules",
        "perm.rule.removeRules": "Remove rules",
        "perm.rule.addDirectories": "Add directories",
        "perm.rule.removeDirectories": "Remove directories",
        "perm.prefix.allow_session": "Allow",
        "perm.prefix.allow_always": "Always allow",
        "perm.prefix.deny_session": "Deny",
        "perm.prefix.deny_always": "Always deny",
        "perm.prefix.ask": "Ask",

        "ask.window_title": "Claude Code \u2014 Question",
        "ask.heading": "Claude has a question for you",
        "ask.confirm": "\u2713  Confirm",
        "ask.cancel": "\u2715  Cancel",
        "ask.placeholder": "Type your answer...",

        "stop.failure_title": "Claude Code - API Error",
        "stop.failure_body": "The turn ended due to an API error: {error}.",
        "stop.waiting_title": "Claude Code - Waiting",
        "stop.waiting_body_single": "Claude is paused while {parts} is still running.",
        "stop.waiting_body_many": "Claude is paused while {parts} are still running.",
        "stop.done_title": "Claude Code - Done",
        "stop.done_body": "Claude finished. Waiting for your input.",
        "stop.task": "{n} background task",
        "stop.tasks": "{n} background tasks",
        "stop.cron": "{n} scheduled wakeup",
        "stop.crons": "{n} scheduled wakeups",
        "stop.join": "{a} and {b}",

        "plan.window_title": "Claude Code",
        "plan.body": "Plan is ready. Please review and approve.",

        "notif.agent_needs_input.title": "Claude Code - Agent Needs Input",
        "notif.agent_needs_input.body": "An agent needs your input.",
        "notif.agent_completed.title": "Claude Code - Agent Done",
        "notif.agent_completed.body": "An agent finished its work.",
    },
    "zh": {
        "perm.window_title": "Claude Code",
        "perm.title.command": "{tool} \u547d\u4ee4",
        "perm.title.edit": "\u7f16\u8f91\u6587\u4ef6",
        "perm.title.write": "\u5199\u5165\u6587\u4ef6",
        "perm.title.read": "\u8bfb\u53d6\u6587\u4ef6",
        "perm.title.generic": "\u6743\u9650 \u2014 {tool}",
        "perm.body.empty": "(\u7a7a\u547d\u4ee4)",
        "perm.body.truncated": "\n... (\u5df2\u622a\u65ad)",
        "perm.button.allow": "\u2713  \u5141\u8bb8",
        "perm.button.deny": "\u2715  \u62d2\u7edd",
        "perm.suggestion.fallback": "\u5e94\u7528\u89c4\u5219",
        "perm.suggestion.combo": "{name}\uff08{dest}\uff09",
        "perm.suggestion.deny_note": " \u00b7 \u4ec5\u672c\u6b21",
        "perm.dest.session": "\u672c\u6b21\u4f1a\u8bdd",
        "perm.dest.localSettings": "\u672c\u5730\u9879\u76ee",
        "perm.dest.projectSettings": "\u5171\u4eab\u9879\u76ee",
        "perm.dest.userSettings": "\u5168\u5c40",
        "perm.mode.default": "\u9ed8\u8ba4\u6a21\u5f0f",
        "perm.mode.manual": "\u9ed8\u8ba4\u6a21\u5f0f",
        "perm.mode.auto": "\u81ea\u52a8\u6279\u51c6",
        "perm.mode.acceptEdits": "\u81ea\u52a8\u63a5\u53d7\u7f16\u8f91",
        "perm.mode.dontAsk": "\u4e0d\u518d\u8be2\u95ee",
        "perm.mode.bypassPermissions": "\u8df3\u8fc7\u6743\u9650\u68c0\u67e5",
        "perm.mode.plan": "\u8ba1\u5212\u6a21\u5f0f",
        "perm.rule.replaceRules": "\u66ff\u6362\u89c4\u5219",
        "perm.rule.removeRules": "\u79fb\u9664\u89c4\u5219",
        "perm.rule.addDirectories": "\u6dfb\u52a0\u76ee\u5f55",
        "perm.rule.removeDirectories": "\u79fb\u9664\u76ee\u5f55",
        "perm.prefix.allow_session": "\u5141\u8bb8",
        "perm.prefix.allow_always": "\u59cb\u7ec8\u5141\u8bb8",
        "perm.prefix.deny_session": "\u62d2\u7edd",
        "perm.prefix.deny_always": "\u59cb\u7ec8\u62d2\u7edd",
        "perm.prefix.ask": "\u8be2\u95ee",

        "ask.window_title": "Claude Code \u2014 \u95ee\u9898",
        "ask.heading": "Claude \u6709\u4e00\u4e2a\u95ee\u9898\u8981\u95ee\u4f60",
        "ask.confirm": "\u2713  \u786e\u8ba4",
        "ask.cancel": "\u2715  \u53d6\u6d88",
        "ask.placeholder": "\u8bf7\u8f93\u5165\u4f60\u7684\u56de\u7b54...",

        "stop.failure_title": "Claude Code - API \u9519\u8bef",
        "stop.failure_body": "\u672c\u8f6e\u56e0 API \u9519\u8bef\u7ed3\u675f\uff1a{error}\u3002",
        "stop.waiting_title": "Claude Code - \u7b49\u5f85\u4e2d",
        "stop.waiting_body_single": "Claude \u5df2\u6682\u505c\uff0c\u4ecd\u6709 {parts} \u5728\u8fd0\u884c\u3002",
        "stop.waiting_body_many": "Claude \u5df2\u6682\u505c\uff0c\u4ecd\u6709 {parts} \u5728\u8fd0\u884c\u3002",
        "stop.done_title": "Claude Code - \u5b8c\u6210",
        "stop.done_body": "Claude \u5df2\u5b8c\u6210\uff0c\u7b49\u5f85\u4f60\u7684\u8f93\u5165\u3002",
        "stop.task": "{n} \u4e2a\u540e\u53f0\u4efb\u52a1",
        "stop.tasks": "{n} \u4e2a\u540e\u53f0\u4efb\u52a1",
        "stop.cron": "{n} \u4e2a\u5b9a\u65f6\u5524\u9192",
        "stop.crons": "{n} \u4e2a\u5b9a\u65f6\u5524\u9192",
        "stop.join": "{a} \u548c {b}",

        "plan.window_title": "Claude Code",
        "plan.body": "\u8ba1\u5212\u5df2\u5c31\u7eea\uff0c\u8bf7\u5ba1\u9605\u5e76\u6279\u51c6\u3002",

        "notif.agent_needs_input.title": "Claude Code - \u5b50\u4ee3\u7406\u9700\u8981\u8f93\u5165",
        "notif.agent_needs_input.body": "\u5b50\u4ee3\u7406\u9700\u8981\u4f60\u7684\u8f93\u5165\u3002",
        "notif.agent_completed.title": "Claude Code - \u5b50\u4ee3\u7406\u5b8c\u6210",
        "notif.agent_completed.body": "\u5b50\u4ee3\u7406\u5df2\u5b8c\u6210\u4efb\u52a1\u3002",
    },
}

_lang = None


def _locale_language(env) -> str | None:
    """Language implied by LC_ALL/LC_MESSAGES/LANG, or None when it carries no
    information. C/POSIX locales are what Git Bash and cron leave behind on
    Windows; they mean "unset", not "English", so the OS language still wins.
    """
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = (env.get(var) or "").strip().lower()
        if not value:
            continue
        base = value.split(".")[0].replace("-", "_")
        if base in ("c", "posix"):
            continue
        return "zh" if base.startswith("zh") else "en"
    return None


def _platform_language() -> str | None:
    if sys.platform == "win32":
        try:
            import ctypes
            # Low word is the primary language ID; 0x04 = Chinese.
            if (ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF) == 0x04:
                return "zh"
        except (AttributeError, OSError):
            pass
    return None


def resolve_language(environ=None) -> str:
    """Resolve the UI language: explicit override > meaningful locale env >
    Windows UI language > 'en'."""
    env = os.environ if environ is None else environ

    override = (env.get("CLAUDE_GUI_HOOKS_LANG") or "").strip().lower()
    if override:
        return "zh" if override.startswith("zh") else "en"

    return _locale_language(env) or _platform_language() or DEFAULT_LANG


def language() -> str:
    global _lang
    if _lang is None:
        _lang = resolve_language()
    return _lang


def set_language(code):
    """Force a language ('zh'/'en'), or pass None to re-detect (used by tests)."""
    global _lang
    if code is None:
        _lang = None
    else:
        _lang = "zh" if str(code).lower().startswith("zh") else "en"


def tr(key: str, default: str = None, **kwargs) -> str:
    template = STRINGS.get(language(), {}).get(key)
    if template is None:
        template = STRINGS[DEFAULT_LANG].get(key, default)
    if template is None:
        return key
    return template.format(**kwargs) if kwargs else template


def ui_font(size: int = 10, bold: bool = False):
    """Pick a font family that matches the platform and language."""
    if sys.platform == "win32":
        family = "Microsoft YaHei UI"
    elif sys.platform == "darwin":
        family = "PingFang SC" if language() == "zh" else "Helvetica Neue"
    else:
        family = "Noto Sans CJK SC" if language() == "zh" else "DejaVu Sans"
    return (family, size, "bold") if bold else (family, size)


def apply_theme(style):
    """Use the most modern ttk theme available on this platform."""
    import tkinter as tk

    if sys.platform == "win32":
        candidates = ("vista", "winnative", "clam", "default")
    elif sys.platform == "darwin":
        candidates = ("aqua", "clam", "default")
    else:
        candidates = ("clam", "default")

    for theme in candidates:
        try:
            style.theme_use(theme)
            return
        except tk.TclError:
            continue


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

def gui_disabled() -> bool:
    """True in CI or when the user opted out; hooks then leave the flow alone."""
    return os.environ.get("CLAUDE_GUI_HOOKS_DISABLE") == "1" or bool(os.environ.get("CI"))


def read_stdin_json() -> dict:
    """Best-effort UTF-8 JSON read from stdin. Returns {} on any failure."""
    try:
        raw = sys.stdin.buffer.read()
        if not raw:
            return {}
        data = json.loads(raw.decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def enable_high_dpi():
    """Per-monitor DPI awareness on Windows so dialogs aren't blurry."""
    if sys.platform != "win32":
        return
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # per-monitor V2 (Win 8.1+)
    except (AttributeError, OSError):
        try:
            ctypes.windll.user32.SetProcessDPIAware()  # legacy fallback (Vista+)
        except (AttributeError, OSError):
            pass


# ---------------------------------------------------------------------------
# Cross-process dialog lock
# ---------------------------------------------------------------------------

class _DialogLock:
    def __init__(self, fd: int):
        self._fd = fd
        self._released = False

    def release(self):
        if self._released:
            return
        self._released = True
        try:
            _unlock_fd(self._fd)
        finally:
            os.close(self._fd)


class _NoopLock:
    """Returned when the OS lock is unusable; dialogs still work, just unserialized."""

    def release(self):
        pass


def _lock_path() -> str:
    if hasattr(os, "getuid"):
        suffix = f"-{os.getuid()}"
    else:
        user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
        suffix = f"-{user}" if user else ""
    return os.path.join(tempfile.gettempdir(), f"claude-code-notify{suffix}.lock")


def _try_lock_fd(fd: int) -> bool:
    try:
        if sys.platform == "win32":
            import msvcrt
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _unlock_fd(fd: int):
    try:
        if sys.platform == "win32":
            import msvcrt
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass


def acquire_dialog_lock(wait_seconds: float = 0.0):
    """Take the cross-process dialog lock.

    Returns a handle, or None if another dialog process held the lock for the
    whole wait. Blocking hooks queue (wait then show anyway on timeout);
    background notifications drop the popup. The OS releases the lock if the
    holding process dies, so a crash cannot wedge future dialogs.
    """
    try:
        fd = os.open(_lock_path(), os.O_CREAT | os.O_RDWR, 0o600)
    except OSError:
        return _NoopLock()

    deadline = time.monotonic() + max(0.0, float(wait_seconds))
    while True:
        if _try_lock_fd(fd):
            return _DialogLock(fd)
        if time.monotonic() >= deadline:
            os.close(fd)
            return None
        time.sleep(LOCK_POLL_SECONDS)
