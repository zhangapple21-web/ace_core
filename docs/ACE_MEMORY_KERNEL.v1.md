# ACE Memory Kernel v1

## 状态收口（2026-09-29 更新）

**当前结论：MemoryKernel 不能切生产默认；`MemoryIndex` 仍是唯一生产存储后端，并由 `MemoryGateway` 作为唯一运行时入口；Hindsight 是 MemoryKernel 内部检索策略。** 活跃调用方统一和真实 PRIVATE 数据副本回滚演练已完成；这不等于候选检索 A/B、治理复核或生产切换已通过。

| 收口项 | 当前状态 |
| --- | --- |
| 批次审计 | 已落实；`selected_by` 是调用方声明值，不是认证身份。 |
| 量化门槛 | 已接入评估器；没有合格的独立标注集和真实 A/B 收据，指标未通过。 |
| 调用方统一 | 活跃 daemon 运行时 8 个已接线消费者共享一个 `MemoryGateway`；CLI 旧记忆命令 fail-closed，Markdown 记忆骨架为迁移专用。哈希绑定收据：`08_GOVERNANCE/evidence/memory_gateway_caller_unification_20260928.json`。 |
| 真实数据回滚 | 当前快照 6,985 条真实 PRIVATE 数据副本演练 `PASS_REAL_PRIVATE_DATA_BACKEND_ROLLBACK_REHEARSAL`；未触碰生产文件，未做生产切换。 |
| 一次性切换清单 | 已列出；未执行，不切生产。 |
| 独立提交 | `7cb943b`，已本地提交、未推送；来源和推送边界见下方记录。 |

**下一道门：**

> 先用真实本地、独立标注的查询集完成预注册 A/B 和隐私/并发评估，再经过既有治理复核；只有全门通过才可在一次维护窗口切换。之前保持 `MemoryIndex` 默认，不做隐式双读或双写。

**真实数据副本演练收据：**

- `06_RUNTIME/ace/data/memory/evidence/real_memory_backend_rollback_20260929.json`：2026-09-29 00:31（本地时间）快照为 6,985 条、全部 `PRIVATE`；从其中显式选择 50 条仅导入临时目录中的候选 Kernel，批次收据完整，候选只读查询有回执。旧收据 `real_memory_backend_rollback_20260928.json` 保留为历史快照证据。
- 临时目录中对候选事件账本注入损坏，Kernel 正确 fail-closed；回绑到旧 `MemoryIndex` 副本并恢复后，条目 ID 集合和文件 SHA-256 与演练基线一致；耗时小于 1 秒。临时原始副本已销毁，生产源只读且演练前后哈希一致。
- 这证明“真实数据的隔离副本可恢复”，不证明故障中的生产切换已演练，也不替代 A/B 标签、Validator/Guardian 治理复核或维护窗口切换验收。

`ops/assess_memory_index_migration.py` 现读取并校验当前 daemon/CLI 源码哈希、调用方审计收据和最新的 2026-09-29 回滚收据；`08_GOVERNANCE/evidence/memory_kernel_migration_assessment_20260929.json` 是本次现状，旧的 2026-09-28 报告保留为历史记录。当前调用方统一和离线副本恢复均通过，量化 A/B 仍为 `REVIEW_REQUIRED`，生产切换仍为 `NOT_RUN`。本地收据均未认证为治理批准。

**`selected_by` 语义：**

> 审计记录的是调用方声明了谁，不代表系统认证了谁。

**`7cb943b` provenance / 推送边界：**

