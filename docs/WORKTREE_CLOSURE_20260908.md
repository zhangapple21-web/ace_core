# 工作树收口记录（2026-09-08）

## 目的

把本地工作区整理成可审查、可回溯、可同步的提交边界。远端
`origin/main` 是可移植的云端副本；本地运行态、缓存和临时材料不作为
ACE 的事实或生产能力证明。

## 本次纳入远端

- ACE 运行时与既有控制面上的最小变更：`ace_daemon.py`、`core/` 下的
  路由、凭据隔离、金融窗口、发现、职责和表达组件。
- 对应回归测试：`ops/test_*.py`（能力路由、凭据管理、交易时机、金融窗口）。
- 协议与说明：`ACE_WSET_INSPIRED_LOOP.md`、`docs/ACE_TRADE_TIMING_AND_XIAOYAN_VOICE_20260908.md`。
- 自由区与治理证据：哈希绑定的桥接 receipts、evidence registry、provider
  registry、语义种子、蒸馏/提案/报告，以及 `research/` 中的审查记录。
- 当日可复核产物：`outputs/ACE_CLOSE_REVIEW_*.md` 与
  `outputs/ACE_DAILY_SHIFT_*_PATROL.md`。

## 明确留在本地

- `runtime/`、`media_staging/`、`episodes/`、临时 PowerShell 脚本、锁文件、
  缓存、日志、PNG 和测试运行目录。
- Free Zone 的实验工厂、实验中间物、lazy-cat 生成物及易变的
  `autonomy_state.json` / `model_shift_state.json`。它们可由已有入口重建，
  不是独立生产事实；保留的报告、蒸馏、提案和桥接 receipt 足以复核边界。
- `agent_team/` 与 `archaeology/legacy_runtime/` 的历史协作/考古工作副本，
  本次不混入运行核心提交，避免把主线与历史材料混成一个不可审查的大提交。

## 证据状态

- 当前 Free Zone 最近一次记录为显式隔离实验：`PASS` 仅证明 sandbox 内部
  执行归因；`natural_daemon_cycle=UNKNOWN`、`runtime_proof=false`、
  `production_integration=false`。
- 本地测试：772 项全量通过；本次新增/相关测试 26 项通过；Python 编译与
  `git diff --check` 通过。
- 远端同步前后必须检查 `git status --short --branch` 与提交哈希，不能以
  README、文件存在或一次探针替代运行时验收。

## 恢复路径

1. 从 `origin/main` 克隆并读取 `AGENTS.md`、`README.md`、本记录。
2. 按 `.gitignore` 保留的边界恢复本地运行态，不把生成物当成源码。
3. 重新执行既有审计/测试入口；只有新鲜 receipt 和 sole-daemon 证据才能
   更新生产状态。
