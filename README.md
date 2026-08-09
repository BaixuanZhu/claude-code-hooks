# Claude Code GUI Hooks

Replace Claude Code's terminal permission prompts with native GUI dialogs — zero dependencies, just Python + tkinter. Cross-platform: Windows, macOS, Linux.

## Demo

| Hook | Screenshot |
|------|------------|
| Permission Request | ![Permission Request](docs/screenshots/permission-request.png) |
| Ask User Question | ![Ask User Question](docs/screenshots/ask-user-question.png) |
| Stop Notify | ![Stop Notify](docs/screenshots/stop-notify.png) |
| Exit Plan Mode | ![Exit Plan Mode](docs/screenshots/exit-plan-mode.png) |

## Features

| Hook | Event | What it does |
|------|-------|--------------|
| **Permission Request** | `PermissionRequest` | Allow/Deny dialog with suggestion buttons (session/project/global scope, Chinese labels) |
| **Ask User Question** | `PreToolUse` → `AskUserQuestion` | Native option dialog — single select or multi select, with multi-line free-text "Other" input |
| **Stop Notify** | `Stop` | Auto-closing messagebox when Claude finishes (8s) |
| **Exit Plan Mode** | `PermissionRequest` → `ExitPlanMode` | Topmost messagebox when plan is ready (auto-closes 25s) |

- **Zero dependencies** — Python 3.10+ + tkinter, nothing else
- **Cross-platform** — Windows, macOS, Linux
- **Modern ttk styling** — themed widgets (vista/winnative/clam) for a clean native look
- **Keyboard shortcuts** — Enter to Allow, Escape to Deny, number keys for suggestions, Ctrl+Enter to confirm in text areas
- **No console flash** — uses `pythonw` on Windows (falls back to `python3` on macOS/Linux)

## Install

### Plugin install (recommended)

Requires Claude Code v2.1+ with plugin support.

**Step 1** — Add the marketplace:

```bash
claude plugin marketplace add BaixuanZhu/claude-code-hooks
```

**Step 2** — Install the plugin:

```bash
claude plugin install claude-code-hooks@claude-code-hooks
```

Or use the interactive `/plugin` command to browse and enable. No `settings.json` modification needed — hooks are bundled in the plugin.

**Update** — Push new commits to the repo; Claude Code auto-updates on next session:

```bash
claude plugin update claude-code-hooks
```

**Uninstall** — Clean removal, no leftover config:

```bash
claude plugin uninstall claude-code-hooks
```

To test locally before publishing:

```bash
git clone https://github.com/BaixuanZhu/claude-code-hooks.git
claude plugin marketplace add ./claude-code-hooks
claude plugin install claude-code-hooks@claude-code-hooks
```

### PowerShell one-liner (Windows)

```powershell
iwr https://raw.githubusercontent.com/BaixuanZhu/claude-code-hooks/main/install.ps1 -UseBasicParsing | iex
```

Downloads all 4 hooks and merges into `~/.claude/settings.json`. Idempotent — safe to re-run.

### AI-assisted install

Share this URL with your Claude Code:

```
https://raw.githubusercontent.com/BaixuanZhu/claude-code-hooks/main/skills/SKILL.md
```

The AI reads `SKILL.md` and installs everything automatically.

### Manual

1. Clone the repo
2. Copy `hooks/*.py` into `~/.claude/hooks/scripts/` (create the folder if needed)
3. Add to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PermissionRequest": [
      {
        "matcher": "Bash|Edit|Write|Read|Glob|Grep|WebFetch|WebSearch|mcp__.*",
        "hooks": [{ "type": "command", "command": "pythonw ~/.claude/hooks/scripts/permission_request.py || python3 ~/.claude/hooks/scripts/permission_request.py" }]
      },
      {
        "matcher": "ExitPlanMode",
        "hooks": [{ "type": "command", "command": "pythonw ~/.claude/hooks/scripts/exit_plan_mode_notify.py || python3 ~/.claude/hooks/scripts/exit_plan_mode_notify.py" }]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "AskUserQuestion",
        "hooks": [{ "type": "command", "command": "pythonw ~/.claude/hooks/scripts/ask_user_question.py || python3 ~/.claude/hooks/scripts/ask_user_question.py" }]
      }
    ],
    "Stop": [
      {
        "hooks": [{ "type": "command", "command": "pythonw ~/.claude/hooks/scripts/stop_notify.py || python3 ~/.claude/hooks/scripts/stop_notify.py" }]
      }
    ]
  }
}
```

4. Restart Claude Code

> On Windows, `pythonw` runs without a console window. On macOS/Linux, `pythonw` is absent so `python3` is used via the `||` fallback. `~` is expanded automatically by Claude Code.

## Platform requirements

| Platform | Python | tkinter | Notes |
|----------|--------|---------|-------|
| Windows | 3.10+ | Built-in | `pythonw` for no console flash |
| macOS | 3.10+ | `brew install python-tk` | Falls back to `python3` |
| Linux | 3.10+ | `sudo apt install python3-tk` | Falls back to `python3` |

## Limitations

- **tkinter required** — most Python installations include it; Linux may need `python3-tk`
- **ttk themed** — uses native widget themes (vista on Windows, clam fallback on others); no custom color scheme
- **DPI awareness** — optimized for Windows; macOS/Linux use system defaults

## License

[MIT](LICENSE)
