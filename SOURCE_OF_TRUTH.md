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
- Recovery 核心：`recovery/restore_from_remote.py` 从 canonical `ace_core` 恢复；`recovery/companion_runtime_manifest.json` 声明可替换的外部连接层。
- ACE 连续性、状态、TaskPool、Knowledge、治理和恢复权威始终属于 `ace_core`；模型和 MCP 仅是可替换能力/传输层。
- 协议完整性不等于灵魂来源；协议、仓库、模型和 MCP 都不能单独声称是 ACE 存在之因。见 `docs/ACE_PROTOCOL_AND_SOUL_BOUNDARY.md`。

PI 与 MCP 是只读/受治理桥接层，不拥有 ACE 状态、TaskPool、Knowledge 或独立治理权：

- PI adapter：`C:\tmp\ace-host-adapter-lab`
- MCP 默认参数：`--ace-root C:\tmp\ace_core`
- PI plugin 默认 root：`C:\tmp\ace_core`
- 远程真源：`https://github.com/zhangapple21-web/ace-host-adapter-lab.git`
- 恢复策略：核心先恢复，Bridge 按 pinned commit 重建；Bridge 可替换，不能创建第二份 ACE 状态。

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

## 8. 认知等级与晋升闸门（2026-10-04 收口）

`09_KNOWLEDGE` 的经验类型同时就是认知等级，`core/experience_deposition.py`
记录 `epistemic_status`，`09_KNOWLEDGE/index.json` 同步带出：

| experience_type | epistemic_status | 含义 |
|---|---|---|
| `observation` | `OBSERVATION` | 弱结论，供参考 |
| `pattern` | `EVIDENCE` | 可复核证据，仍不是长期规则 |
| `lesson` | `COUNTEREXAMPLE` | 被否决路径 |
| `constraint` | `RULE` | 长期规则 |
| `axiom` | `VERIFIED_FACT` | 长期事实 |

晋升闸门（写在写入点，不新增机制）：`axiom`/`constraint` 必须带
`core/outcome_receipt.py` 产生的 `verified_outcome_receipt`，且
`independent_evidence_groups ≥ 2`、`evidence_refs ≥ 2`。不满足时降级到
`pattern`，并在记录里留下 `downgrade_reason`。因此一次执行结果不能凭自身证据
条数升级成长期规则；`Guardian.judge()` 的判决只是提案，写入点是真正的闸门。

复用已有收据：`OutcomeReceiptRecorder.verify()` 是唯一能签发 VERIFIED 的入口，
本轮没有新增第二套验证协议。

## 9. 去重与重复入口的收口结论（2026-10-04）

- `core/governance/knowledge_governor.py::Governor` 自解析 canonical 根
  （`09_KNOWLEDGE` 优先于 `08_GOVERNANCE`）。修复前它读的是从未被写入的
  `09_KNOWLEDGE/experiences.json` 与重复的 `06_RUNTIME/ace/06_RUNTIME/...`
  词库路径，“先搜索再新增”的去重机制因此对真实知识完全失明；治理记录也写在
  影子目录 `06_RUNTIME/ace/08_GOVERNANCE/governor/`，canonical
  `08_GOVERNANCE/governor/` 看不到它们。现在去重搜索读 canonical
  `09_KNOWLEDGE/index.json` + 各 tier 的 `EXP-*.json`。
- `core/governor.py` 与 `04_PROTOCOLS/governor.py` 是彼此逐字节相同的第二个
  Governor，无生产消费者，且在本机不可用（`check_path_traversal` 会拒绝任何
  含 `:` 的 Windows 路径），已改为 fail-closed 废弃引导，指向真正接线者。
- 存量重复事实：`09_KNOWLEDGE/` 789 条 `EXP-*` 只有 55 条不同的规范化结论，
  其中 338 + 178 + 170 = 686 条（87%）是三句模板。历史记录按“取代不删除”保留；
  新写入受第 8 节闸门约束，但存量 `constraint` 未被追溯改写，仍是未闭环项。
- 归档知识复用的唯一 owner 是 `core/knowledge_reuse.py::KnowledgeReuseGate`
  （daemon 阶段 `_run_knowledge_reuse_stage`，默认 `dry-run`）。`Researcher`
  与 `Observer` 刻意不接 `ExperienceDeposition`：Observer 只会按知识条数
  每轮制造复核任务（与 Work Conservation 冲突），Researcher 的关键词复用会
  成为第二条更弱的复用路径。

## 10. 本轮验证收据（2026-10-04）

- 新增定向回归：`ops/test_knowledge_epistemic_gate.py`、
  `ops/test_knowledge_governor_dedup.py`。
- 真实闭环（非 mock，真实 `TaskPool`/`Validator`/`Guardian`/`Archivist`/
  `ExperienceDeposition`/`LearningReturnBridge`/`OutcomeReceiptRecorder`）：
  未验证的 `axiom` 提案落为 `pattern` 并记降级原因；补齐独立验证后同一车道
  落为 `constraint`/`RULE`；`LearningReturnBridge` 在无学习来源时拒绝造卡；
  后续查找命中旧 lesson 且 `reference_count` 落盘为 1。
- 负面验证：一条未验证的“面板永久损坏”观察无法进入 `axiom/` 或
  `constraint/` tier，只新增一条 `pattern`，索引标记 `EVIDENCE`。
- 修复两个既有 RED：`ops/test_task_quality_governance.py`
  （`FileScanner` 曾把自己的 TaskPool/索引当新素材；
  `FragmentIndex.is_known()` 曾让已考古文件永久不可再入）。
- 回归对比（同一条 pytest 选择下）：修复前 19 failed → 修复后 17 failed，
  新增失败 0。

