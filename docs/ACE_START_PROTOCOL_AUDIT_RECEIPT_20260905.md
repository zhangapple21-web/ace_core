# ACE 开工协议审计回执层 — 2026-09-05

## 本次补强

在现有 `Task.outputs.execution_discipline` envelope 之上增加了只读审计层：

- `validate_execution_discipline(task)`：检查协议版本、阶段证据结构、事件阶段回退、
  终止原因和轻量分支提示；不调用模型、不创建 Worker、不改变任务状态。
- `protocol_receipt(task)`：生成可 JSON 序列化的紧凑回执，包含任务、协议、复杂度、
  当前状态、最后事件、必需阶段、事件数、未知项数、错误和警告。
- `python ace.py protocol <任务ID>`：通过现有 ACE CLI 只读查看单个任务回执，不运行
  daemon、不推进任务、不发送外部副作用。
- `record_event(..., evidence=...)`：把阶段证据同步放入对应 pipeline 阶段，仍受有限长度
  约束。

## 为什么这比“只写流程文档”更强

OMX 风格工作流可以要求“先计划再做”，但如果状态字段和事件顺序失真，外部流程本身
未必能发现。ACE 现在把协议状态留在现有 TaskPool 单一事实源中，并提供独立的、只读的
自检回执：阶段回退、停止无理由和字段损坏会被明确标为 `valid=false`，不会被包装成
成功。

## 边界

- 这不是第二个 Runtime、Scheduler、Router、TaskPool 或 mailbox。
- 审计层不授予生产、外部发送、provider 或自动接管权限。
- `valid=true` 只表示 envelope 结构和事件记录自洽，不证明速度、质量、成本、独立审查、
  并行或崩溃恢复收益。

## 验证

- `python -m pytest ops/test_execution_discipline.py -q` → `9 passed`
- `python -m pytest ops/test_task_admission.py ops/test_taskpool_nonconvergence.py ops/test_protocol_fail_closed.py -q` → `37 passed`

## 证据分类

- **FACT**：审计函数和回执函数已实现，阶段回退/无停止理由可被检测，相关回归通过。
- **INFERENCE**：ACE 的开工协议现在具有“记录 → 执行 → 自检 → 回执”的闭环，比单纯
  的外部提示词流程更容易审计和恢复。
- **UNKNOWN**：尚未证明 OMX 或 ACE 在真实任务上的速度、质量、成本或并行收益；这些
  仍需独立、对称计时的 Free Zone 实验。