- 完整提交：`7cb943bb567512cde6d2b4b4f351bf64ed37dda0`；父提交：`4b6103ef0b0f0c1dafbf351d4c98c7663a8815a1`（`test(ace): check that every pointer the F-family queue cards cite still resolves`）。
- 分支：`core/daemon-lifecycle-resilience-20260912`；该提交只包含已记录的记忆治理代码、文档和测试，不包含当前工作树的其他在途改动。提交验收记录为 68 项相关测试通过、Kernel 自检 PASS、`py_compile` 与 `git diff --check` 通过。
- 推送范围白名单意图仅为 `7cb943b` 与其直接父提交 `4b6103e`。当前远端 `origin/core/daemon-lifecycle-resilience-20260912` 指向 `9fdd18d`，本地分支领先 8 个提交；现有分支普通推送会附带所选两提交之外的另外 6 个提交。因此本次不推送，也不把普通分支推送描述成满足白名单。若后续要严格遵守该范围，须从干净远端基线隔离并重放这两项变更（届时会产生新提交 SHA），核对补丁等价后才可推送；所有其他提交和在途工作树改动均排除在外。本记录不表示已推送。

## 目标

把 ACE 目前分散的记忆能力收敛成一条可恢复、可审计、可替换的主线：

```text
事实/观察/任务收据
        ↓
受治理收纳（source + evidence + data class）
        ↓
时间与范围索引 + 多路召回
        ↓
冲突 / UNKNOWN / 过期处理
        ↓
独立验证收据
        ↓
经验或能力候选
        ↓
闭环评估与痛苦复盘
        ↓
显式接纳 / 替代 / 归档
```

实现位于 `core/memory_kernel.py`。它是 ACE 的治理记忆层，不是新的聊天窗口记忆，
也不是模型调用器。

## 和现有系统的关系

| 现有能力 | Memory Kernel 的位置 |
| --- | --- |
| `core/memory_gateway.py` | 唯一活跃生产记忆入口；只暴露兼容读写 API，不开放候选迁移或 Kernel 查询 |
| `core/memory_index.py` | 唯一生产存储后端，由 Gateway 持有；`search_governed()` 仍是显式候选 API，不执行迁移 |
| `core/agent/memory_system.py` | 早期 Markdown 双层记忆骨架，保留考古和迁移用途，不再作为隐式生产真相 |
| `core/experience_deposition.py` | 经验文件沉积器；内核只接收其来源/证据投影，不绕过 Guardian 和闭环晋升 |
| `core/hindsight_memory_adapter.py` | 只读多策略召回器；内核对其加上范围、状态、分级和恢复边界 |
| `core/closed_loop_engine.py` | 能力晋升的唯一证据来源之一；`promote_capability()` 要求真实 baseline → change → test → evaluation → compare 和六项 painful review |
| `core/mirror_constitution.py` | 数据分级、凭证检测和出站边界；内核所有写入先过内部边界检查 |

## 当前运行决策：有界并置，不是已完成替换

| 组件 | 当前状态 | 权威/职责 |
| --- | --- | --- |
| `MemoryGateway → MemoryIndex` | `ACTIVE_PRODUCTION_PATH` | daemon 构造的唯一 Gateway 实例注入所有已 wiring 的记忆消费者；Backend 仍为 MemoryIndex。`daemon.memory_index` 仅是同一 Gateway 的兼容别名。 |
| `MemoryKernel` | `STAGED_TARGET` | 目标治理账本与候选迁移路径；目前没有 daemon/worker 生产消费者，不能称为当前生产真相源。 |
| `HindsightStyleRetriever` | `INTERNAL_RETRIEVAL_STRATEGY` | 只读排序策略，由 `MemoryKernel.query()` 复用；不是存储、写入权威或另一套记忆生命周期。 |
| `ACEBaseMemory` | `LEGACY_MIGRATION_ONLY` | 旧 Markdown 记忆骨架，只能作为显式迁移输入。 |

因此当前选择是**有界并置**：Gateway 统一生产入口，仍由旧索引承载读写；内核只作为隔离候选；不做双写、默认双读或自动回退。Hindsight 仅在候选内核内部使用。

