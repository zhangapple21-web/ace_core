# Reconstruct the tinghe site's eight scheduled tasks from the repository.
#
# Why this exists: the tasks were registered ad hoc, so the only copy of their
# definitions lived in the Task Scheduler database. A rebuild, a profile reset or
# a wrong edit left nothing to restore from, and no test could tell the
# difference between "registered correctly" and "never registered". The
# definitions now live here, and -Check proves the machine matches them.
#
# Constraints learned by measuring the working tasks rather than assuming:
#
#   1. This file stays ASCII-only. PowerShell 5.1 reads a .ps1 without a BOM in
#      the ANSI codepage, so a CJK literal here would be silently mangled. The
#      site path is recovered from the deployed wrappers - the machine's own
#      record of where its site lives - or supplied with -Site on a fresh host.
#
#   2. Wrappers are written as GBK with CRLF, and their log paths are ABSOLUTE
#      under the site directory. cmd.exe reads a batch file in the OEM codepage,
#      so writing UTF-8 would make the cd fail; a relative log path would write
#      into C:\tmp\tinghe-wrappers instead of the site.
#
#   3. Task Scheduler's COM view is not the cmdlet's view. ExecutionTimeLimit
#      comes back as the string "PT12H", LogonType as the int 3, and
#      DisallowStartIfOnBatteries / StopIfGoingOnBatteries / AllowDemandStart
#      are not parameters of New-ScheduledTaskSettingsSet at all - they are
#      properties. The comparison below uses the COM shapes.
#
#   4. Per-task settings are NOT uniform. genre-check alone runs elevated with a
#      one-hour cap and no battery or wake permission; daily-origin alone retries
#      twice. A shared settings block would silently change both.

