# Claude Code Notify — Install Skill

Install native GUI hooks for Claude Code. Cross-platform (Windows/macOS/Linux), zero external dependencies — just Python 3.10+ with tkinter.

Hooks installed: permission dialog, question dialog, Stop / API-failure notification, and subagent notification.

## Option A: Plugin install (recommended)

If Claude Code plugins are available (v2.1.300+), install as a plugin — no settings.json modification needed.

**Step 1** — Add the marketplace:

```bash
claude plugin marketplace add BaixuanZhu/claude-code-hooks
```

**Step 2** — Install the plugin:

```bash
claude plugin install desktop-dialogs@claude-code-hooks
```

Or use the interactive `/plugin` command to browse and enable. Hooks are bundled in the plugin and activate automatically.

To test locally before publishing:

```bash
claude plugin marketplace add /path/to/claude-code-hooks
claude plugin install desktop-dialogs@claude-code-hooks
```

> On Windows, the plugin uses a shell-form command that needs Git for Windows (Git Bash). If Git Bash is unavailable, use Option B — it installs exec-form commands that need no shell.

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
| `notification_notify.py` | `https://raw.githubusercontent.com/BaixuanZhu/claude-code-hooks/main/hooks/notification_notify.py` |
| `hook_common.py` | `https://raw.githubusercontent.com/BaixuanZhu/claude-code-hooks/main/hooks/hook_common.py` |

`hook_common.py` is a shared module imported by the five hook scripts (language, fonts, dialog lock). All six files must sit in the same directory.

### Fallback: git clone

If `raw.githubusercontent.com` is unreachable:

1. `git clone https://github.com/BaixuanZhu/claude-code-hooks.git` into a temp directory
2. Copy `hooks/*.py` (6 files) to `~/.claude/hooks/scripts/`
3. Delete the temp directory

### Step 3: Configure settings.json

Read `~/.claude/settings.json` and merge the config below.

Placeholders to resolve before writing:

- `<PYTHON>` — `pythonw` on Windows (no console flash), `python3` on macOS/Linux
- `<SCRIPTS_DIR>` — absolute path to the scripts directory, for example `C:/Users/you/.claude/hooks/scripts` or `/Users/you/.claude/hooks/scripts`. Forward slashes are fine on every platform.

Exec form (`command` + `args`, no shell) is deliberate: it avoids quoting problems and the Windows PowerShell 5.1 failure where `||` is a parse error. `onFailure: "continue"` guarantees a broken hook never blocks a tool call.

Merge rules:

- If the file does not exist or has no `"hooks"` key → write the full config below
- If `"hooks"` exists → for each event, remove only entries whose `command` or `args` reference one of the five hook script filenames, then append the entries below
- Never delete unrelated hook entries

Target config to merge:

```json
{
  "hooks": {
    "PermissionRequest": [
      {
        "matcher": "^(Bash|PowerShell|Edit|Write|Read|Glob|Grep|Agent|Workflow|WebFetch|WebSearch|NotebookEdit|mcp__.*)$",
        "hooks": [
          {
            "type": "command",
            "command": "<PYTHON>",
            "args": ["<SCRIPTS_DIR>/permission_request.py"],
            "onFailure": "continue"
          }
        ]
      },
      {
        "matcher": "^ExitPlanMode$",
        "hooks": [
          {
            "type": "command",
            "command": "<PYTHON>",
            "args": ["<SCRIPTS_DIR>/exit_plan_mode_notify.py"],
            "async": true,
            "onFailure": "continue"
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "^AskUserQuestion$",
        "hooks": [
          {
            "type": "command",
            "command": "<PYTHON>",
            "args": ["<SCRIPTS_DIR>/ask_user_question.py"],
            "onFailure": "continue"
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "<PYTHON>",
            "args": ["<SCRIPTS_DIR>/stop_notify.py"],
            "async": true
          }
        ]
      }
    ],
    "StopFailure": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "<PYTHON>",
            "args": ["<SCRIPTS_DIR>/stop_notify.py"],
            "async": true
          }
        ]
      }
    ],
    "Notification": [
      {
        "matcher": "agent_needs_input|agent_completed",
        "hooks": [
          {
            "type": "command",
            "command": "<PYTHON>",
            "args": ["<SCRIPTS_DIR>/notification_notify.py"],
            "async": true
          }
        ]
      }
    ]
  }
}
```

### Step 4: Verify

1. All 6 `.py` files exist and are non-empty in `~/.claude/hooks/scripts/`
2. `~/.claude/settings.json` is valid JSON
3. `hooks.PermissionRequest`, `hooks.PreToolUse`, `hooks.Stop`, `hooks.StopFailure`, `hooks.Notification` are all present

### Step 5: Report

Tell the user:
- Which files were fetched
- Whether settings.json was created or merged
- That dialogs are skipped in CI or when `CLAUDE_GUI_HOOKS_DISABLE=1` is set
- That the UI language follows the system locale (Chinese or English); `CLAUDE_GUI_HOOKS_LANG=zh` / `=en` overrides it
- Any warnings (e.g. tkinter unavailable, fetch failed and fell back to git clone)
- **Restart Claude Code session** for hooks to take effect
