# Claude Code Hooks for Windows

Replace Claude Code's terminal permission prompts with native Windows GUI dialogs — zero dependencies, just Python + tkinter.

## Features

| Hook | Event | What it does |
|------|-------|--------------|
| **Permission Request** | `PermissionRequest` | Allow/Deny dialog with suggestion buttons (session/project/global scope) |
| **Ask User Question** | `PreToolUse` → `AskUserQuestion` | Native option dialog — single select or multi select |
| **Stop Notify** | `Stop` | OSC 9 desktop notification when Claude finishes |
| **Exit Plan Mode** | `PermissionRequest` → `ExitPlanMode` | Topmost messagebox when plan is ready (auto-closes 25s) |

- **Zero dependencies** — Python 3.10+ + tkinter, nothing else
- **Keyboard shortcuts** — Enter to Allow, Escape to Deny, number keys for suggestions
- **`.pyw` suffix** — no console window flash

## Install

### One-click (share URL with AI)

Share this URL with your Claude Code:

```
https://raw.githubusercontent.com/a2359117018/claude-code-dialogs/main/skills/SKILL.md
```

The AI reads `SKILL.md` and installs everything automatically — no manual steps.

> If `raw.githubusercontent.com` is unreachable, use `git clone` as fallback (see SKILL.md for details).

### Manual

1. Clone the repo
2. Copy `hooks/*.pyw` into `~/.claude/hooks/scripts/` (create the folder if needed)
3. Add to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PermissionRequest": [
      {
        "matcher": "Bash|Edit|Write|Read|Glob|Grep|WebFetch|WebSearch|mcp__.*",
        "hooks": [{ "type": "command", "command": "pythonw C:\\Users\\YOU\\.claude\\hooks\\scripts\\permission_request.pyw" }]
      },
      {
        "matcher": "ExitPlanMode",
        "hooks": [{ "type": "command", "command": "pythonw C:\\Users\\YOU\\.claude\\hooks\\scripts\\exit_plan_mode_notify.pyw" }]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "AskUserQuestion",
        "hooks": [{ "type": "command", "command": "pythonw C:\\Users\\YOU\\.claude\\hooks\\scripts\\ask_user_question.pyw" }]
      }
    ],
    "Stop": [
      {
        "hooks": [{ "type": "command", "command": "pythonw C:\\Users\\YOU\\.claude\\hooks\\scripts\\stop_notify.pyw" }]
      }
    ]
  }
}
```

4. Restart Claude Code

> Replace `C:\Users\YOU` with your actual user path. Use `pythonw` (not `python`) — prevents console window flash.

## Limitations

- **Windows only** — tkinter dialogs are Windows-native
- **No dark mode** — uses system default styling
- **Stop notify requires modern terminal** — Windows Terminal / WezTerm / iTerm2; legacy `cmd.exe` doesn't support OSC 9

## License

[MIT](LICENSE)