**活跃生产调用方已统一。** `ace_daemon.py` 只构造一个 `MemoryGateway(MemoryIndex(...))`；默认实际接线的 8 个消费者为 `disk_scanner`、`observer`、`researcher`、`validator`、`archivist`、`guardian`、`local_archaeologist`、`task_creator`。存在来源资产时，`eco_parser` / `slice_clusterer` 以及显式启用时的 `web_scout` 也注入同一 Gateway。访问方法为兼容的 `add/search/get_by_concept/get_recent/get_stats/get_concept_graph`；没有独立 backend 选择或 Kernel 隐式回退。`ops/run_memory_gateway_caller_audit.py` 在隔离临时目录实际构造 daemon 并验证已接线对象身份；同时检查 daemon 的直接读写旁路、候选 Kernel 未接入和旧 CLI fail-closed。收据记录 8 个默认消费者、零 Provider 调用、零生产数据写入，并绑定 daemon/CLI 源码哈希。该收据是本机可复跑证据，不是独立治理批准。

| 调用方/历史路径 | 当前入口与结论 |
| --- | --- |
| `ace_daemon.py`、`core/task_roles.py`、扫描/解析/聚类/考古器及可选 WebScout | 唯一生产 Gateway；旧属性名 `memory_index` 仅为接口兼容，不代表另一个后端。 |
| `ace.py mem` | 在主入口处明确拒绝，拒绝发生于加载 legacy scheduler 之前；底层 `core.scheduler` 自身也会 fail-closed。历史 handler 不可达，不是生产消费者。 |
| `core/self_healing.py` | 只读检查 canonical runtime data dir 的 `memory_index.json`；检测损坏后标记不可自动修复，不重建空索引、不写记忆。 |
| `ops/status_summary.py` | 只读读取 `memory_index.json` 的总数用于运维状态展示，不做查询、写入或迁移；属于诊断旁路，不是第二生产检索入口。 |
| `core/base_worker.py`、`06_RUNTIME/workers/base_worker.py` | 仅为接收注入对象的 worker 基类；生产 daemon 未实例化独立旁路，已 wiring 实例由 Gateway 覆盖。 |
| `core/agent/memory_system.py` / `ACEBaseMemory` | 独立的旧 Markdown 类型，`LEGACY_MIGRATION_ONLY`；当前无 daemon 生产消费者，不是第二个活动 JSON 索引。 |

`MemoryIndex.search_governed()` 仍是候选查询 API，不属于 Gateway，也不负责迁移；只有显式调用 `MemoryKernel.import_records()` 才能迁移，每批硬上限 50 条。导入现保留来源时间和引用，并按稳定来源身份区分重复标题；没有来源事件 ID 时不会把同名旧记录错误合并。

### 批次审计收据

每次显式迁移必须提供 `selected_by`（调用方声明的责任标识；当前没有认证系统，故收据明确标记 `selection_identity_authenticated=false`）。Kernel 在同一哈希链记录批次开始和结束事件，含唯一 `batch_id`、时间、来源前缀、选中记录数与逐条内容哈希、批次哈希、导入/拒绝计数、拒绝原因、结果和事件哈希。可用 `MemoryKernel.list_import_batches()` 回读状态；只有开始事件而无结束事件的批次会显示 `INCOMPLETE`。超出 50 条会写入零写入拒绝事件，再抛出带批次 ID 的错误。收据不复制原始记忆文本。

当前默认旧检索行为没有被静默替换。真实索引截至最新演练快照为 6,985 条、全部 `PRIVATE`，来源字段并不完整；全量导入不合适。并置有清楚边界和退场条件，不代表两套都成为默认。

## 收敛规则

这套内核是记忆治理的唯一新增主线。后续不再增加平行索引、第二套事件账本、独立
记忆守护进程或绕过闭环的晋升通道。Hindsight 只能作为内核下的检索适配器；旧
Markdown/旧索引只能通过 candidate-only 迁移进入。任何新增字段都必须同时具备真实
消费者、回归测试和替代/退役路径，否则不进入生产层。

