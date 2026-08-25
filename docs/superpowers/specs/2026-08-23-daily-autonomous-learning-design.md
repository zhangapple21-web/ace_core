# ACE 每日自主学习闭环设计

## 目标

在没有更高优先级内部工作时，ACE 每个自然日至少完成一轮有治理的自主学习，或者持久化 `NO_VALID_LEARNING_TARGET` 并记录没有值得学习目标的可核验原因。

该能力复用既有 Discovery、Observation、TaskPool、任务角色、EvidenceRegistry、TripleCrossValidation、KnowledgeGovernor、KnowledgeLifecycle、ExperienceDeposition 与 Archivist；不创建第二套任务、路由、治理或归档系统。

## 范围和安全边界

本轮只增加一个窄的学习编排层和它所需的现有接口扩展。

- 不调用真实荐股、实时行情、Telegram、自动荐股、自动推送或客户发布入口。
- 外部学习结果只形成受治理的知识资产、观察或拒绝记录；不直接修改 Runtime、荐股策略、数据源配置或自动执行权限。
- 不因为每日要求而创建没有明确证据和学习价值的任务。
- 外部来源发现不内置固定站点清单。它只接收学习目标和来源层级，具体来源由可替换的发现器选择。
- 默认离线运行；只有调用方显式注入外部发现器和检索器时才会检索外部资料。

## 复用组件和职责

| 既有组件 | 学习闭环中的职责 |
| --- | --- |
| `DiscoveryMode` / `DiscoveryCandidate` | 承载候选、Observation 记录和候选指纹去重 |
| `ObservationToTaskConverter` | 将完整学习候选转换为现有 `TaskPool` 任务 |
| `TaskPool` / `Task` | 保存学习合同、来源发现、证据、治理结果及归档状态 |
| `Researcher` | 复用本地记忆、词库、经验、考古材料的内部研究能力 |
| `EvidenceRegistry` | 追加式登记每条内部或外部证据及完整来源元数据 |
| `TripleCrossValidation` | 复用三类证据交叉验证输出，并保留其分类限制 |
| `KnowledgeGovernor` | 对知识候选给出 `PASS`、`REJECT`、`MERGE`、`REVISE`、`DELAY` 等准入结论 |
| `KnowledgeLifecycle` | 记录 Observation 到 Archived/Graveyard 的阶段转移 |
| `Guardian` / `Archivist` / `ExperienceDeposition` | 仅在受治理结论后复用现有分类、归档和经验沉淀能力 |

## 学习合同

学习候选在原有 `DiscoveryCandidate` 字段之外，通过 `metadata["learning"]` 携带以下必填字段：

```json
{
  "why_learn": "为什么当前缺口值得学习",
  "learning_objective": "要验证或掌握的具体命题",
  "required_evidence": ["所需证据种类和最低门槛"],
  "mastery_criteria": ["可以判定已掌握的可验证标准"]
}
```

候选转换前必须校验四项均为非空。缺项的 Learning Observation 可以被记录为观察，但不得创建学习任务或进入来源发现。

学习任务使用既有 `Task.outputs["discovery"]` 保存原始 Discovery 元数据，并在 `Task.outputs["learning"]` 保存合同、来源发现、独立性分析、交叉验证、治理决定、最终结果和无副作用声明。

## 每日编排

每日入口使用显式 `run_date` 和隔离的数据根目录执行，并先查找该日是否已有学习终局记录。终局包括 `adopt`、`observe`、`reject` 和 `NO_VALID_LEARNING_TARGET`；已有终局则幂等返回。

```text
检查当天终局记录
  -> 发现内部候选
  -> 有高价值、证据支持的内部候选？
       -> 创建完整学习合同
       -> Discovery Observation
       -> ObservationToTaskConverter
       -> 内部证据研究
  -> 否则创建外部学习合同
       -> 按来源层级请求来源发现器
       -> 登记可直接核验的来源内容
  -> EvidenceRegistry
  -> 来源独立性判定
  -> TripleCrossValidation
  -> KnowledgeGovernor
  -> adopt / observe / reject
  -> KnowledgeLifecycle + Archivist + ExperienceDeposition
```

内部候选依次来自已有可用证据：失败经验、Runtime 缺口、测试缺口、仓库差距、数据源异常、荐股系统状态、词库缺口、R1/ACE 考古。候选必须说明事实来源、风险或价值、缺失知识和可验证完成标准。无事实支撑的“可能值得研究”不能成为内部学习任务。

