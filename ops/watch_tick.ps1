# Hourly dead-component watch tick.
#
# Why this lives in the repo: the previous tick script was
# C:\Users\Administrator\AppData\Local\Temp\opencode\ace_watch_tick.ps1, a path
# that gets cleaned. When it vanished, ACE-Watch-Hourly kept firing every hour and
# failing every hour, and the dead_components_snapshot it should refresh went 27
# hours stale - a structural-integrity watch that was silently blind. Nothing
# reported this because nothing watched the watcher.
#
# ASCII-only for the same reason ops/install_tinghe_tasks.ps1 is: PowerShell 5.1
# reads a .ps1 without a BOM in the ANSI codepage, so a CJK literal here would be
# silently mangled.
#
# NOT_DUE is success, not failure. The watch owns a twelve-hour interval
# (MIN_INTERVAL_HOURS) and this task fires hourly, so most ticks are correctly
# no-ops. Treating "snapshot not refreshed" as failure made this script report an
# error on every one of the eleven no-op hours between real runs - a watcher that
# cries wolf is as blind as one that never speaks.

param(
    [string]$RepoRoot = "C:\tmp\ace_core",
    [switch]$Json
)

$ErrorActionPreference = "Stop"

$script = Join-Path $RepoRoot "ops\dead_component_watch.py"
if (-not (Test-Path -LiteralPath $script)) {
    Write-Error "dead_component_watch.py not found under $RepoRoot"
    exit 1
}

# Unbuffered, JSON by default so a caller reads a report instead of prose.
# --force is deliberately NOT passed: the watch owns its interval, and forcing it
# on every tick would rewrite the snapshot hourly and destroy the cadence
# evidence that says when it last actually looked.
$pyArgs = @("-3", "-u", $script, "--root", $RepoRoot, "--json")

$output = & py @pyArgs 2>&1
$exitCode = $LASTEXITCODE

if ($exitCode -ne 0) {
    Write-Error "dead_component_watch exited $exitCode"
    exit $exitCode
}

$status = ""
try {
    $report = $output | Out-String | ConvertFrom-Json
    $status = "$($report.status)"
} catch {
    # Unparseable output is a real failure: the watch either worked and did not
    # say so, or broke while claiming success.
    Write-Error "could not read the watch report as JSON"
    exit 1
}

if ($status -eq "NOT_DUE") {
    # The watch's own interval has not elapsed. Correct behaviour for most hours.
    exit 0
}

if ($status -ne "SCANNED") {
    Write-Error "watch reported unexpected status: $status"
    exit 1
}

# It actually scanned, so the snapshot must be fresh. Checking only here is the
# difference between verifying the work and demanding it happen hourly.
$snapshot = Join-Path $RepoRoot "08_GOVERNANCE\structural_integrity\dead_components_snapshot.json"
if (-not (Test-Path -LiteralPath $snapshot)) {
    Write-Error "watch scanned but wrote no snapshot at $snapshot"
    exit 1
}
$ageMinutes = ((Get-Date) - (Get-Item -LiteralPath $snapshot).LastWriteTime).TotalMinutes
if ($ageMinutes -gt 30) {
    Write-Error "watch scanned but the snapshot is $([math]::Round($ageMinutes, 1)) minutes old"
    exit 1
}

exit 0
