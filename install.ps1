# install.ps1 - Claude Code Hooks installer for Windows
# Usage:
#   iwr https://raw.githubusercontent.com/BaixuanZhu/claude-code-hooks/main/install.ps1 -UseBasicParsing | iex
#
# Idempotent: safe to re-run. Overwrites .pyw files and merges into settings.json.

$ErrorActionPreference = "Stop"

$RepoOwner = "BaixuanZhu"
$RepoName  = "claude-code-hooks"
$BaseUrl   = "https://raw.githubusercontent.com/$RepoOwner/$RepoName/main"

$HooksDir  = Join-Path $env:USERPROFILE ".claude\hooks\scripts"
$SettingsPath = Join-Path $env:USERPROFILE ".claude\settings.json"
$Scripts   = @(
    "permission_request.pyw",
    "ask_user_question.pyw",
    "stop_notify.pyw",
    "exit_plan_mode_notify.pyw"
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
    Write-Ok "No existing settings.json — will create new"
}

# Ensure 'hooks' is a hashtable-like object (PSCustomObject)
if (-not ($settings.PSObject.Properties.Name -contains 'hooks') -or $null -eq $settings.hooks) {
    $settings | Add-Member -NotePropertyName 'hooks' -NotePropertyValue ([PSCustomObject]@{}) -Force
}

# Ensure 'hooks.<Event>' is an array of matchers
function Ensure-EventList($obj, $eventName) {
    $existing = $obj.PSObject.Properties[$eventName]
    if ($null -eq $existing -or $null -eq $obj.$eventName) {
        $obj | Add-Member -NotePropertyName $eventName -NotePropertyValue @() -Force
    }
}

# Build the target config
$permissionMain = [PSCustomObject]@{
    matcher = "Bash|Edit|Write|Read|Glob|Grep|WebFetch|WebSearch|mcp__.*"
    hooks   = @(@{ type = "command"; command = "pythonw ~/.claude/hooks/scripts/permission_request.pyw" })
}
$permissionExit = [PSCustomObject]@{
    matcher = "ExitPlanMode"
    hooks   = @(@{ type = "command"; command = "pythonw ~/.claude/hooks/scripts/exit_plan_mode_notify.pyw" })
}
$preAsk = [PSCustomObject]@{
    matcher = "AskUserQuestion"
    hooks   = @(@{ type = "command"; command = "pythonw ~/.claude/hooks/scripts/ask_user_question.pyw" })
}
$stopHook = [PSCustomObject]@{
    matcher = $null
    hooks   = @(@{ type = "command"; command = "pythonw ~/.claude/hooks/scripts/stop_notify.pyw" })
}

# PermissionRequest: replace or add both matchers
Ensure-EventList $settings.hooks "PermissionRequest"
$prList = @($settings.hooks.PermissionRequest)
# Drop existing ExitPlanMode entry (we own that now)
$prList = @($prList | Where-Object { $_.matcher -ne "ExitPlanMode" })
# Drop existing main matcher (we own that now)
$prList = @($prList | Where-Object { $_.matcher -ne "Bash|Edit|Write|Read|Glob|Grep|WebFetch|WebSearch|mcp__.*" })
# Append ours
$prList += $permissionMain
$prList += $permissionExit
$settings.hooks.PermissionRequest = $prList

# PreToolUse: add AskUserQuestion if not present
Ensure-EventList $settings.hooks "PreToolUse"
$ptList = @($settings.hooks.PreToolUse)
if (-not ($ptList | Where-Object { $_.matcher -eq "AskUserQuestion" })) {
    $ptList += $preAsk
}
$settings.hooks.PreToolUse = $ptList

# Stop: add ours if not present
Ensure-EventList $settings.hooks "Stop"
$stList = @($settings.hooks.Stop)
$hasStopHook = $false
foreach ($entry in $stList) {
    if ($entry.hooks) {
        foreach ($h in $entry.hooks) {
            if ($h.command -like "*stop_notify.pyw*") { $hasStopHook = $true; break }
        }
    }
}
if (-not $hasStopHook) {
    $stList += $stopHook
}
$settings.hooks.Stop = $stList

# Write back
$json = $settings | ConvertTo-Json -Depth 10
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
    Get-Content $SettingsPath -Raw | ConvertFrom-Json | Out-Null
    Write-Ok "settings.json is valid JSON"
}
catch {
    Write-Err "settings.json invalid: $_"
    $allOk = $false
}

if ($allOk) {
    Write-Host "`nDone! Restart Claude Code for hooks to take effect." -ForegroundColor Green
}
else {
    Write-Host "`nInstall completed with errors. See above." -ForegroundColor Red
    exit 1
}
