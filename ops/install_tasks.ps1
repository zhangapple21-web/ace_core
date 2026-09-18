param(
    [switch]$Remove,
    [switch]$Check
)

$ErrorActionPreference = "Stop"

$ScriptDir = $PSScriptRoot
$BaseDir = Split-Path -Parent $ScriptDir

function Resolve-AcePython {
    $candidates = @(
        $env:ACE_PYTHON,
        (Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"),
        "C:\Users\Administrator\AppData\Local\Programs\Python\Python311\python.exe"
    )
    foreach ($candidate in $candidates) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            return $candidate
        }
    }
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd -and $cmd.Source -and ($cmd.Source -notmatch 'WindowsApps')) {
        return $cmd.Source
    }
    return $null
}

$PythonExe = Resolve-AcePython
if (-not $PythonExe) {
    Write-Host "[ERROR] real python.exe was not found (WindowsApps stub is ignored)" -ForegroundColor Red
    exit 1
}

# pythonw keeps the boot/liveness probe off the desktop.
$PythonW = Join-Path (Split-Path -Parent $PythonExe) "pythonw.exe"
$LaunchExe = if (Test-Path -LiteralPath $PythonW) { $PythonW } else { $PythonExe }

$DaemonScript = Join-Path -Path $BaseDir -ChildPath "ace.py"
$DaemonArguments = '"{0}" daemon --serve' -f $DaemonScript
$BootTrigger = New-ScheduledTaskTrigger -AtStartup
$LivenessTrigger = New-ScheduledTaskTrigger -Once `
    -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes 10) `
    -RepetitionDuration (New-TimeSpan -Days 1)
$tasks = @(@{
    Name = "ACE_Daemon_Boot"
    Description = "ACE boot daemon main loop"
    Command = $LaunchExe
    Arguments = $DaemonArguments
    Trigger = @($BootTrigger, $LivenessTrigger)
    Delay = "PT5M"
    StartIn = $BaseDir
})

if ($Check) {
    Write-Host "ACE scheduled task status" -ForegroundColor Yellow
    foreach ($task in $tasks) {
        $registeredTask = Get-ScheduledTask -TaskName $task.Name -ErrorAction SilentlyContinue
        if ($registeredTask) {
            $taskInfo = $registeredTask | Get-ScheduledTaskInfo
            Write-Host "[$($registeredTask.State)] $($task.Name) last run: $($taskInfo.LastRunTime), result: $($taskInfo.LastTaskResult)" -ForegroundColor Green
        } else {
            Write-Host "[not installed] $($task.Name)" -ForegroundColor Gray
        }
    }
    exit 0
}

if ($Remove) {
    foreach ($task in $tasks) {
        if (Get-ScheduledTask -TaskName $task.Name -ErrorAction SilentlyContinue) {
            Unregister-ScheduledTask -TaskName $task.Name -Confirm:$false
            Write-Host "[removed] $($task.Name)" -ForegroundColor Red
        } else {
            Write-Host "[not installed] $($task.Name)" -ForegroundColor Gray
        }
    }
    exit 0
}

foreach ($task in $tasks) {
    if (Get-ScheduledTask -TaskName $task.Name -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $task.Name -Confirm:$false
    }

    $action = New-ScheduledTaskAction `
        -Execute $task.Command `
        -Argument $task.Arguments `
        -WorkingDirectory $task.StartIn
    $executionTimeLimit = [timespan]::Zero
    $settings = New-ScheduledTaskSettingsSet `
        -Hidden `
        -StartWhenAvailable `
        -DontStopIfGoingOnBatteries `
        -AllowStartIfOnBatteries `
        -ExecutionTimeLimit $executionTimeLimit `
        -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 5)

    if ($task.Delay) {
        $BootTrigger.Delay = $task.Delay
    }

    $principal = New-ScheduledTaskPrincipal `
        -UserId ("{0}\{1}" -f $env:USERDOMAIN, $env:USERNAME) `
        -LogonType Interactive `
        -RunLevel Limited

    try {
        Register-ScheduledTask `
            -TaskName $task.Name `
            -Description $task.Description `
            -Action $action `
            -Trigger $task.Trigger `
            -Settings $settings `
            -Principal $principal `
            -Force | Out-Null
        Write-Host "[installed] $($task.Name)" -ForegroundColor Green
    } catch {
        Write-Host "[failed] $($task.Name): $($_.Exception.Message)" -ForegroundColor Red
        exit 1
    }
}
