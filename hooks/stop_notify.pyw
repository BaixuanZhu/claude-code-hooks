#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Claude Code Stop hook.

When Claude finishes responding and waits for user input,
emits an OSC 9 terminal notification sequence via stdout.
Claude Code then sends it through its own terminal write path,
triggering a desktop notification in Windows Terminal / iTerm2 / WezTerm etc.

Reads JSON from stdin (UTF-8). The Stop event includes
`last_assistant_message`, so we surface a short preview of it as the
notification body — falling back to a generic "Task completed" message.
Outputs JSON with `terminalSequence` to stdout.
"""

import json
import re
import sys

MAX_PREVIEW = 80  # cap the notification body length


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


def _build_body(data: dict) -> str:
    """Derive a short, single-line notification body from the Stop input."""
    msg = (data.get("last_assistant_message") or "").strip()
    if not msg:
        return "Task completed"

    # Collapse whitespace and drop control chars / newlines so the OSC 9
    # sequence stays a single clean line. Claude Code's allowlist rejects
    # disallowed escape sequences anyway, but stray newlines corrupt the payload.
    msg = re.sub(r"\s+", " ", msg)

    if len(msg) > MAX_PREVIEW:
        msg = msg[:MAX_PREVIEW].rstrip() + "\u2026"
    return msg


def main():
    data = _read_stdin_json()
    body = _build_body(data)

    # OSC 9 notification sequence: \033]9;title;body\007
    # Supported by Windows Terminal, iTerm2, WezTerm, ConEmu, etc.
    seq = f"\033]9;Claude Code;{body}\007"

    result = {"terminalSequence": seq}
    print(json.dumps(result, ensure_ascii=False))

    sys.exit(0)


if __name__ == "__main__":
    main()
