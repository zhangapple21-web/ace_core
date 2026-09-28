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
| `core/memory_index.py` | 现有结构化索引；通过 `search_governed()` 显式迁移到内核，不改变旧 `search()` |
| `core/agent/memory_system.py` | 早期 Markdown 双层记忆骨架，保留考古和迁移用途，不再作为隐式生产真相 |
| `core/experience_deposition.py` | 经验文件沉积器；内核只接收其来源/证据投影，不绕过 Guardian 和闭环晋升 |
| `core/hindsight_memory_adapter.py` | 只读多策略召回器；内核对其加上范围、状态、分级和恢复边界 |
| `core/closed_loop_engine.py` | 能力晋升的唯一证据来源之一；`promote_capability()` 要求真实 baseline → change → test → evaluation → compare 和六项 painful review |
| `core/mirror_constitution.py` | 数据分级、凭证检测和出站边界；内核所有写入先过内部边界检查 |

内核不是把旧系统全部重写一遍，而是提供唯一的渐进收口点。默认的旧检索行为没有被
静默替换；只有显式调用 `MemoryIndex.search_governed()` 或 `MemoryKernel.query()` 才会
走新链路。这是有意的升级门，避免一次迁移把未知问题传播到生产。

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
