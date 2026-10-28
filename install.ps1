# install.ps1 - Claude Code Notify installer (Windows)
# Usage:
#   iwr https://raw.githubusercontent.com/BaixuanZhu/claude-code-hooks/main/install.ps1 -UseBasicParsing | iex
#
# Idempotent: safe to re-run. Overwrites .py files and merges into settings.json.
# Uses exec form (command + args) so no shell is involved: this avoids the
# PowerShell 5.1 problem where `||` is a parse error.
# Note: For Claude Code v2.1+ plugin install is recommended over this script:
#   claude plugin marketplace add BaixuanZhu/claude-code-hooks
#   claude plugin install desktop-dialogs@claude-code-hooks

$ErrorActionPreference = "Stop"

$RepoOwner = "BaixuanZhu"
$RepoName  = "claude-code-hooks"
$BaseUrl   = "https://raw.githubusercontent.com/$RepoOwner/$RepoName/main"

$HooksDir  = Join-Path $env:USERPROFILE ".claude\hooks\scripts"
$SettingsPath = Join-Path $env:USERPROFILE ".claude\settings.json"
$Scripts   = @(
    "permission_request.py",
    "ask_user_question.py",
    "stop_notify.py",
    "exit_plan_mode_notify.py",
    "notification_notify.py"
)

function Write-Step($msg)  { Write-Host "`n== $msg ==" -ForegroundColor Cyan }
function Write-Ok($msg)    { Write-Host "  [OK] $msg" -ForegroundColor Green }
function Write-Warn($msg)  { Write-Host "  [!]  $msg" -ForegroundColor Yellow }
function Write-Err($msg)   { Write-Host "  [X]  $msg" -ForegroundColor Red }

# --- Step 1: Create directory ---
Write-Step "Step 1/4: Create hooks directory"
if (-not (Test-Path $HooksDir)) {
    New-Item -ItemType Directory -Path $HooksDir -Force | Out-Null
    Write-Ok "Created: $HooksDir"
} else {
    Write-Ok "Already exists: $HooksDir"
}

# --- Step 2: Download scripts ---
Write-Step "Step 2/4: Download hook scripts"
foreach ($s in $Scripts) {
    $url = "$BaseUrl/hooks/$s"
    $out = Join-Path $HooksDir $s
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $url -OutFile $out -UseBasicParsing -TimeoutSec 30
        Write-Ok "$s ($([math]::Round((Get-Item $out).Length / 1KB, 1)) KB)"
    }
    catch {
        Write-Err "Failed to download $s from $url"
        Write-Host "       $_"
        exit 1
    }
}

# --- Step 3: Merge settings.json ---
Write-Step "Step 3/4: Merge settings.json"

# Load existing settings (or start fresh)
if (Test-Path $SettingsPath) {
    try {
        $settings = Get-Content $SettingsPath -Raw -Encoding UTF8 | ConvertFrom-Json
        Write-Ok "Loaded existing: $SettingsPath"
    }
    catch {
        Write-Err "Existing settings.json is not valid JSON: $_"
        exit 1
    }
    # Backup
    $bak = "$SettingsPath.bak"
    Copy-Item $SettingsPath $bak -Force
    Write-Ok "Backup: $bak"
}
else {
    $settings = [PSCustomObject]@{}
    Write-Ok "No existing settings.json - will create new"
}

# Ensure 'hooks' is an object
if (-not ($settings.PSObject.Properties.Name -contains 'hooks') -or $null -eq $settings.hooks) {
    $settings | Add-Member -NotePropertyName 'hooks' -NotePropertyValue ([PSCustomObject]@{}) -Force
}

function New-HookHandler($scriptName, [switch]$Async) {
    $handler = [PSCustomObject]@{
        type      = "command"
        command   = "pythonw"
        args      = @((Join-Path $HooksDir $scriptName))
        onFailure = "continue"
    }
    if ($Async) {
        $handler | Add-Member -NotePropertyName 'async' -NotePropertyValue $true
    }
    return $handler
}

