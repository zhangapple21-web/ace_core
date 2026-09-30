# Restore Test Result

基线日期：2026-09-30
状态：`NOT_RUN / BLOCKED`

## 原因

本次执行开始时，两个核心仓库均存在大量未提交修改；视频仓库还存在约 2.74 GiB 的未跟踪/生成资产，其中单个 watchdog 日志约 2.79 GiB。为避免覆盖、删除或误推送当前工作，先完成清单和恢复入口，再进行选择性提交、推送和隔离 clone。

## 必须记录的真实证据

- 核心仓库恢复提交 SHA 与远程 ref：`PENDING`
- 视频仓库恢复提交 SHA 与远程 ref：`PENDING`
- 隔离恢复目录：`PENDING`
- bootstrap 完整输出：`PENDING`
- compile/import 结果：`PENDING`
- 基础 pytest 结果：`PENDING`
- `ops/health_check.py`：`PENDING`
- TaskPool / lease / fencing smoke：`PENDING`
- 视频入口 dry-run（不提交 Provider）：`PENDING`
- 需要人工补回项：见 `MISSING_HUMAN_REQUIRED.md`

## 验收规则

未填入上述真实命令与输出前，不得把状态写成 `BACKUP_COMPLETE / RECOVERABLE`。
