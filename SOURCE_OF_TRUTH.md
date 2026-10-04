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

## 9b. 治理与复用的合拢边界（2026-10-04）

两端正交：**治理决定存什么，复用决定怎么用**，合拢后仍然各有一个 owner。

| 关注点 | owner | 不做什么 |
|---|---|---|
| 净化 / 等级 / `reference_count` 落盘 | `core/experience_deposition.py` | 不判断“这次复用值不值” |
| 身份键关联 / 提示词注入 / `artifact_contributions` | `core/knowledge_reuse.py` | 不写 Knowledge、不改等级 |

- `reference_count` 是**两个不同对象上的同名字段**，实测确认不是一条链路：
  `Experience.reference_count`（`09_KNOWLEDGE/<tier>/EXP-*.json`）由治理端
  `find_related()` 复用时落盘；`Task.reference_count`（`task_pool/`）是任务账本
  计数，被 `KnowledgeReuseGate.group_of()` 读取。复用模块不 import
  `ExperienceDeposition`，也不 import `Governor`；治理模块不 import
  `knowledge_reuse`。因此"复用触发 Governor 重复判定"在结构上不可能发生。
- `knowledge_join:` 证据被 `core/task_roles.py::_is_reuse_pointer()` 显式排除在
  `Validator._unique_evidence()` 与 prospect 评分之外：指向自家记忆的指针不是
  对世界的独立观察，不能当佐证，也不能推动 evidence signature。
- 注入顺序：`AceDaemon.__init__` 中 `self.knowledge_governor`
  （`__init__` 早期）→ `experience_deposition` → `Guardian` →
  `knowledge_reuse`（`_init_task_lifecycle` 内），两者共用同一个 `task_pool`。
- 合拢验证：`ops/test_knowledge_governance_reuse_merge.py`（4 项）在真实
  `AceDaemon` 上证明：Governor 定级 RULE → intent 任务按身份键命中 →
  `knowledge_join:` 记录指向该 RULE 记录 → 交付产物真的引用后被记为
  contribution → 该指针不算佐证也无法把未验证声明升成规则 → dry-run 只算不写。

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

## 11. 治理↔复用合拢收据（2026-10-04 第二轮）

### 11.1 已合拢的接线

| 关注点 | owner | 运行时落点 |
|---|---|---|
| 净化 / 等级 / `reference_count` | `core/experience_deposition.py` | `EPISTEMIC_STATUS`、`LONG_TERM_TYPES`、`_verification_state` |
| 去重判定 | `core/governance/knowledge_governor.py` | `self.knowledge_governor`（全 runtime 单例） |
| 身份键关联 / 提示词 / 交付溯源 | `core/knowledge_reuse.py` | `KnowledgeReuseGate` + `_run_knowledge_reuse_stage` |

注入顺序：`__init__` 建 `self.knowledge_governor` → `_init_task_lifecycle`
建 `experience_deposition` → 注入 `Guardian` → 建 `knowledge_reuse`；两者共用
同一个 `task_pool`。`Governor(` 在 `ace_daemon.py` 中只出现 1 次。

### 11.2 一处必须纠正的认知

工单原述"Governor 写入的 `reference_count` 能被 `KnowledgeReuseGate` 读取"
**不成立**：这是两个对象上的同名字段。

- `Experience.reference_count` → `09_KNOWLEDGE/<tier>/EXP-*.json`，治理端独占写。
- `Task.reference_count` → `task_pool/`，`KnowledgeReuseGate.group_of()` 读它做
  重复组折叠。

实测：复用挂载后治理记录 `reference_count` 仍为 0。`knowledge_reuse.py`
既不 import `ExperienceDeposition` 也不 import `Governor`，因此"复用触发
Governor 重复判定"在结构上不可能发生，无需再加防护。

### 11.3 补上的一个真实缺口：join index 无人构建

`core/knowledge_reuse.py` 完全信任 `09_KNOWLEDGE/join_index.v1.json`；该文件
缺失/过期/指错时复用阶段静默地什么都不计划，**不报错**。全树无人构建它，
它冻结在 2026-10-03T20:57，且只指向合拢前的记录（168 条中 0 条带
`epistemic_status`）。这是工单验收第 2 项在生产上原本不可达的真实原因。

新增 `ops/build_knowledge_join_index.py`：从 `09_KNOWLEDGE/index.json` +
`task_pool/archived` 只读重建，原子写，非归档任务的记录被丢弃，悬空记录
可见。当前：810 条全部入索引，`RULE=143`、`EVIDENCE=667`，gate
`load_index()` 状态 `OK`。

### 11.4 验收（第 2 项，真实 TaskPool）

`ops/test_knowledge_governance_reuse_merge.py` + 真实池脚本全通过：

```
[PASS] Governor 把已验证记录定为 RULE
[PASS] intent 任务按身份键命中 → knowledge_join:file:b8ee9e195092
[PASS] 命中指向 EXP-RQ-20260823-004-constraint-6368bac88d9b.json（RULE）
[PASS] 交付产物真的引用该 id → artifact_contributions 记账
[PASS] 复用指针不算佐证（unique_evidence=0），也无法升格未验证声明
[PASS] 复用未写 Governor 的 reference_count，且未新增任何 Knowledge 记录
[PASS] dry-run 仍然算得出命中、但一条都不写
```