function Test-OwnedEntry($entry) {
    if ($null -eq $entry) { return $false }
    $candidates = @($entry.hooks)
    foreach ($h in $candidates) {
        if ($null -eq $h) { continue }
        $text = "$($h.command) $(@($h.args) -join ' ')"
        foreach ($s in $Scripts) {
            if ($text -like "*$s*") { return $true }
        }
    }
    return $false
}

function Set-HookEvent($eventName, $entries) {
    if (-not ($settings.hooks.PSObject.Properties.Name -contains $eventName) -or $null -eq $settings.hooks.$eventName) {
        $settings.hooks | Add-Member -NotePropertyName $eventName -NotePropertyValue @() -Force
    }
    # Drop only entries this installer owns; keep every unrelated hook.
    $kept = @(@($settings.hooks.$eventName) | Where-Object {
        $null -ne $_ -and -not (Test-OwnedEntry $_)
    })
    $settings.hooks.$eventName = @($kept) + @($entries)
}

$permissionMain = [PSCustomObject]@{
    matcher = "^(Bash|PowerShell|Edit|Write|Read|Glob|Grep|Agent|Workflow|WebFetch|WebSearch|NotebookEdit|mcp__.*)$"
    hooks   = @(New-HookHandler "permission_request.py")
}
$permissionExit = [PSCustomObject]@{
    matcher = "^ExitPlanMode$"
    hooks   = @(New-HookHandler "exit_plan_mode_notify.py" -Async)
}
$preAsk = [PSCustomObject]@{
    matcher = "^AskUserQuestion$"
    hooks   = @(New-HookHandler "ask_user_question.py")
}
$stopHook = [PSCustomObject]@{
    hooks   = @(New-HookHandler "stop_notify.py" -Async)
}
$stopFailureHook = [PSCustomObject]@{
    hooks   = @(New-HookHandler "stop_notify.py" -Async)
}
$notificationHook = [PSCustomObject]@{
    matcher = "agent_needs_input|agent_completed"
    hooks   = @(New-HookHandler "notification_notify.py" -Async)
}

Set-HookEvent "PermissionRequest" @($permissionMain, $permissionExit)
Set-HookEvent "PreToolUse" @($preAsk)
Set-HookEvent "Stop" @($stopHook)
Set-HookEvent "StopFailure" @($stopFailureHook)
Set-HookEvent "Notification" @($notificationHook)

# Write back
$json = $settings | ConvertTo-Json -Depth 12
[System.IO.File]::WriteAllText($SettingsPath, $json, [System.Text.UTF8Encoding]::new($false))
Write-Ok "Wrote: $SettingsPath"

# --- Step 4: Verify ---
Write-Step "Step 4/4: Verify"
$allOk = $true
foreach ($s in $Scripts) {
    $p = Join-Path $HooksDir $s
    if ((Test-Path $p) -and ((Get-Item $p).Length -gt 0)) {
        Write-Ok "$s present"
    } else {
        Write-Err "$s missing or empty"
        $allOk = $false
    }
}
try {
    $check = Get-Content $SettingsPath -Raw | ConvertFrom-Json
    Write-Ok "settings.json is valid JSON"
    foreach ($eventName in @("PermissionRequest", "PreToolUse", "Stop", "StopFailure", "Notification")) {
        if ($check.hooks.PSObject.Properties.Name -contains $eventName) {
            Write-Ok "hooks.$eventName present"
        } else {
            Write-Err "hooks.$eventName missing"
            $allOk = $false
        }
    }
}
catch {
    Write-Err "settings.json invalid: $_"
    $allOk = $false
}

if ($allOk) {
    Write-Host "`nDone! Restart Claude Code for hooks to take effect." -ForegroundColor Green
    Write-Host "Note: exec form uses pythonw; if Python is installed without pythonw.exe, install it or use the plugin install instead." -ForegroundColor Yellow
}
else {
    Write-Host "`nInstall completed with errors. See above." -ForegroundColor Red
    exit 1
}