仅当内部候选不存在或均低于阈值时，才允许外部学习。外部来源层级为：官方/一手、技术原始资料、GitHub/论文/文档、社区实践、开放网络。层级只约束发现优先级，不硬编码网址。

当内部无高价值候选、外部无可用学习目标或所有来源均未达到证据门槛时，写入当日唯一 `NO_VALID_LEARNING_TARGET`，包括内部评估摘要、外部发现摘要和拒绝原因。

## 证据与来源独立性

每条证据都通过 `EvidenceRegistry.register()` 登记，并在 metadata 保存：

```json
{
  "source_tier": "official|technical_primary|documentation|community|open_web|internal",
  "publisher": "发布者或本地资产所有者",
  "upstream_identity": "最终一手来源或本地事实域",
  "directness": "primary|derived|repost|search_result",
  "retrieval_method": "internal_scan|fixture|external_discovery",
  "independence_group": "按上游归一化的独立来源组"
}
```

独立来源计数按 `independence_group` 去重，而不是按 URL、适配器、搜索结果或登记条目计数。

- 同一上游的多个包装器只算一个独立组。
- 转载、镜像、摘要和搜索结果不能作为独立交叉验证证据。
- 搜索结果只能引导来源发现，只有可读取、可登记且具有内容哈希的原文或本地事实才可成为证据。
- 内部运行事实可以作为内部独立事实域，但不能被伪装为外部独立来源。

来源独立性结果会和 `TripleCrossValidation` 结果同时保存。后者仍使用其既有 `local/tg/external` 三分类，故它不能单独证明发布者或上游独立性。

## 治理和结果映射

学习资产必须先通过独立性门和交叉验证，再调用 `KnowledgeGovernor.evaluate()`。治理结论是知识是否采纳的唯一依据：

| Governor 结论 | 学习结果 | 生命周期 | 后续处理 |
| --- | --- | --- | --- |
| `PASS` | `adopt` | Published -> Archived | 调用 Guardian、ExperienceDeposition、Archivist |
| `DELAY` / `REVISE` / `MERGE` / `SPLIT` / `SUPERSEDE` | `observe` | Validation 或 Repository Candidate -> Archived | 保存待补证据、重复或修订原因并归档 |
| `REJECT` | `reject` | Graveyard -> Archived | 保存拒绝原因和证据边界并归档 |

`Validator` 的 `approved` 和 `Guardian` 的 `axiom`/`constraint` 不是知识采纳依据。学习编排层会将其作为任务工作流产物记录，并额外记录以下架构差异：现有 `Validator` 可以在三次复审后强制通过，而既有 `Guardian` 依据任务证据量分类；二者均未检查来源层级、上游独立性、完整交叉验证或 `KnowledgeGovernor` 准入。本轮不改变它们的通用实现。

## 隔离验证

测试必须完全在临时目录内运行，注入假的内部候选源、外部发现器和来源内容，不访问网络，并断言不调用市场、荐股、Telegram、自动执行模块。

连续四个逻辑自然日：

1. Day 1：存在有本地失败事实支持的内部候选；创建完整合同，登记证据，完成验证和治理，形成一个新 `adopt` 学习资产。
2. Day 2：无内部高价值候选；外部发现器按层级返回可核验来源，形成外部学习任务和受治理结果。
3. Day 3：候选与已采纳知识高度重复；`KnowledgeGovernor` 阻止再次采纳，结果为 `observe` 或 `reject`。
4. Day 4：外部材料只有转载、搜索摘要或同一上游包装器；独立性/证据门失败，结果只能为 `observe` 或 `reject`，不得 `adopt`。

另有无目标测试：内部无候选且外部没有达到门槛的目标时，当天恰好记录一条 `NO_VALID_LEARNING_TARGET`，再次运行保持幂等。

## 文件边界

预计修改：

- `core/discovery.py`：允许候选携带受校验的学习 metadata，并暴露内部候选源适配点。
- `core/observation_to_task.py`：拒绝合同不完整的学习 Observation，同时保留 metadata 到现有任务输出。
- 新增一个专责学习编排模块，实例化并协调既有组件，不实现新的任务池、证据库或治理器。
- `ops/test_daily_autonomous_learning.py`：完整的隔离多日模拟和副作用禁区断言。

除上述窄接线外，不修改荐股策略、实时数据源、自动运行配置、Telegram 逻辑或通用 Validator/Guardian 语义。