当前运行时的旧 `memory_index.json` 约有 6.9k 条记录，来源路径覆盖率约 4%，且全部
标为 `PRIVATE`，主要是周期摘要和任务归档。因此已经记录为
`STAGED_MIGRATION_REQUIRED`，不会把这些摘要批量伪装成事实导入；后续只迁移有来源、
有用途、可验证的切片。评估脚本是 `ops/assess_memory_index_migration.py`，收据位于
`08_GOVERNANCE/evidence/memory_kernel_migration_assessment_20260929.json`。

### 允许替换默认路径的条件

阈值在执行真实 A/B 前预注册于 `ops/assess_memory_index_migration.py` 的 `REPLACEMENT_THRESHOLDS`；评估收据缺字段保持 `REVIEW_REQUIRED`，仅指标过线返回 `METRICS_PASS_REVIEW_REQUIRED`，不等于治理晋升。阈值为：至少 300 条真实本地脱敏标注查询，六类（general/temporal/conflict/provenance/privacy/unknown）各不少于 50 条；Recall@5 ≥ 0.90，Recall@5/MRR@10/Precision@5 相对旧路径回退均不超过 0.02；冲突保留率与 UNKNOWN 拒答准确率均为 100%；P99 ≤ min(250ms, 旧路径 P99 × 1.25)；越权泄漏为 0，边界测试全过；至少 100 个并发读、10 个并发写、3 个故障注入点均完成恢复演练。

真实数据回滚门要求在本机的**真实 PRIVATE 索引副本**上执行，不能上传；回滚前后快照 SHA-256 必须相同、已确认写入丢失数为 0、回滚耗时 ≤ 5 分钟。该离线副本演练已经完成并有收据；生产维护窗口的切换/回绑演练仍未运行，收据也尚未进入既有 Validator/Guardian 复核，因此不能据此宣称生产切换门全过。

只有以下切换清单全部打勾，才可把 Kernel 变为唯一生产后端：

1. 所有上表调用者完成归属审计；建立唯一兼容门面并将 daemon、CLI、worker、扫描器、研究/经验写入和恢复路径全迁入；静态检查不再发现生产调用方绕过门面。
2. 完成本节量化 A/B、隐私、并发、故障恢复和真实本地数据回滚门；所有收据完整且审核通过。
3. 切换前停写/排空队列，生成并校验旧索引快照哈希；在一次维护窗口只切换 daemon bootstrap 的后端绑定（当前没有后端配置开关，届时不得分散新增多个 feature flags）。
4. 启动后运行读写、权限、哈希链、事件恢复及召回冒烟；任一失败立即将唯一绑定切回旧索引，确认哈希与数据完整后结束维护窗口。
5. 不启用长期双写/双读；迁移期间旧索引快照保留为唯一回滚源，稳定验收后再按保留策略归档。

未满足时保持上述有界并置；不再新增第三套索引或另建迁移协议。

## 记忆类型和状态

### 类型（memory_type）

- `WORKING`：临时工作上下文，可以没有来源，但绝不能自动晋升。
- `EPISODIC`：一次任务、一次视频镜头、一次故障的经历。
- `SEMANTIC`：经过验证的可复用事实或概念。
- `PROCEDURAL`：可执行流程候选，必须经过验证才能成为规则。
- `OBSERVATION`：对现实的观察，默认是 `CANDIDATE` 或 `UNKNOWN`。
- `EXPERIENCE`：从任务结果沉淀的经验，不等于能力。
- `CAPABILITY_CANDIDATE`：待闭环验证的能力候选。
- `CAPABILITY_ACCEPTED`：已通过 ACE 晋升门的能力；不能由模型自报成功产生。
- `UNKNOWN`：证据不足或无法观测的内容。

### 认识状态（epistemic_status）

`UNKNOWN → CANDIDATE → VERIFIED` 是正常路径。存在相反证据时进入
`CONFLICTED`，被新版本取代时进入 `SUPERSEDED`，过期或不再进入召回时进入
`ARCHIVED`。任何状态都保留事件历史，禁止物理删除。

