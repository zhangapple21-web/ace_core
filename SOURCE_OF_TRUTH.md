# ACE Source of Truth

> 基准：2026-10-02。本文记录已核实的运行真源、写入路径、权威关系和未闭环项。
> 它不是新的运行时、任务池、记忆库或治理入口。

## 1. 唯一运行真源

- **Canonical Runtime**：`C:\tmp\ace_core`
- 官方启动入口：`C:\tmp\ace_core\ace.py daemon --serve`
- daemon 实现：`C:\tmp\ace_core\ace_daemon.py`
- 当前 TaskPool：`C:\tmp\ace_core\task_pool`
- 当前 Runtime 状态：`C:\tmp\ace_core\06_RUNTIME\ace\data\`
- 当前 Knowledge：`C:\tmp\ace_core\09_KNOWLEDGE\`
- Recovery 核心：`recovery/restore_from_remote.py` 从 canonical `ace_core` 恢复。

PI 与 MCP 是只读/受治理桥接层，不拥有 ACE 状态、TaskPool、Knowledge 或独立治理权：

- PI adapter：`C:\tmp\ace-host-adapter-lab`
- MCP 默认参数：`--ace-root C:\tmp\ace_core`
- PI plugin 默认 root：`C:\tmp\ace_core`

## 2. 副本分类

| 类别 | 处理原则 | 当前结论 |
|---|---|---|
| canonical | 唯一运行、状态写入和恢复核心 | `C:\tmp\ace_core` |
| host bridge | 只读投影，不是 ACE 副本 | `C:\tmp\ace-host-adapter-lab` |
| recovery / drill | 保留证据，不进入默认运行链 | `C:\tmp\ace_recovery_*`、`D:\tmp\ace_dr_*`、remote-state 目录 |
| archaeology / audit | 保留来源和收据，不授予运行权 | `ace_codex_guard`、审计/恢复证据目录 |
| optional domain | 独立能力域，不替代 ACE 核心 | `ace-video-kingdom`、视频资产目录 |
| UNKNOWN | 未有实际入口、消费者或写入证据时不移动、不删除 | 继续观察 |

目录存在不等于正在运行。任何副本只有在发现实际启动入口、有效消费者和独立状态写入证据后，才可升级为 `ACTIVE_REPLICA`。

## 3. TaskPool admission 权威

TaskPool 是任务状态权威，唯一生产落盘目录为 `task_pool/`。

考古文件的身份由以下字段共同确定：

1. 规范化绝对源路径 `source_ref`；
2. 内容 SHA-256 `source_fingerprint`；
3. `source_type` 与完整 admission/evidence。

相同源路径且相同指纹的未终结任务复用已有任务；内容变化允许产生新的版本任务。旧的动态 `path + mtime + size` 任务记录保留为历史证据，不直接删除。

实现位置：

- `core/file_scanner.py`
- `core/task_admission.py`
- `core/task.py`

生命周期仍必须经过：

`Admission → TaskPool → Researcher → Validator → Guardian → Archivist / Experience`

## 4. 记忆、知识、状态权威关系

宪法层级 `L0-L6` 是规则权威；记忆、经验、治理收据和当前状态属于 `L5 STATE`，不能改写规则。

| 数据 | 当前权威 | 角色 | 非权威/投影 |
|---|---|---|---|
| 生产记忆读写 | `MemoryGateway → MemoryIndex` | 唯一活跃生产记忆入口和后端 | `MemoryKernel` 当前不是生产消费者 |
| 任务状态 | `TaskPool` JSON 状态目录 | pending/active/review/approved/archived 等生命周期权威 | MCP/PI 状态结果只是有界投影 |
| 运行状态 | `06_RUNTIME/ace/data/memory/daemon_state.json` 与 heartbeat | 持久化运行快照/心跳证据 | 快照不能单独证明 liveness |
| 经验沉积 | `ExperienceDeposition` 与受治理 Knowledge 路径 | 记录已通过流程的经验 | 单一 summary、index 或模型输出不能单独授权 |
| 能力候选 | `09_KNOWLEDGE/capability_cards/` | `RESEARCH_READY_NOT_PROMOTED` 候选及 lineage | 不等于生产能力，不等于 provider 路由 |
| MemoryKernel | `core/memory_kernel.py` | staged governance/migration candidate | 不得作为默认读写源或第二索引 |
| Free Zone | `07_SANDBOX/free_research/` | 沙盒实验和候选证据 | `production_integration=false`，不自动晋升 |

DailyLearningLoop 的运行时数据与 canonical Knowledge 已分离：daemon 现在显式将
`ExperienceDeposition` 指向 `C:\tmp\ace_core\09_KNOWLEDGE\`；原
`06_RUNTIME/ace/data/memory/daily_learning/knowledge/` 仅保留历史材料和隔离测试
语义，不再是 daemon 的默认生产写入路径。
当前 `09_KNOWLEDGE/index.json` 的 `DAILY_INDEX_REFS` 为空。daily-learning 分支
目前仅发现 2 个 JSON（其中 1 个 `EXP-*`），canonical 路径发现 920 个 JSON
（其中 761 个 `EXP-*`）。这些数字仅是存量证据，不等于有效学习或生产能力。
最近 34 个每日结果实际为 `NO_VALID_LEARNING_TARGET=20`、`queued_research=12`、
`adopt=1`、`observe=1`。
生产路径已完成单一写入收敛；历史材料不删除，后续由治理生命周期处理。

当前生产 daemon 构造一个 `MemoryGateway(MemoryIndex(...))`，已接线消费者共享该 gateway；MemoryKernel、Hindsight 和旧 Markdown 记忆只按既定候选/迁移边界使用。

## 5. 摄取与能力转化判定

“吃到东西”必须区分四层事实：

1. **摄取**：观察/文件扫描发现来源并形成 evidence；
2. **入池**：通过 admission 写入 TaskPool；
3. **研究转化**：Researcher、Validator、Guardian 形成可复核记录；
4. **能力晋升**：满足独立证据和 production gate，才可进入生产能力。

截至本基准：

- daemon 心跳/快照存在，但最新 heartbeat PID `27332` 不存在，不能称为持续更新；
- 近期存在真实 `Researcher → Validator → Guardian(experience)` → capability card 路径；
- 最新能力卡状态仍为 `RESEARCH_READY_NOT_PROMOTED`；
- 能力卡 `production_integration` 仍为 `false`；
- 因此可以确认“有摄取、有研究、有经验候选”，不能确认“已转化为生产能力”。
- 2026-10-02 的历史输入中混入大量 `ace_codex_guard/state.json` 重复任务；这些历史任务保留，但不应作为每日有效学习量。

## 6. 当前已验证证据

- `ops/run_memory_gateway_caller_audit.py`：`PASS_SINGLE_GATEWAY_RUNTIME_AUDIT`，8 个接线消费者共享单一 gateway。
- `ops/run_continuity_audit.py --check`：`CONTINUITY_VERIFIED`。
- Task admission / archaeology / governance 回归测试通过。
- 最新一次持久化 heartbeat 的 PID `27332` 不存在；`daemon_state.json` 的完整周期记录不能单独证明 daemon 常驻。
- 本轮 P1 审计：`08_GOVERNANCE/P1_KNOWLEDGE_RUNTIME_AUDIT_20261002.md`。

## 7. 未闭环项

- `daemon_state.json` 是持久化快照，不单独证明实时 liveness；以 heartbeat/进程证据共同判断。
- 历史重复任务未删除，等待既有生命周期自然收口或经 Guardian/Archivist 处理。
- `RESEARCH_READY_NOT_PROMOTED` 尚未达到生产能力晋升条件。
- 真实每日“有效摄取量、独立来源数、晋升数”仍需从任务 lineage/独立证据统计，不能用文件数或 capability card 总数代替。
- 任何新的权威关系变更必须经过 baseline → change → test → evaluation → compare，并保留收据。

