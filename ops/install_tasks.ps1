param(
    [switch]$Remove,
    [switch]$Check
)

$ErrorActionPreference = "Stop"

$ScriptDir = $PSScriptRoot
$BaseDir = Split-Path -Parent $ScriptDir
$PythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $PythonExe) {
    Write-Host "[ERROR] python.exe was not found on PATH" -ForegroundColor Red
    exit 1
}

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
    Command = $PythonExe
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
