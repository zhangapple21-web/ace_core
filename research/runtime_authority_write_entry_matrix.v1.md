# Runtime authority write-entry matrix v1

日期：2026-09-06（Asia/Shanghai）  
结论范围：已发现的 Python 生命周期与写入口；不是全仓库 syscall/ACL 封锁证明。历史条目保留，但本矩阵以本轮已验证收口状态为当前判定。

## Matrix

| 入口 / 边界 | 当前判定 | 已验证事实 | 明确边界 / 剩余风险 |
|---|---|---|---|
| `AceDaemon` | `SOLE_MODERN_PRODUCTION_RUNTIME` | 唯一现代生产运行时；统一承载生产 daemon 生命周期、TaskPool 和 heartbeat | 不是全仓库任意文件写入的 ACL 证明 |
| `ace.py daemon/run/once/submit` | `OBSERVED_GUARD` | 路由到 `AceDaemon` / `core.ace_start.run_runtime` | 只覆盖公开 CLI |
| `ace.py start`、顶层 `ace_start.py task` | `OBSERVED_GUARD` | `core.ace_start.ace_start` 要求 execution envelope，再调用 `TaskPool.claim_task` | 只覆盖这两个入口 |
| `TaskPool.create_task` | `STRICT_ADMISSION_GUARD` | 生产调用要求 Admission；不再以公开配置、creator 字符串或 CLI 启用缺失 Admission | 测试边界不构成生产写入口 |
| `TaskPool.claim_task/renew_lease/move_task/update_task` | `OBSERVED_GUARD` | owner/claim/fencing/transition 回归通过 | 不能阻止绕过 API 的直接文件写入 |
| `ops.independent_acceptance` | `READ_ONLY_VERIFIER` | 独立进程直读、前后 hash、回执绑定、无 Runtime mutation | 只证明受测 TaskPool/start 路径 |
| `core.scheduler.Scheduler` | `FAIL_CLOSED` | legacy lifecycle 已 fail-closed | 保留历史源码不等于完成 ACL 级隔离 |
| `core.task_queue.TaskQueue` | `FAIL_CLOSED` | legacy queue 已 fail-closed | 任意脚本直接写旧目录仍不是 ACL 级封锁 |
| `04_PROTOCOLS/heartbeat` | `FAIL_CLOSED` | 历史 heartbeat 不可执行，不能启动旧循环或写入旧状态 | 仅确认该已发现 legacy 入口 |
| 生产 heartbeat | `DAEMON_OWNED` | `owner=ace_daemon`，记录包含 `run_id` | cron/外部调度上下文的运行归属仍应按实际运行记录审计 |
| `.workspace.write.lock` | `DAEMON_LIFECYCLE_GUARD` | `AceDaemon` 生命周期获取并释放；冲突返回 `workspace_write_locked`、`owner`、`run_id`、`lock_file`、`recommendation`；malformed lock fail-closed | 非 daemon 直接文件写入不在此锁的 ACL 覆盖范围内 |
| `agent_team.active_work_manifest` | `OBSERVED_GUARD` | owner/TTL/窗口冲突只决定 read-only；不接管 TaskPool | 所有窗口工具是否调用 guard 未全量证明 |
| project cron 自动化 | `CONFIG_OBSERVED` | 绑定 project，不绑定具体终端 | 不等于每次运行都有稳定 thread owner |
| 3000 LiteLLM/OneAPI | `INDEPENDENT_REPORTING_REQUIRED` | 与 3002 分开报告；catalog 包含 `gpt-5.6-sol` | 3002 成功不能覆盖 3000；3000 诊断保持独立风险 |
| 3002 Responses 兼容层 | `INDEPENDENT_REPORTING_REQUIRED` | 与 3000 分开报告；catalog 包含 `gpt-5.6-sol` | 3000 结果不能覆盖 3002 |
| `OneAPIProvider` 与 SurvivalLoop OneAPI | `MODEL_PRECHECK_FAIL_CLOSED` | `/chat/completions` 前校验 `/models`；未知模型返回不可重试的 `model_unavailable` | catalog 的实时变化仍须按独立端口/路径重新验证 |

## Applied patch

本轮已验证的收口包括：`AceDaemon` 唯一现代生产运行时、legacy Scheduler/TaskQueue/协议 heartbeat fail-closed、daemon-owned heartbeat identity、workspace 写锁生命周期、3000/3002 独立报告，以及 OneAPI 模型目录预检。旧源文件没有删除；这些修复不扩大为任意脚本或任意文件系统写入的 ACL 级封锁。

## Acceptance

- `ops/test_legacy_cli_fail_closed.py`：旧 CLI 不加载/不构造 legacy runtime，直接构造 `Scheduler` / `TaskQueue` 也 fail-closed。
- heartbeat 回归：生产记录含 `owner=ace_daemon` 与 `run_id`；`04_PROTOCOLS/heartbeat` fail-closed。
- workspace lock 回归：daemon 生命周期获取/释放；活跃冲突返回完整 `workspace_write_locked` 诊断；malformed lock fail-closed。
- OneAPI 回归：`OneAPIProvider` 和 SurvivalLoop 都在 `/chat/completions` 前查询 `/models`，未知模型为不可重试的 `model_unavailable`。
- 3000 与 3002 catalog 分别验证并均包含 `gpt-5.6-sol`；端口健康和目录结果必须分别保留。
- 全量 `pytest`：`744 passed`；`compileall`：通过；`git diff --check` 仅报告既有 EOF 空行和一处既有尾随空格。

## Not claimed / remaining risks

这不是“整个 checkout 已经干净”或“全仓库写入已被 ACL 封锁”的结论。任意脚本仍可能绕过 API 直接写文件；所有窗口工具是否调用 manifest guard 未全量证明；cron/外部调度的实际线程归属仍须以运行记录审计。3000 与 3002 是独立路由面：任何一侧的成功、失败或 catalog 都不能推断另一侧状态。manifest、report、receipt、learning 或 model output 不能反向改变 Runtime。
