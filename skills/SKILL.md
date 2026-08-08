# Claude Code GUI Hooks — Install Skill

Install native GUI hooks for Claude Code. Cross-platform (Windows/macOS/Linux), zero external dependencies — just Python 3.10+ with tkinter.

## Option A: Plugin install (recommended)

If Claude Code plugins are available (v2.1+), install as a plugin — no settings.json modification needed.

**Step 1** — Add the marketplace:

```bash
claude plugin marketplace add BaixuanZhu/claude-code-hooks
```

**Step 2** — Install the plugin:

```bash
claude plugin install claude-code-hooks@claude-code-hooks
```

Or use the interactive `/plugin` command to browse and enable. Hooks are bundled in the plugin and activate automatically.

To test locally before publishing:

```bash
claude plugin marketplace add /path/to/claude-code-hooks
claude plugin install claude-code-hooks@claude-code-hooks
```

## Option B: Manual install

Use this if plugins are unavailable or you prefer manual control.

### Step 1: Create directory

Create `~/.claude/hooks/scripts/` if it does not exist. (`~` expands to user home directory.)

### Step 2: Fetch hook scripts

Fetch each file and save to `~/.claude/hooks/scripts/`:

| File | URL |
|------|-----|
| `permission_request.py` | `https://raw.githubusercontent.com/BaixuanZhu/claude-code-hooks/main/hooks/permission_request.py` |
| `ask_user_question.py` | `https://raw.githubusercontent.com/BaixuanZhu/claude-code-hooks/main/hooks/ask_user_question.py` |
| `stop_notify.py` | `https://raw.githubusercontent.com/BaixuanZhu/claude-code-hooks/main/hooks/stop_notify.py` |
| `exit_plan_mode_notify.py` | `https://raw.githubusercontent.com/BaixuanZhu/claude-code-hooks/main/hooks/exit_plan_mode_notify.py` |

### Fallback: git clone

If `raw.githubusercontent.com` is unreachable:

1. `git clone https://github.com/BaixuanZhu/claude-code-hooks.git` into a temp directory
2. Copy `hooks/*.py` (4 files) to `~/.claude/hooks/scripts/`
3. Delete the temp directory

### Step 3: Configure settings.json

Read `~/.claude/settings.json`. Apply the following rules:

- If the file does not exist or has no `"hooks"` key → write the full config below
- If `"hooks"` exists → merge by event name:
  - For each event (`PermissionRequest`, `PreToolUse`, `Stop`): if the event key is missing, add it; if it exists, append entries that don't already match by `matcher`
  - For `PermissionRequest`: remove any existing entry with `matcher: "ExitPlanMode"` before adding the new one
  - Never delete existing hook entries that are not part of this install

Target config to merge:

```json
{
  "hooks": {
    "PermissionRequest": [
      {
        "matcher": "Bash|Edit|Write|Read|Glob|Grep|WebFetch|WebSearch|mcp__.*",
        "hooks": [
          {
            "type": "command",
            "command": "pythonw ~/.claude/hooks/scripts/permission_request.py || python3 ~/.claude/hooks/scripts/permission_request.py"
          }
        ]
      },
      {
        "matcher": "ExitPlanMode",
        "hooks": [
          {
            "type": "command",
            "command": "pythonw ~/.claude/hooks/scripts/exit_plan_mode_notify.py || python3 ~/.claude/hooks/scripts/exit_plan_mode_notify.py"
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "AskUserQuestion",
        "hooks": [
          {
            "type": "command",
            "command": "pythonw ~/.claude/hooks/scripts/ask_user_question.py || python3 ~/.claude/hooks/scripts/ask_user_question.py"
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "pythonw ~/.claude/hooks/scripts/stop_notify.py || python3 ~/.claude/hooks/scripts/stop_notify.py"
          }
        ]
      }
    ]
  }
}
```

Note: On Windows, `pythonw` runs without a console window (no flash). On macOS/Linux, `pythonw` is typically absent so `python3` is used via the `||` fallback. Keep `~` as-is — Claude Code expands it automatically.

### Step 4: Verify

1. All 4 `.py` files exist and are non-empty in `~/.claude/hooks/scripts/`
2. `~/.claude/settings.json` is valid JSON
3. `hooks.PermissionRequest`, `hooks.PreToolUse`, `hooks.Stop` are all present in settings

### Step 5: Report

Tell the user:
- Which files were fetched
- Whether settings.json was created or merged
- Any warnings (e.g. tkinter unavailable, fetch failed and fell back to git clone)
- **Restart Claude Code session** for hooks to take effect
