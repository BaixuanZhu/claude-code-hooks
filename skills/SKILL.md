# Claude Code Windows Hooks — Install Skill

Install native Windows GUI hooks for Claude Code. Zero external dependencies — just Python 3.10+ with tkinter.

## Step 1: Create directory

Create `~/.claude/hooks/scripts/` if it does not exist. (`~` expands to user home directory.)

## Step 2: Fetch hook scripts

Fetch each file and save to `~/.claude/hooks/scripts/`:

| File | URL |
|------|-----|
| `permission_request.pyw` | `https://raw.githubusercontent.com/BaixuanZhu/claude-code-hooks/main/hooks/permission_request.pyw` |
| `ask_user_question.pyw` | `https://raw.githubusercontent.com/BaixuanZhu/claude-code-hooks/main/hooks/ask_user_question.pyw` |
| `stop_notify.pyw` | `https://raw.githubusercontent.com/BaixuanZhu/claude-code-hooks/main/hooks/stop_notify.pyw` |
| `exit_plan_mode_notify.pyw` | `https://raw.githubusercontent.com/BaixuanZhu/claude-code-hooks/main/hooks/exit_plan_mode_notify.pyw` |

### Fallback: git clone

If `raw.githubusercontent.com` is unreachable:

1. `git clone https://github.com/BaixuanZhu/claude-code-hooks.git` into a temp directory
2. Copy `hooks/*.pyw` (4 files) to `~/.claude/hooks/scripts/`
3. Delete the temp directory

## Step 3: Configure settings.json

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
            "command": "pythonw ~/.claude/hooks/scripts/permission_request.pyw"
          }
        ]
      },
      {
        "matcher": "ExitPlanMode",
        "hooks": [
          {
            "type": "command",
            "command": "pythonw ~/.claude/hooks/scripts/exit_plan_mode_notify.pyw"
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
            "command": "pythonw ~/.claude/hooks/scripts/ask_user_question.pyw"
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "pythonw ~/.claude/hooks/scripts/stop_notify.pyw"
          }
        ]
      }
    ]
  }
}
```

Note: Use `pythonw` (not `python`) to prevent console window flash. Keep `~` as-is — Claude Code expands it automatically.

## Step 4: Verify

1. All 4 `.pyw` files exist and are non-empty in `~/.claude/hooks/scripts/`
2. `~/.claude/settings.json` is valid JSON
3. `hooks.PermissionRequest`, `hooks.PreToolUse`, `hooks.Stop` are all present in settings

## Step 5: Report

Tell the user:
- Which files were fetched
- Whether settings.json was created or merged
- Any warnings (e.g. tkinter unavailable, fetch failed and fell back to git clone)
- **Restart Claude Code session** for hooks to take effect
