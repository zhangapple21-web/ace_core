# Restore Test Result

基线日期：2026-09-30
状态：`BACKUP_COMPLETE / RECOVERABLE`

## 已执行的真实独立演练

- 隔离目录：`D:\tmp\ace_dr_final_20260930`
- 核心 checkout：只从远程 `core/daemon-lifecycle-resilience-20260912` clone，HEAD `2ce7f9068441c0d341d8ed26cec1ea77d72cdbf8`
- 视频 checkout：只从远程 `main` clone，HEAD `27da48891ac778e88689fd1e33cdc058472f9b90`
- `py -3 recovery/bootstrap.py --workspace-root .`：Git/Python/config/目录/compileall PASS；bootstrap pytest `34 passed`；ACE `status` smoke PASS；未读取原工作区源码、缓存或运行态。
- 核心离线专项：`71 passed`（TaskLedger、Worker Capsule、CLI、workspace lock、admission、execution discipline）。
- 视频能力域：JSON parse PASS；生产控制、入口、语音步骤测试 `36 passed`。
- `python ace.py status`：PASS；空 checkout 可初始化 TaskPool、MemoryGateway 和状态结构。
- 冷 checkout 直接 health：预期 `overall=error`，唯一 error 是尚未启动 AceDaemon heartbeat；这不是远程缺文件。
- 启动当前 AceDaemon（`--serve --interval 1 --max-iter 8 --dry-run --force`）后 health：`overall=warning`、`errors=0`、daemon heartbeat/进程归属 PASS，daemon exit `0`；空知识/归档目录仅为非阻断 warning。
- Worker Capsule death drill：`first=HALF_DONE`；lease 过期后 `resume=PASS`，旧 fencing token 被清除并进入 review。
- 视频入口 dry-run：`status=COMPLETED`、`provider_submission=NOT_PERFORMED`、exit `0`。
- `3000/3002`、legacy scheduler/heartbeat：未启动，未成为恢复依赖。

## 判断

恢复链已通过。bootstrap 不会未经授权长期启动 daemon，因此冷 checkout 的 heartbeat error 是预期门槛；在按运维授权启动当前 AceDaemon 后，health gate 采用 `errors == 0`，本次实测通过。外部 Provider、模型权重、私有媒体和真实凭据仍需按人工清单补回，但不阻断核心代码和离线能力复活。

## 必须保留的真实证据

- 核心远程 ref：`origin/core/daemon-lifecycle-resilience-20260912 = 2ce7f9068441c0d341d8ed26cec1ea77d72cdbf8`
- 视频远程 ref：`origin/main = 27da48891ac778e88689fd1e33cdc058472f9b90`
- bootstrap 输出：隔离目录 `ace_core/recovery/bootstrap_report.json`（本地产物，不提交）
- 冷 checkout 的 heartbeat 缺失被如实记录为预期门槛；授权启动当前 AceDaemon 后重新检查得到 `errors=0`，因此没有把冷启动状态伪造成 PASS。
- `MISSING_HUMAN_REQUIRED.md` 中的凭据、CosyVoice 权重、私有媒体仍需安全来源补回。
