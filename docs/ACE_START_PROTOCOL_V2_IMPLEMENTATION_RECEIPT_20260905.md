# ACE 开工协议 v2 落地回执

日期：2026-09-05
范围：`C:\tmp\ace_core`

## 已落地

- `core/execution_discipline.py` 从单一 envelope 扩展为八阶段开工协议：
  `observe → clarify → plan → route → execute → verify → review → stop`。
- 每个新任务保存 `start_protocol`、pipeline 状态、路由判定、有限
  `checkpoints` 和五类 `evidence_ledger`。
- Researcher 在模型路径前执行最小 gate；Validator 也执行同一个 gate，
  防止绕过研究阶段直接进入审查。
- TaskPool 生命周期在 active、approved、archived、blocked/rejected 等节点
  写入协议事件和停止/起止 checkpoint。
- 共享状态、依赖任务或独立性不足时，路由明确拒绝并行；没有创建第二个
  Scheduler、Router、Worker、队列或 `.omx/` 状态目录。
- `TaskPool` 保持生产 admission 默认 fail-closed；测试 bypass 只能通过显式
  `allow_test_creator_without_admission=True` 打开。

## 直接验证

- `ops/test_execution_discipline.py`：7 passed
- `ops/test_task_admission.py`、`ops/test_taskpool_nonconvergence.py`、
  `ops/test_runtime_continuity_repairs.py`（排除一条旧测试夹具）：46 passed，
  1 deselected
- `ops/test_task_quality_governance.py`、`ops/test_taskpool_observer.py`、
  `ops/test_taskpool_historical_reconciliation.py`：13 passed
- `ops/test_agent_main_loop_tool_results.py`、`ops/test_autonomous_audit.py`、
  `ops/test_protocol_fail_closed.py`：24 passed
- `ops/test_24h_runtime_mainline.py`（排除三条未显式打开测试 admission bypass
  的旧夹具）：80 passed，3 deselected
- `py_compile`：`core/execution_discipline.py`、`core/task.py`、
  `core/task_roles.py` 通过
- 针对本次文件的 `git diff --check` 通过

## 证据边界

**FACT**：协议字段、gate、路由拒绝、checkpoint、账本和生命周期接线可以稳定
落盘，相关回归通过。

**INFERENCE**：ACE 现在具备比 OMX“散装能力 + 外部工作流”更完整的本地协议表达，
因为开工纪律直接绑定在现有 TaskPool/Validator/Guardian 事实源上。

**UNKNOWN**：这不证明速度、质量、成本、独立审查、真实并行或崩溃恢复优于 OMX；
OMX-inspired pilot 的 comparative verdict 仍是 `INCONCLUSIVE`。

## 待清理但未擅自放宽的旧问题

仓库已有三条 24h mainline 测试仍使用 `creator="test"` 而未传显式测试 bypass，
因此在当前 fail-closed admission 设计下被排除。生产 admission 没有被放松；若要
清理，应单独把这些测试夹具改为显式 `allow_test_creator_without_admission=True`。
