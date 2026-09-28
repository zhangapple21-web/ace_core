# ACE Memory Kernel v1

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
| `core/memory_index.py` | 当前生产运行时索引；`search_governed()` 只读已存在的内核，不执行迁移 |
| `core/agent/memory_system.py` | 早期 Markdown 双层记忆骨架，保留考古和迁移用途，不再作为隐式生产真相 |
| `core/experience_deposition.py` | 经验文件沉积器；内核只接收其来源/证据投影，不绕过 Guardian 和闭环晋升 |
| `core/hindsight_memory_adapter.py` | 只读多策略召回器；内核对其加上范围、状态、分级和恢复边界 |
| `core/closed_loop_engine.py` | 能力晋升的唯一证据来源之一；`promote_capability()` 要求真实 baseline → change → test → evaluation → compare 和六项 painful review |
| `core/mirror_constitution.py` | 数据分级、凭证检测和出站边界；内核所有写入先过内部边界检查 |

## 当前运行决策：有界并置，不是已完成替换

| 组件 | 当前状态 | 权威/职责 |
| --- | --- | --- |
| `MemoryIndex` | `ACTIVE_LEGACY_RUNTIME` | daemon 与 worker 当前实际读写的运行时索引；仍是现行默认路径，直到切换门通过。 |
| `MemoryKernel` | `STAGED_TARGET` | 目标治理账本与候选迁移路径；目前没有 daemon/worker 生产消费者，不能称为当前生产真相源。 |
| `HindsightStyleRetriever` | `INTERNAL_RETRIEVAL_STRATEGY` | 只读排序策略，由 `MemoryKernel.query()` 复用；不是存储、写入权威或另一套记忆生命周期。 |
| `ACEBaseMemory` | `LEGACY_MIGRATION_ONLY` | 旧 Markdown 记忆骨架，只能作为显式迁移输入。 |

因此当前选择是**有限期并置**：旧索引继续承载现有运行时读写；内核只作为已测但未准入的替代候选；不做双写、默认双读或自动回退。Hindsight 算法只在候选内核的查询实现中复用；它不再有直接挂到旧 `MemoryIndex` 的独立查询入口。

**调用方统一尚未完成。** 目前 daemon 把同一个 `MemoryIndex` 实例注入部分读写模块，但调用者仍直接调用旧 `.search()` / `.add()`；`search_governed()` 是查询候选 Kernel 的试验入口，不是生产统一门面，也不应在 Kernel 获批前被当成生产默认。当前调用清单：

| 调用方 | 当前入口/状态 | Kernel 替换前必须完成 |
| --- | --- | --- |
| `ace_daemon.py` | 构造 `MemoryIndex` 并自身直接 `.search()` / `.add()`；将实例注入多个 runtime 组件，确认为主 runtime owner。 | 创建唯一兼容门面；daemon 自身及所有注入消费者改为依赖门面接口。 |
| `core/task_roles.py` | 由 daemon 注入同一实例；直接 `.search()` / `.add()` / `.get_stats()`。 | 所有角色查询、写入及统计走同一门面。 |
| `core/disk_scanner.py`、`core/eco_parser.py`、`core/slice_clusterer.py` | daemon 注入；扫描、解析及聚类路径直接写 `.add()`。 | 写入改经门面；扫描恢复仍使用已批准的后端恢复接口。 |
| `core/local_archaeologist.py` | daemon 注入；直接 `.search()`。 | 检索改经门面，保留来源及数据分级过滤。 |
| `core/web_scout.py` | 源码中有注入及 `.add()`；daemon 注释显示旧 WebScout 路径不作为当前受治理挖矿入口，实际运行触发状态需单独确认。 | 若仍可执行则纳入门面，否则明确退役；不得保留隐藏写旁路。 |
| `ace.py` | 操作者 CLI 经 scheduler 的 `memory_index` 直接 `.add()` / `.search()`。 | CLI 改用同一门面；迁移诊断工具只能走显式候选 API。 |
| `core/self_healing.py` | 直接读写 `memory_index.json`，损坏时先备份再重建空索引；绕过 `MemoryIndex` API。 | 迁移前改用后端恢复接口，并证明恢复不会静默丢弃已提交记忆。 |
| `core/base_worker.py`、`06_RUNTIME/workers/base_worker.py`、`core/agent/memory_system.py` | 源码仍有直接访问或独立构造；当前生产 wiring 未证明，且存在重复/历史实现。 | 逐一证明仍在用并纳入门面，或经测试确认已退役；UNKNOWN 按阻塞处理。 |