### 11.5 本轮发生的一次事故与护栏

合拢中我一度用旧快照**整文件覆盖** `ace_daemon.py`，抹掉了复用窗口的
`_reuse_hint_for` / `_record_reuse_contributions` / `_knowledge_reuse_contributions`；
随后发现对方 commit `e0d4ce3` 里的 `ace_daemon.py` **本身就是坏的**
（`_run_task_lifecycle_unlocked` 被截断，SyntaxError）。已从可编译基线重建并
逐条原样回植 7 处接线。

护栏（防止复发）：
- `ops/test_ace_daemon_wiring_guard.py`：文件必须可编译；复用与治理 landmark
  必须在位；用 AST 断言 landmark 是**被调用**的而不只是被 import；
  `Governor(` 必须恰好 1 处。
- `ops/verify_fixes.py` 第 2b 项扩展：补 `_knowledge_reuse_contributions`、
  治理侧 landmark、`EPISTEMIC_STATUS` 组、以及对 `ace_daemon.py` 的**真实编译**
  （此前只做文本断言，损坏文件能通过）。
- 修正 `EPISTEMIC_STATUS` 拼写（原为 `EPSTEMIC_STATUS`）。

### 11.6 提交前的第二次自我否决（重要）

准备提交时才发现：工作树的 `ace_daemon.py` 是从旧快照重建的，因此相对 HEAD
多出 **852/780** 行改动，其中包括

- 另一窗口**未提交**的 worker-router 接线（`self.worker_router` /
  `opencode_worker` / `opencode_workspace` / `_execute_task_with_worker` 完整实现）；
- 一处真实回归：`_run_local_only_work` 里 `update_task` 之后的
  `summary["reviewed"] / ["blocked"]` 记账 4 行被丢掉；
- `self.lifecycle_lock_file` 的赋值（HEAD 在方法内赋值，两处读取用
  `getattr` 兜底，故 HEAD 无此缺口）。

若照此提交，会把别人的 WIP 一起吞掉，并静默回退一处记账逻辑。
因此改为 **以 HEAD 为基线、只叠加本轮治理接线** 重写该文件。

重写后的 diff 收敛为 `18 insertions(+), 3 deletions(-)`，仅触及
`__init__` 与 `_init_task_lifecycle` 两个方法；命名面 0 丢失、仅新增
`knowledge_governor`；函数体长度对比只有这两处变化。

由此新增两条提交前断言（临时脚本，规则已写进
`ops/test_ace_daemon_wiring_guard.py` 与 `ops/verify_fixes.py`）：

1. **命名面双向对比**：HEAD 定义的每个 def/class/属性名都必须在暂存版本里
   仍在（防止"函数还在但函数体被掏空"）。
2. **函数体长度对比**：同名函数长度变化必须能逐条解释。

> 教训：`git diff --stat` 的行数不能当作"改动大小"的证据。1632 行的 diff
> 背后是"基线选错了"，不是"改动很多"。

### 11.7 未闭环

- **生产复用闸门关闭**：`ace_config.json` 无 `knowledge_reuse` 键 →
  `enabled=False`、`mode=dry-run`。上述 knowledge_join 是在真实池上按 canary
  模式验证的；要让它自然发生需要显式改配置（配置决策，未擅自改）。
- **生产重启未执行**：属状态变更，需走 `ACE_Daemon_Boot` 计划任务。当前
  pid 9668 持续存活、心跳正常。
- 全量回归：1292 tests / 17 failures，基线 46，**新增 0**；17 个全部落在
  `capability_routing` / `model_pool_mainline` / `execution_discipline` /
  `task_ledger` / `ds41` / `execution_contract`，无一触及本轮改动模块。
  `test_daemon_service_entrypoint` 对机器负载敏感（单跑 12.2s / 预算 30s，
  6 倍负载 14.3s），非合拢引入。
- 另一窗口的 worker-router WIP（`core/worker_router.py` 及其在
  `ace_daemon.py` 的接线）**未提交**，留给该窗口自己固化；HEAD 对它的引用
  是 try/except fail-closed，不因本次提交改变。

### 11.8 顺带修掉的一个真实运行时故障（活证据）

daemon 今天累计 50 条 `file_scanner` 错误，全部同因：
`[WinError 3] 找不到路径 C:\tmp\ace-host-adapter-lab\...\node_modules\...`。
`FileScanner._scan_new_fragments()` 用 `root.rglob("*")`，而 Windows 对超过
MAX_PATH 的路径直接抛异常 —— `C:\tmp` 下那个 bun 依赖树让**整轮扫描中断**，
于是同一错误每 5 分钟复写一次 `daemon_state.json`，同时真正的碎片一次也没被扫到。

已改为 `os.scandir` 逐层下潜的 `_walk()`：单个不可读子树只记入
`skipped` 并继续；超过 `MAX_PATH` 的路径提前跳过；`scan_and_create()` 把
`unreadable` 计数放进结果而不是抛出。

实测同一根目录：`scanned 15320 / new 3102 / skipped 1`（此前是 0/0/抛异常）。
护栏：`ops/test_file_scanner_path_limit.py`。