## 证据与边界

每条非 `WORKING` 记忆必须有 `source_refs`。有证据但未经独立核验的内容只能是
`CANDIDATE`；没有证据的内容明确是 `UNKNOWN`。`verify()` 需要可回读的收据：

```json
{
  "receipt_id": "probe://receipt/001",
  "source_refs": ["probe://run/001", "logs://run/001"],
  "result": "PASS",
  "reviewer": "guardian"
}
```

`CAPABILITY_CANDIDATE` 只有在闭环实验收据包含 baseline、change、test、evaluation、
compare、至少两组相互独立的证据和六项 painful review 时，才允许
`promote_capability()`。这条门不接受
“模型说已经学会了”、单次成功或文字完整性作为证据。

所有记录都带 `data_class`。内核拒绝未知分级和明显凭证内容；`PRIVATE` / `CORE`
只留在内部。查询返回的是只读投影，恒定带有：

```text
execution_authorized = false
production_integration = false
promotion = false
```

## 记忆结构和恢复

`events.jsonl` 是追加式事件账本，每个事件带：

- `previous_event_hash`
- `event_hash`
- `event_id`
- `event_type`
- `payload`

`snapshot.json` 只是物化加速视图。启动时会从 JSONL 重放并校验哈希链；链损坏时
`MemoryIntegrityError` fail-closed，而不是拿残缺状态继续工作。窗口重启、进程替换或
模型更换不改变记忆身份，因为身份基于逻辑 bank、claim key 和内容哈希，不绑定盘符、
进程、Provider 或机器。

## 召回

`query()` 采用现有 Hindsight 风格适配器的多策略只读召回：关键词、概念图、语义
代理、时间和 RRF 融合；内核额外先按 bank、scope、data class、状态、创建时间和
`as_of` 有效时间窗过滤。
查询默认不写回访问次数，不因为被召回就改变状态或进入生产。

## 冲突、遗忘和替代

- 同一 `claim_key` 出现相反 polarity 时，双方都标记为 `CONFLICTED`，交给下一次有界验证。
- `supersede()` 只增加替代事件，旧记录保持可追溯。
- `archive()` 只改变可见生命周期，永不删除原始事件和证据。
- `apply_retention()` 可以把过期记录降为 `COLD`，人工/治理动作再决定是否 `ARCHIVED`，但不能把历史擦掉。

## 最小用法

```python
from pathlib import Path
from core.memory_kernel import MemoryKernel

kernel = MemoryKernel(Path("02_MEMORY/kernel"), bank="ace")
candidate = kernel.capture(
    content="对白镜头必须保留说前、说中、说后动作",
    memory_type="EXPERIENCE",
    claim_key="video.performance.before_during_after",
    data_class="CAPABILITY",
    source_refs=["receipt://shot/001"],
    evidence_refs=["receipt://qc/001"],
)

result = kernel.query("对白 动作", scope="video")
state = kernel.project_current_state(scope="video")
```

## 当前验收

```text
py -3 -B -m pytest -q ops/test_memory_kernel.py \
  ops/test_hindsight_memory_adapter.py \
  ops/test_data_boundary_enforcement.py \
  ops/test_mirror_constitution.py \
  ops/test_experience_deposition.py \
  ops/test_closed_loop_engine.py
```

当前门内结果：`61 passed`。完整仓库回归仍需在不与其他后台任务争用写锁的窗口执行；
这不影响本轮内核 focused regression 的结论。

## 不做的事

1. 不把 Hindsight、某个模型或某个窗口设为永久居民。
2. 不因为“召回到了”就直接修改生产合同、路由或人格。
3. 不在内核里偷偷调用外网、模型或 Provider。
4. 不删除旧记忆；迁移采用 candidate-only 和 supersede。
5. 不把“有温度”伪装成已证实主观意识；温度体现为理解人的处境、尊严、信任和边界。
