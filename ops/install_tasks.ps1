# ============================================================
# ACE 运维 - Windows 计划任务安装脚本 (ID-06 + ID-08)
# ============================================================
#
# 功能：
#   1. 健康检查：每小时巡检一次（静默）
#   2. 完整巡检：每天03:00（含日志轮转）
#   3. 开机自启：开机后5分钟执行一次主循环
#
# 用法（以管理员身份运行PowerShell）：
#   .\install_tasks.ps1          # 安装所有任务
#   .\install_tasks.ps1 -Remove  # 卸载所有任务
#   .\install_tasks.ps1 -Check   # 检查任务状态
#
# 注意：
#   - 需要管理员权限
#   - Python路径自动检测
#   - 任务名称前缀: ACE_

param(
    [switch]$Remove,
    [switch]$Check
)

$ErrorActionPreference = "Stop"

# ---- 路径配置 ----
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BaseDir = Split-Path -Parent $ScriptDir
$PythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $PythonExe) {
    Write-Host "[ERROR] 未找到 python.exe，请先安装 Python 并加入 PATH" -ForegroundColor Red
    exit 1
}

Write-Host "Python 路径: $PythonExe" -ForegroundColor Cyan
Write-Host "项目目录: $BaseDir" -ForegroundColor Cyan
Write-Host ""

# ---- 任务定义 ----
$tasks = @(
    @{
        Name = "ACE_HealthCheck_Hourly"
        Description = "ACE 每小时健康检查（静默）"
        Command = $PythonExe
        Arguments = "`"$ScriptDir\run_checkup.py`" --quiet"
        Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval (New-TimeSpan -Hours 1) -RepetitionDuration ([timespan]::MaxValue)
        StartIn = $BaseDir
    },
    @{
        Name = "ACE_FullCheckup_Daily"
        Description = "ACE 每日完整巡检 + 日志轮转（凌晨3点）"
        Command = $PythonExe
        Arguments = "`"$ScriptDir\run_checkup.py`" --full"
        Trigger = New-ScheduledTaskTrigger -Daily -At 3:00AM
        StartIn = $BaseDir
    },
    @{
        Name = "ACE_Daemon_Boot"
        Description = "ACE 开机自启主循环（开机后5分钟）"
        Command = $PythonExe
        Arguments = "`"$BaseDir\ace_daemon.py`""
        Trigger = New-ScheduledTaskTrigger -AtStartup
        Delay = "0005:00"
        StartIn = $BaseDir
    }
)

# ---- 检查模式 ----
if ($Check) {
    Write-Host "=== ACE 计划任务状态 ===" -ForegroundColor Yellow
    Write-Host ""
    foreach ($task in $tasks) {
        $t = Get-ScheduledTask -TaskName $task.Name -ErrorAction SilentlyContinue
        if ($t) {
            $state = ($t | Get-ScheduledTaskInfo).LastRunTime
            $result = ($t | Get-ScheduledTaskInfo).LastTaskResult
            Write-Host "  [$($t.State)] $($task.Name)" -ForegroundColor Green
            Write-Host "      上次运行: $state, 结果: $result"
        } else {
            Write-Host "  [未安装] $($task.Name)" -ForegroundColor Gray
        }
    }
    Write-Host ""
    exit 0
}

# ---- 卸载模式 ----
if ($Remove) {
    Write-Host "正在卸载 ACE 计划任务..." -ForegroundColor Yellow
    foreach ($task in $tasks) {
        if (Get-ScheduledTask -TaskName $task.Name -ErrorAction SilentlyContinue) {
            Unregister-ScheduledTask -TaskName $task.Name -Confirm:$false
            Write-Host "  [已删除] $($task.Name)" -ForegroundColor Red
        } else {
            Write-Host "  [不存在] $($task.Name)" -ForegroundColor Gray
        }
    }
    Write-Host ""
    Write-Host "卸载完成。" -ForegroundColor Green
    exit 0
}

# ---- 安装模式 ----
Write-Host "正在安装 ACE 计划任务..." -ForegroundColor Yellow
Write-Host ""

foreach ($task in $tasks) {
    # 先删除旧任务
    if (Get-ScheduledTask -TaskName $task.Name -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $task.Name -Confirm:$false
    }

    # 构建动作
    $action = New-ScheduledTaskAction `
        -Execute $task.Command `
        -Argument $task.Arguments `
        -WorkingDirectory $task.StartIn

    # 构建触发器
    $trigger = $task.Trigger

    # 构建设置
    $settings = New-ScheduledTaskSettingsSet `
        -StartWhenAvailable `
        -DontStopIfGoingOnBatteries `
        -AllowStartIfOnBatteries `
        -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
        -RestartCount 3 `
        -RestartInterval (New-TimeSpan -Minutes 5)

    # 如果有延迟，添加到触发器
    if ($task.Delay) {
        $trigger.Delay = $task.Delay
    }

    # 注册任务
    try {
        Register-ScheduledTask `
            -TaskName $task.Name `
            -Description $task.Description `
            -Action $action `
            -Trigger $trigger `
            -Settings $settings `
            -RunLevel Limited `
            -Force | Out-Null

        Write-Host "  [OK] $($task.Name)" -ForegroundColor Green
        Write-Host "       $($task.Description)" -ForegroundColor Gray
    } catch {
        Write-Host "  [FAIL] $($task.Name): $($_.Exception.Message)" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "安装完成！运行以下命令检查状态：" -ForegroundColor Cyan
Write-Host "  .\install_tasks.ps1 -Check" -ForegroundColor White
Write-Host ""
Write-Host "或者在任务计划程序中查看以 ACE_ 开头的任务。" -ForegroundColor Gray
