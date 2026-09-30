# Restore Test Result

基线日期：2026-09-30
状态：`PARTIAL / BLOCKED`

## 已执行的真实独立演练

- 隔离目录：`D:\tmp\ace_dr_verify_20260930`
- 核心 checkout：只从远程 `core/daemon-lifecycle-resilience-20260912` clone，HEAD `213910155c9574cc75fb0459213785c85d44abfd`
- 视频 checkout：只从远程 `main` clone，HEAD `6d9b9ab8b6745bcc728f0693463b6de1e9bfe234`
- `py -3 recovery/bootstrap.py --workspace-root .`：compileall PASS；ACE `status` smoke PASS；未读取当前工作区源码、缓存或运行态。
- 核心离线测试：`27 passed`（TaskLedger、MemoryGateway、MemoryIndex recovery、cognitive think gate）。
- 视频能力域测试：`53 passed`（生产控制、入口、语音步骤、persona/reference/conflict 测试集）。
- `python ace.py status`：PASS；空 checkout 可初始化 TaskPool、MemoryGateway 和状态结构。
- `ops/health_check.py --json`：确实执行，但冷 checkout 返回 `overall=error`，唯一 error 是没有正在运行的 AceDaemon heartbeat；经验库为空仅为 warning。
- `3000/3002`、legacy scheduler/heartbeat：未启动，未成为恢复依赖。

## 当前阻断与判断

这不是“远程不可恢复”：核心源码、协议、schema、测试、配置模板与 bootstrap 已从远程独立取回并通过编译、单元测试和入口 smoke。

但还不能把结果标成 `BACKUP_COMPLETE / RECOVERABLE`，因为生产 health check 要求活动 daemon heartbeat，而 bootstrap 不应在新机器上未经授权长期启动生产 daemon。新机器完成私密配置注入并按运维授权启动当前 AceDaemon 后，必须重新运行 health check，并补跑 TaskPool lease/fencing 专项收据。

## 必须保留的真实证据

- 核心远程 ref：`origin/core/daemon-lifecycle-resilience-20260912 = 213910155c9574cc75fb0459213785c85d44abfd`
- 视频远程 ref：`origin/main = 6d9b9ab8b6745bcc728f0693463b6de1e9bfe234`
- bootstrap 输出：隔离目录 `ace_core/recovery/bootstrap_report.json`（本地产物，不提交）
- 当前失败不是伪造 PASS：health 的 daemon heartbeat 缺失被记录为阻断。
- `MISSING_HUMAN_REQUIRED.md` 中的凭据、CosyVoice 权重、私有媒体仍需安全来源补回。