[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$Site,
    [string]$WrapperDir = "C:\tmp\tinghe-wrappers",
    [string]$LauncherDir = "C:\tmp",
    [switch]$Check,
    [switch]$Remove,
    # Replace wrappers that already exist. Without it, existing wrappers are left
    # untouched and only reported on, so a stray run cannot clobber a working
    # site.
    [switch]$Force
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
$LauncherSource = Join-Path $RepoRoot "ops\launchers\run-hidden-wait.vbs"

# ---------------------------------------------------------------- task table
# Time: daily fire time. LimitHours: execution cap. Elevated: run as highest.
# BatteryOk: whether the job may start on batteries and continue unplugged.
# Wake: whether it may wake the machine. Restart: retry count and interval.

$TaskTable = @(
    @{ Name = "tinghe-daily-origin"; Time = "08:00"; Script = "run_daily_task.py";
       Args = ""; Log = "daily_run_stdout.log"; Rc = $false;
       LimitHours = 12; Elevated = $false; BatteryOk = $true; Wake = $true;
       RestartCount = 2; RestartIntervalMinutes = 5 },

    @{ Name = "tinghe-genre-check"; Time = "15:10"; Script = "genre_check.py";
       Args = ""; Log = "genre_check.log"; Rc = $true;
       LimitHours = 1; Elevated = $true; BatteryOk = $false; Wake = $false;
       RestartCount = 0; RestartIntervalMinutes = 0 },

    @{ Name = "tinghe-night-repair"; Time = "02:30"; Script = "repair_episodes.py";
       Args = "--max-models 2"; Log = "repair_task.log"; Rc = $false;
       LimitHours = 12; Elevated = $false; BatteryOk = $true; Wake = $true;
       RestartCount = 0; RestartIntervalMinutes = 0 },

    @{ Name = "tinghe-stale-watch"; Time = "09:00"; Script = "check_staleness.py";
       Args = ""; Log = "stale_task.log"; Rc = $true;
       LimitHours = 12; Elevated = $false; BatteryOk = $true; Wake = $true;
       RestartCount = 0; RestartIntervalMinutes = 0 },

    @{ Name = "tinghe-sync-1100"; Time = "11:00"; Script = "verify_daily_sync.py";
       Args = ""; Log = "sync_1100.log"; Rc = $false;
       LimitHours = 12; Elevated = $false; BatteryOk = $true; Wake = $true;
       RestartCount = 0; RestartIntervalMinutes = 0 },

    @{ Name = "tinghe-sync-1400"; Time = "14:00"; Script = "verify_daily_sync.py";
       Args = ""; Log = "sync_1400.log"; Rc = $false;
       LimitHours = 12; Elevated = $false; BatteryOk = $true; Wake = $true;
       RestartCount = 0; RestartIntervalMinutes = 0 },

    @{ Name = "tinghe-sync-1700"; Time = "17:00"; Script = "verify_daily_sync.py";
       Args = ""; Log = "sync_1700.log"; Rc = $false;
       LimitHours = 12; Elevated = $false; BatteryOk = $true; Wake = $true;
       RestartCount = 0; RestartIntervalMinutes = 0 },

    @{ Name = "tinghe-sync-2000"; Time = "20:00"; Script = "verify_daily_sync.py";
       Args = ""; Log = "sync_2000.log"; Rc = $false;
       LimitHours = 12; Elevated = $false; BatteryOk = $true; Wake = $true;
       RestartCount = 0; RestartIntervalMinutes = 0 }
)

# ------------------------------------------------------------------- helpers

function Get-DeployedSite {
    <#
    Recover the site path from a wrapper already on disk. The wrapper is the
    machine's own record of where its site lives; reading it keeps a CJK literal
    out of this ASCII-only script. Returns $null when there is nothing to read,
    which is the honest signal that -Site is required.
    #>
    param([string]$Dir)

    if (-not (Test-Path -LiteralPath $Dir)) { return $null }
    $probe = Get-ChildItem -LiteralPath $Dir -Filter "tinghe-*.cmd" -ErrorAction SilentlyContinue |
             Select-Object -First 1
    if (-not $probe) { return $null }

    $bytes = [System.IO.File]::ReadAllBytes($probe.FullName)
    $text = [System.Text.Encoding]::GetEncoding(936).GetString($bytes)
    foreach ($line in ($text -split "`r?`n")) {
        if ($line -match '^\s*cd\s+/d\s+"(.+)"') { return $Matches[1] }
    }
    return $null
}

function New-WrapperText {
    <#
    Wrapper body. Byte shape matches the working wrappers: @echo off, cd to the
    site, guard on failure, run python unbuffered with both streams redirected,
    optionally record the exit code. Log paths are absolute under the site, as
    they are on disk.
    #>
    param($Task, [string]$SitePath)

    $script = $Task.Script
    if ($Task.Args) { $script = "$script $($Task.Args)" }
    $py = "py -3 -u $script"

    $logPath = Join-Path $SitePath $Task.Log
    $lines = @(
        "@echo off",
        "cd /d `"$SitePath`"",
        "if errorlevel 1 exit /b 1",
        "$py > `"$logPath`" 2>&1"
    )
    if ($Task.Rc) {
        $base = [System.IO.Path]::GetFileNameWithoutExtension($Task.Log)
        $lines += "echo %ERRORLEVEL% > `"$(Join-Path $SitePath "$base.rc")`""
    }
    $lines += "exit /b %ERRORLEVEL%"
    $lines += ""
    return ($lines -join "`r`n")
}

function Get-TaskCom {
    <#
    The COM view of a registered task, because that is where the properties have
    usable types. ExecutionTimeLimit is the string "PT12H", LogonType is the int
    3, and the battery switches are plain booleans. cmdlet objects reshape these
    and a comparison written against the wrong shape flags everything as drift.
    #>
    param([string]$Name)

    $svc = New-Object -ComObject Schedule.Service
    $null = $svc.Connect()
    $folder = $svc.GetFolder('\')
    return $folder.GetTask($Name)
}

function Test-TaskDefinition {
    <#
    Compare a registered task against the table entry. Returns an array of
    mismatched field names; empty means it matches. -Check reports this, and the
    install path re-runs it after registering.
    #>
    param($Task, [string]$WrapperDirPath, [string]$LauncherPath)

    $registered = Get-ScheduledTask -TaskName $Task.Name -ErrorAction SilentlyContinue
    if (-not $registered) { return @("not-registered") }

    # The action must come from the module view: the COM view returns an empty
    # Execute for an exec action, which would flag every task as drift. The
    # settings and principal come from the COM view, where the properties have
    # usable types. Each half is read from the view that actually answers.
    $action = $registered.Actions | Select-Object -First 1
    $trigger = $registered.Triggers | Select-Object -First 1
    $com = Get-TaskCom -Name $Task.Name
    $s = $com.Definition.Settings
    $problems = @()

    $expectedArgs = "//B //nologo `"$LauncherPath`" `"$(Join-Path $WrapperDirPath "$($Task.Name).cmd")`""
    if ($action.Execute -notmatch '(?i)wscript\.exe$') { $problems += "action-execute" }
    if ($action.Arguments -ne $expectedArgs) { $problems += "action-arguments" }
    if ($action.WorkingDirectory -ne $WrapperDirPath) { $problems += "action-workdir" }

    if ([int]$trigger.DaysInterval -ne 1) { $problems += "trigger-not-daily" }
    if ($trigger.StartBoundary.Substring(11, 5) -ne $Task.Time) { $problems += "trigger-time" }

    $expectedLimit = "PT{0}H" -f $Task.LimitHours
    if ("$($s.ExecutionTimeLimit)" -ne $expectedLimit) { $problems += "settings-limit" }
    if (-not $s.Hidden) { $problems += "settings-hidden" }
    if ([int]$s.MultipleInstances -ne 2) { $problems += "settings-multipleinstances" }
    if (-not $s.StartWhenAvailable) { $problems += "settings-startwhenavailable" }
    if ([int]$s.RestartCount -ne $Task.RestartCount) { $problems += "settings-restartcount" }
    if ([bool]$s.WakeToRun -ne [bool]$Task.Wake) { $problems += "settings-wake" }

    # battery switches, in the boolean sense the COM view reports them
    if ([bool]$s.DisallowStartIfOnBatteries -eq [bool]$Task.BatteryOk) { $problems += "settings-battery-disallow" }
    if ([bool]$s.StopIfGoingOnBatteries -eq [bool]$Task.BatteryOk) { $problems += "settings-battery-stop" }

    $wantLevel = if ($Task.Elevated) { 1 } else { 0 }
    if ([int]$com.Definition.Principal.RunLevel -ne $wantLevel) { $problems += "principal-runlevel" }
    if ([int]$com.Definition.Principal.LogonType -ne 3) { $problems += "principal-logontype" }
    if ("$($com.Definition.Principal.UserId)" -notmatch '(^|\\)Administrator$') { $problems += "principal-userid" }
    return $problems
}

function Install-Wrappers {
    <#
    Generate wrappers and compare them byte for byte against what is on disk.
    Nothing is written unless -Apply, and -Apply only reaches a file that is
    missing or different, so a matching wrapper is never touched.
    #>
    param([switch]$Apply)

    $result = @{ Generated = 0; Unchanged = 0; Missing = 0; Stale = 0; Details = @() }
    $gbk = [System.Text.Encoding]::GetEncoding(936)

    foreach ($task in $TaskTable) {
        $path = Join-Path $WrapperDir "$($task.Name).cmd"
        $bytes = $gbk.GetBytes((New-WrapperText -Task $task -SitePath $Site))

        if (Test-Path -LiteralPath $path) {
            $existing = [System.IO.File]::ReadAllBytes($path)
            if ($existing.Length -eq $bytes.Length) {
                $same = $true
                for ($i = 0; $i -lt $bytes.Length; $i++) {
                    if ($existing[$i] -ne $bytes[$i]) { $same = $false; break }
                }
                if ($same) { $result.Unchanged++; continue }
            }
            if (-not $Apply) {
                $result.Stale++
                $result.Details += "$($task.Name): differs from generated"
                continue
            }
            [System.IO.File]::WriteAllBytes($path, $bytes)
            $result.Generated++
        }
        else {
            if (-not $Apply) { $result.Missing++; continue }
            if (-not (Test-Path -LiteralPath $WrapperDir)) {
                New-Item -ItemType Directory -Path $WrapperDir -Force | Out-Null
            }
            [System.IO.File]::WriteAllBytes($path, $bytes)
            $result.Generated++
        }
    }
    return $result
}

function Install-Tasks {
    param([switch]$Apply)

    $result = @{ Registered = 0; Already = 0; Failed = @() }

    foreach ($task in $TaskTable) {
        $problems = Test-TaskDefinition -Task $task -WrapperDirPath $WrapperDir -LauncherPath $LauncherPath
        if (-not $problems) { $result.Already++; continue }
        if (-not $Apply) { continue }

        if ($PSCmdlet.ShouldProcess($task.Name, "register scheduled task")) {
            try {
                $wrapper = Join-Path $WrapperDir "$($task.Name).cmd"

                # -Argument is singular here. The task object's property is
                # Arguments (plural); the cmdlet's parameter is not. Passing the
                # plural form fails parameter binding outright, which is how this
                # was found - the registration probe registered nothing.
                # Note //nologo with both slashes: the checker compares the
                # argument string byte for byte, and a single dash reads as
                # equivalent to wscript but is not the same string.
                $action = New-ScheduledTaskAction `
                    -Execute "$env:SystemRoot\System32\wscript.exe" `
                    -Argument "//B //nologo `"$LauncherPath`" `"$wrapper`"" `
                    -WorkingDirectory $WrapperDir

                $parts = $task.Time.Split(":")
                $at = [datetime]::Today.AddHours([int]$parts[0]).AddMinutes([int]$parts[1])
                $trigger = New-ScheduledTaskTrigger -Daily -At $at

                # DisallowStartIfOnBatteries, StopIfGoingOnBatteries and
                # AllowDemandStart are properties, not cmdlet parameters; setting
                # them here is the only way through the cmdlet.
                #
                # RestartInterval is the opposite case, and the difference is not
                # cosmetic. Passing it as a cmdlet parameter serialises to
                # <Interval>PT5M</Interval>, which the scheduler accepts.
                # Assigning $settings.RestartInterval = (New-TimeSpan ...) after
                # the fact serialises to 00:05:00 instead, and Register-ScheduledTask
                # rejects the XML outright - "(36,28):Interval:00:05:00". Only
                # tinghe-daily-origin sets a retry interval, which is why this
                # stayed hidden until every task's registration was probed.
                $settingsParams = @{
                    Hidden                = $true
                    MultipleInstances     = "IgnoreNew"
                    ExecutionTimeLimit    = New-TimeSpan -Hours $Task.LimitHours
                    StartWhenAvailable    = $true
                    Priority              = 7
                    RestartCount          = $Task.RestartCount
                    WakeToRun             = [bool]$Task.Wake
                }
                if ($Task.RestartIntervalMinutes -gt 0) {
                    $settingsParams["RestartInterval"] = New-TimeSpan -Minutes $Task.RestartIntervalMinutes
                }
                $settings = New-ScheduledTaskSettingsSet @settingsParams
                $settings.AllowDemandStart = $true
                if ($task.BatteryOk) {
                    $settings.DisallowStartIfOnBatteries = $false
                    $settings.StopIfGoingOnBatteries = $false
                }
                else {
                    $settings.DisallowStartIfOnBatteries = $true
                    $settings.StopIfGoingOnBatteries = $true
                }

                $runLevel = if ($task.Elevated) { "Highest" } else { "Limited" }
                $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel $runLevel

                if (Get-ScheduledTask -TaskName $task.Name -ErrorAction SilentlyContinue) {
                    Unregister-ScheduledTask -TaskName $task.Name -Confirm:$false
                }

                Register-ScheduledTask `
                    -TaskName $task.Name `
                    -Description "tinghe-archive site job: $($task.Script) (reconstructed from ops/install_tinghe_tasks.ps1)" `
                    -Action $action `
                    -Trigger $trigger `
                    -Settings $settings `
                    -Principal $principal `
                    -Force | Out-Null
                $result.Registered++
            }
            catch {
                $result.Failed += "$($task.Name): $($_.Exception.Message)"
            }
        }
    }
    return $result
}

# --------------------------------------------------------------- site resolve

if (-not $Site) {
    $Site = Get-DeployedSite -Dir $WrapperDir
    if (-not $Site) {
        Write-Host "[ERROR] no -Site given and none recoverable from $WrapperDir; pass -Site." -ForegroundColor Red
        exit 1
    }
    Write-Host "[info] site recovered from deployed wrappers" -ForegroundColor DarkGray
}
if (-not (Test-Path -LiteralPath $Site)) {
    Write-Host "[ERROR] site does not exist: $Site" -ForegroundColor Red
    exit 1
}
if (-not (Test-Path -LiteralPath $LauncherSource)) {
    Write-Host "[ERROR] launcher source missing from the repo: $LauncherSource" -ForegroundColor Red
    exit 1
}

$LauncherPath = Join-Path $LauncherDir "run-hidden-wait.vbs"

# --------------------------------------------------------------------- modes

if ($Remove) {
    foreach ($task in $TaskTable) {
        if (Get-ScheduledTask -TaskName $task.Name -ErrorAction SilentlyContinue) {
            if ($PSCmdlet.ShouldProcess($task.Name, "remove scheduled task")) {
                Unregister-ScheduledTask -TaskName $task.Name -Confirm:$false
                Write-Host "[removed] $($task.Name)" -ForegroundColor Red
            }
        }
        else { Write-Host "[not installed] $($task.Name)" -ForegroundColor DarkGray }
    }
    exit 0
}

if ($Check) {
    Write-Host "tinghe scheduled-task status" -ForegroundColor Yellow
    $bad = 0
$missed = 0
    foreach ($task in $TaskTable) {
        $problems = Test-TaskDefinition -Task $task -WrapperDirPath $WrapperDir -LauncherPath $LauncherPath
        if (-not (Get-ScheduledTask -TaskName $task.Name -ErrorAction SilentlyContinue)) {
            Write-Host "[not installed] $($task.Name)" -ForegroundColor Red
            $bad++
            continue
        }
        $info = Get-ScheduledTask -TaskName $task.Name | Get-ScheduledTaskInfo
        if ($problems) {
            Write-Host "[drift] $($task.Name) -> $($problems -join ',')" -ForegroundColor Red
            $bad++
        }
        elseif ($info.NumberOfMissedRuns -gt 0) {
            # A correct definition that did not fire is not "ok". These tasks run
            # as InteractiveToken, so they cannot start when nobody is logged on:
            # on 2026-10-17 the user was logged out at 02:59, the machine rebooted
            # at 03:02, and the next logon was 11:31 - so the 08:00 and 11:00 slots
            # were skipped while this audit still printed eight [ok] lines, because
            # it only printed LastRunTime and LastTaskResult and never asked
            # whether the trigger had actually fired.
            #
            # Reported as its own category so the cause is not mistaken for drift,
            # and warned rather than failed: a missed run is evidence about the
            # machine's session, not about the installer's correctness, so it must
            # not turn a definition check red. Re-registering does not fix it -
            # StartWhenAvailable cannot recover a window during which no session
            # existed.
            $missed++
            Write-Host ("[missed] {0} last={1} result={2} missed={3}" -f `
                $task.Name, $info.LastRunTime, $info.LastTaskResult, $info.NumberOfMissedRuns) `
                -ForegroundColor Yellow
            Write-Host ("         the trigger did not fire: these tasks need a logged-on session " +
                "(InteractiveToken); run the site's catch-up if that day's content matters") `
                -ForegroundColor Yellow
        }
        else {
            Write-Host "[ok] $($task.Name) last=$($info.LastRunTime) result=$($info.LastTaskResult)" -ForegroundColor Green
        }
    }
    $launcherOk = (Test-Path -LiteralPath $LauncherPath) -and
                  ([System.IO.File]::ReadAllBytes($LauncherPath).Length -eq [System.IO.File]::ReadAllBytes($LauncherSource).Length)
    Write-Host "[$(if ($launcherOk) { 'ok' } else { 'drift' })] launcher deployed at $LauncherPath" -ForegroundColor $(if ($launcherOk) { 'Green' } else { 'Red' })
    $wrappers = Install-Wrappers
    $wrapperBad = ($wrappers.Missing + $wrappers.Stale) -gt 0
    Write-Host "[$(if ($wrapperBad) { 'drift' } else { 'ok' })] wrappers: $($wrappers.Unchanged) match, $($wrappers.Stale) stale, $($wrappers.Missing) missing" -ForegroundColor $(if ($wrapperBad) { 'Red' } else { 'Green' })
    if ($wrapperBad) { $wrappers.Details | ForEach-Object { Write-Host "        $_" -ForegroundColor Red } }
    # Missed runs are summarised separately and do NOT fail the audit: the
    # definitions are correct, the machine simply had no session at trigger time.
    # Failing here would conflate "the installer is wrong" with "the machine was
    # logged out", and the second one is not something re-registering can fix.
    if ($missed -gt 0) {
        Write-Host "[warning] $missed task(s) did not fire since their last run (see [missed] above)" -ForegroundColor Yellow
    }
    exit $(if (($bad -gt 0) -or (-not $launcherOk) -or $wrapperBad) { 1 } else { 0 })
}

# ------------------------------------------------------------------ install

Write-Host "installing tinghe site tasks" -ForegroundColor Yellow
Write-Host "  wrappers: $WrapperDir" -ForegroundColor DarkGray
Write-Host "  launcher: $LauncherPath" -ForegroundColor DarkGray

if ($PSCmdlet.ShouldProcess("run-hidden-wait.vbs", "deploy launcher into $LauncherDir")) {
    Copy-Item -LiteralPath $LauncherSource -Destination $LauncherPath -Force
    $deployed = [System.IO.File]::ReadAllBytes($LauncherPath)
    $source = [System.IO.File]::ReadAllBytes($LauncherSource)
    if ($deployed.Length -ne $source.Length) {
        Write-Host "[ERROR] launcher deployed but length differs from the repo copy" -ForegroundColor Red
        exit 1
    }
    Write-Host "[deployed] launcher" -ForegroundColor Green
}

$wrappers = Install-Wrappers -Apply:$Force
Write-Host "[wrappers] $($wrappers.Unchanged) already match, $($wrappers.Generated) written" -ForegroundColor Green
if (-not $Force) {
    $wrappers.Details | ForEach-Object { Write-Host "        $_ (pass -Force to replace)" -ForegroundColor Yellow }
}

$tasks = Install-Tasks -Apply:$true
Write-Host "[tasks] $($tasks.Registered) registered, $($tasks.Already) already correct" -ForegroundColor Green
if ($tasks.Failed.Count -gt 0) {
    Write-Host "[failed]" -ForegroundColor Red
    $tasks.Failed | ForEach-Object { Write-Host "   $_" -ForegroundColor Red }
    exit 1
}

# Registering successfully is not the same as registering correctly. Re-read
# every definition back and refuse to report success on anything less.
$drift = @()
foreach ($task in $TaskTable) {
    $problems = Test-TaskDefinition -Task $task -WrapperDirPath $WrapperDir -LauncherPath $LauncherPath
    if ($problems) { $drift += "$($task.Name): $($problems -join ',')" }
}
if ($drift.Count -gt 0) {
    Write-Host "[DRIFT] registered but does not match the declared contract:" -ForegroundColor Red
    $drift | ForEach-Object { Write-Host "   $_" -ForegroundColor Red }
    exit 1
}
Write-Host "[verified] all $($TaskTable.Count) tasks match the declared contract" -ForegroundColor Green
exit 0
