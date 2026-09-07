# ACE 开工协议 v2

状态：已落地为现有 ACE TaskPool/单 daemon 的协议层，不是第二个 Runtime。

## 目的

把 ACE 已经拥有的能力串成一条默认的、可审计的开工流水线：

```text
observe → clarify → plan → route → execute → verify → review → stop
```

这条链路是任务 envelope 的状态机，不创建 `.omx/`、第二个 Scheduler、第二个
Router、共享 mailbox 或新的事实源。任务仍由 ACE 现有 admission、TaskPool、
Researcher、Validator、Guardian、Archivist 和 continue-gate 负责。

## 每个任务都会得到什么

`Task.outputs.execution_discipline` 现在包含：

- `start_protocol`：协议版本；
- `pipeline`：八阶段状态、是否必需、阶段证据；
- `clarification`：目标、非目标、已知事实、未知项、边界；
- `minimal_plan`：中/复杂任务的三步最小计划；
- `constraints.route`：当前 ACE 生命周期的路由决策；
- `constraints.parallelism_decision`：共享/依赖/独立性不足时明确拒绝并行；
- `checkpoints`：有限长度的可恢复检查点；
- `evidence_ledger`：source/runtime/result/review/unknown 五类证据账本；
- `events`：有限长度的生命周期事件；
- `stop`：完成、证据缺口、未知/失败保留和无剩余动作条件。

## 复杂度分支

- `simple`：轻量分支，不强制产生计划，仍保留验证和停止条件；
- `medium`：目标/边界/未知项/最小计划/验证方法必须存在；
- `complex`：在 medium 之上记录路由和并行拒绝理由，并在研究前写入
  `pre_execution_gate` checkpoint。

## 路由原则

ACE 可以判断“是否存在独立并行候选”，但 v2 默认不启动并行 Worker。下列任何
条件都会进入现有单生命周期：共享状态、依赖任务、独立性没有明确证据、或仅有
OMX/同一 Worker 的自报。并行能力若要成为真实运行能力，必须另做有独立来源、
对称计时、真实中断/接管和冲突记录的 Free Zone 实验。

## 证据和停止

协议记录证据，不制造证据。`UNKNOWN`、`FAILED`、`INCONCLUSIVE` 和 proposal-only
保持原义。任何阶段都可以写 checkpoint；到达 blocked/rejected/archived/graveyard
时由现有 TaskPool 写入 stop 事件。继续工作仍需走已有 continue-before-work gate，
不会因为 checkpoint 存在而自动重放、接管或外发。

## 验收边界

本次实现证明的是协议字段、生命周期接线、最小 gate、路由拒绝和 checkpoint 能够
稳定落盘；它不证明 OMX 的速度、质量、成本、独立审查、并行或崩溃恢复收益。
这些仍然是待验证的实验命题，不能由协议存在本身推出。