以上调用目前没有统一切到 Kernel，也没有已落地的 `MemoryGateway`/兼容 facade；因此当前准确状态是“一个旧后端被多处直接调用 + 一个隔离候选”，不是“调用方已统一”。`MemoryIndex.search_governed()` 只查询已存在的 Kernel，不负责迁移；迁移必须由调用者明确选择记录后调用 `MemoryKernel.import_records()`，每批硬上限为 50 条。

### 批次审计收据

每次显式迁移必须提供 `selected_by`（调用方声明的责任标识；当前没有认证系统，故收据明确标记 `selection_identity_authenticated=false`）。Kernel 在同一哈希链记录批次开始和结束事件，含唯一 `batch_id`、时间、来源前缀、选中记录数与逐条内容哈希、批次哈希、导入/拒绝计数、拒绝原因、结果和事件哈希。可用 `MemoryKernel.list_import_batches()` 回读状态；只有开始事件而无结束事件的批次会显示 `INCOMPLETE`。超出 50 条会写入零写入拒绝事件，再抛出带批次 ID 的错误。收据不复制原始记忆文本。

当前默认旧检索行为没有被静默替换。这是因为真实索引有 6,922 条记录、来源覆盖率约 4.2%、全部为 `PRIVATE`；全量导入不合适，内核也尚未接管所有生产读写调用。并置有清楚边界和退场条件，不代表两套都成为默认。

## 收敛规则

这套内核是记忆治理的唯一新增主线。后续不再增加平行索引、第二套事件账本、独立
记忆守护进程或绕过闭环的晋升通道。Hindsight 只能作为内核下的检索适配器；旧
Markdown/旧索引只能通过 candidate-only 迁移进入。任何新增字段都必须同时具备真实
消费者、回归测试和替代/退役路径，否则不进入生产层。

当前运行时的旧 `memory_index.json` 约有 6.9k 条记录，来源路径覆盖率约 4%，且全部
标为 `PRIVATE`，主要是周期摘要和任务归档。因此已经记录为
`STAGED_MIGRATION_REQUIRED`，不会把这些摘要批量伪装成事实导入；后续只迁移有来源、
有用途、可验证的切片。评估脚本是 `ops/assess_memory_index_migration.py`，收据位于
`08_GOVERNANCE/evidence/memory_kernel_migration_assessment_20260928.json`。

### 允许替换默认路径的条件

阈值在执行真实 A/B 前预注册于 `ops/assess_memory_index_migration.py` 的 `REPLACEMENT_THRESHOLDS`；评估收据缺字段保持 `REVIEW_REQUIRED`，仅指标过线返回 `METRICS_PASS_REVIEW_REQUIRED`，不等于治理晋升。阈值为：至少 300 条真实本地脱敏标注查询，六类（general/temporal/conflict/provenance/privacy/unknown）各不少于 50 条；Recall@5 ≥ 0.90，Recall@5/MRR@10/Precision@5 相对旧路径回退均不超过 0.02；冲突保留率与 UNKNOWN 拒答准确率均为 100%；P99 ≤ min(250ms, 旧路径 P99 × 1.25)；越权泄漏为 0，边界测试全过；至少 100 个并发读、10 个并发写、3 个故障注入点均完成恢复演练。

真实数据回滚门要求在本机的**真实 PRIVATE 索引副本**上执行，不能上传；回滚前后快照 SHA-256 必须相同、已确认写入丢失数为 0、回滚耗时 ≤ 5 分钟。合成数据回滚、材料声明或单独的脚本 PASS 都不算通过；收据须可回读并由既有 Validator/Guardian 复核。

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
