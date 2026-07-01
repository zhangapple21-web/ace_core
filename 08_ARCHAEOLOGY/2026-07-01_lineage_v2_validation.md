# Lineage v2 提案验证对比报告

**日期**: 2026-07-01
**提案来源**: GPT（Survival Lineage / Lineage v2）
**验证方法**: 横切扫描 ACE 现有体系（抽屉翻查）+ 对比判断
**结论**: 5 个观点中 3 个正确、1 个部分正确、1 个 ACE 已有更完整实现

---

## 验证清单

| GPT 观点 | ACE 现有实现 | 对不对 | 怎么做 |
|---------|------------|--------|--------|
| ① Lineage 是 Paper Lineage，应升级为 Capability Lineage | 有 Lexicon（概念层），但 Lineage 节点确实是"报告级"的 | ✅ 部分对 | 增强但不推翻，增加 capability 字段做映射 |
| ② 同义节点问题，需要 Canonicalizer | ConceptHealthMonitor 已有同义检测 + EntropyMonitor 已有重复检测 | ⚠️ ACE 已经有 | 不新建 Canonicalizer，复用现有模块 |
| ③ 孤立节点不是坏事，应有三状态 | Lineage 已有 status 字段 + ConceptHealth 已有 orphan 检测 | ✅ 对 | 扩展状态机，对齐已有体系 |
| ④ Gap 检测太浅，应检测 Pattern/Principle 层 | 目前只有 type_jump 规则 | ✅ 对 | 增加演化阶段检测规则 |
| ⑤ 应增加 survival_reason / fitness | ConceptHealthMonitor + ExperienceHealthMonitor 已有完整健康度体系 | ⚠️ ACE 更完整 | 不是新增字段，而是打通已有健康度数据 |

---

## 详细验证

### ① Paper Lineage → Capability Lineage

**GPT 说的**：现在 Lineage 挂的是 Report，应该挂 Capability。Report 只是证据，Capability 才是文明。

**ACE 现状**：
- Lineage 节点确实是从考古报告里提取的"报告级"概念（如 "Sekiro RPC Protocol"）
- ACE 有 Lexicon（词库概念体系）、有 Protocol/Constraint/Experience 等资产分类
- 但 Lineage 没有和 Lexicon 打通——两套体系各玩各的

**判断**：✅ **方向对，但不应该推翻重来**

- 不是"把 Report 节点换成 Capability 节点"
- 而是"Report 节点保留（作为证据），增加 Capability 节点（作为文明主体），两者用 evidence 边连接"
- 这和 P4（Non-invasive）一致——不修改旧数据，只做 Overlay 增强

**证据来源**：
- 抽屉：[lexicon.py](file:///C:/Users/USER/Downloads/Telegram%20Desktop/ace_runtime/core/lexicon.py) — 已有 7 大类概念体系
- 抽屉：[lineage.py](file:///C:/Users/USER/Downloads/Telegram%20Desktop/ace_runtime/core/lineage.py) — 节点类型已有 concept/constraint/protocol/blueprint/experience/code 六类
- 结论：ACE 有 Capability 的分层，只是 Lineage 没有用正确的粒度去索引

---

### ② 同义节点 / Canonicalizer

**GPT 说的**：25 个节点里有很多同义节点，需要 Canonicalizer 做归一化。

**ACE 现状**：
- [ConceptHealthMonitor](file:///C:/Users/USER/Downloads/Telegram%20Desktop/ace_runtime/core/governance/concept_health.py) 已经检测 5 种问题：重复命名、不同名同义、同名不同义、孤立概念、缺少父子节点
- [EntropyMonitor](file:///C:/Users/USER/Downloads/Telegram%20Desktop/ace_runtime/core/governance/entropy_monitor.py) 已有文件重复、概念重复、协议重复、经验重复、语义重复 5 种检测
- [SimilarityEngine](file:///C:/Users/USER/Downloads/Telegram%20Desktop/ace_runtime/core/similarity_engine.py) 已有 n-gram Jaccard 相似度算法

**判断**：⚠️ **ACE 已经有更完整的实现**

- GPT 说的 Canonicalizer，ACE 已经分散在 ConceptHealthMonitor + EntropyMonitor + SimilarityEngine 三个模块里
- 不是"没有"，是"分散在不同地方，Lineage 没有调用它们"
- 正确做法：不是新建 Canonicalizer，而是让 LineageSystem 在注册节点时调用现有检测能力

**证据来源**：
- 抽屉：concept_health.py 第 30-35 行 — 明确列出 synonym_different_names（不同名同义）检测
- 抽屉：entropy_monitor.py 第 95-175 行 — 5 种重复检测方法
- 抽屉：similarity_engine.py — 已有相似度算法

---

### ③ 孤立节点 / 三状态

**GPT 说的**：孤立节点不是坏事，是"还没进入文明，在观察期"。应该有 Candidate → Observation → Accepted 三状态。

**ACE 现状**：
- LineageNode 已有 `status` 字段（active/deprecated/frozen/archived），但缺 "候选/观察" 状态
- ConceptHealthMonitor 已有 orphan_concepts 检测
- KnowledgeEvolutionTracker 已有 12 种演化事件类型（CREATED/PROMOTED/DEMOTED/FROZEN/ARCHIVED/DEPRECATED 等）

**判断**：✅ **完全正确**

- 状态机思路完全正确
- 但 ACE 已有更丰富的状态体系，需要对齐而不是新建
- 正确做法：扩展 status 为 Candidate → Observation → Accepted → Deprecated → Extinct，对齐 KnowledgeEvolutionTracker 的演化事件

**证据来源**：
- 抽屉：lineage.py 第 53 行 — 已有 status 字段
- 抽屉：knowledge_evolution.py 第 38-51 行 — 12 种演化类型
- 抽屉：concept_health.py — orphan 检测

---

### ④ Gap 检测太浅

**GPT 说的**：现在只检测 type_jump（类型跳跃），太浅。应该检测完整的演化阶段：Experience → Pattern → Principle → Protocol → Blueprint → Capability。

**ACE 现状**：
- 目前只有 2 条 Gap 规则：低置信度边、类型跳跃
- 类型跳跃用的是 axiom→concept→constraint→protocol→blueprint→experience→code 的顺序
- 这个顺序是我随手写的，确实有问题（experience 不应该在 blueprint 之后）

**判断**：✅ **完全正确**

- Gap 检测确实太浅
- 但 GPT 提出的演化阶段（Experience→Pattern→Principle→Protocol→Blueprint→Capability）和 ACE 现有分类不完全一致
- 正确做法：修正演化阶段顺序，增加 Pattern/Principle 中间层的检测规则

**ACE 正确的演化顺序应该是**：
```
Experience（经验）
  → Pattern（模式）
    → Principle（原则/约束）
      → Protocol（协议）
        → Blueprint（蓝图）
          → Implementation（实现/代码）
```

**证据来源**：
- 抽屉：lineage.py 第 553-561 行 — 当前 type_evolution_order 有问题
- 抽屉：三系统对比报告里的架构分析 — 验证了从经验到实现的演化路径

---

### ⑤ Survival Reason / Fitness

**GPT 说的**：Lineage 不应该只回答"从哪里来"，而应该回答"为什么活下来"。增加 survival_reason 和 fitness_score。

**ACE 现状**：
- [ConceptHealthMonitor](file:///C:/Users/USER/Downloads/Telegram%20Desktop/ace_runtime/core/governance/concept_health.py) — 概念健康度检测
- [ExperienceHealthMonitor](file:///C:/Users/USER/Downloads/Telegram%20Desktop/ace_runtime/core/governance/experience_health.py) — 经验健康度检测
- [EntropyMonitor](file:///C:/Users/USER/Downloads/Telegram%20Desktop/ace_runtime/core/governance/entropy_monitor.py) — 熵值计算（重复+冲突+孤立）
- [CivilizationStatus](file:///C:/Users/USER/Downloads/Telegram%20Desktop/ace_runtime/core/governance/civilization_status.py) — 文明状态整体评估

**判断**：⚠️ **ACE 已经有更完整的体系**

- GPT 说的 fitness，ACE 已经有 ConceptHealth + ExperienceHealth + EntropyMonitor 三套系统在做
- GPT 说的 survival_reason，ACE 的 Experience/Concept 里有使用频率、引用次数等数据
- 问题不是"没有 fitness"，而是"Lineage 没有接入这些健康度数据"
- 正确做法：不是新增 survival_reason/fitness 字段，而是让 Lineage 能查询已有健康度系统的数据

**证据来源**：
- 抽屉：concept_health.py — 6 种健康检查
- 抽屉：experience_health.py — 6 种健康检查
- 抽屉：entropy_monitor.py — 熵值计算和趋势追踪
- 抽屉：civilization_status.py — 文明状态整体评估

---

## 合并计划

### 应该做的（增量增强，不新建模块）

**P0 — 修正 Gap 检测的演化顺序**
- 把 type_evolution_order 修正为正确的演化路径
- 增加 Pattern/Principle 中间层概念
- 成本：极小，改几行代码

**P0 — 扩展 Lineage 状态机**
- status 从 4 种扩展为 6 种：Candidate → Observation → Accepted → Frozen → Deprecated → Extinct
- 对齐 KnowledgeEvolutionTracker 的演化事件
- 成本：小，增加字段和状态转换规则

**P1 — Lineage 节点分级（Report vs Capability）**
- 增加 node_tier 字段：evidence（报告级）/ capability（能力级）
- Report 节点保留为 evidence，增加 Capability 节点作为文明主体
- 用 evidence_of 边连接
- 成本：中，需要重新梳理概念

**P1 — 接入现有健康度数据**
- Lineage 查询时调用 ConceptHealthMonitor/ExperienceHealthMonitor
- 不新增 fitness 字段，而是实时查询已有系统
- 成本：中，打通数据通路

### 不该做的（避免重复建设）

❌ 不新建 Canonicalizer — ACE 已有 ConceptHealth + EntropyMonitor + SimilarityEngine
❌ 不新增 survival_reason 字段 — 健康度数据已有系统在管，Lineage 只做查询
❌ 不推翻现有节点 — 全部用 Overlay 增量增强
❌ 不重做数据结构 — 现有结构够用

### 以后再说的（数据不够，做了也白做）

⏳ Capability 节点的大规模梳理 — 等 Lineage 有 100+ 节点再做
⏳ 完整的 Canonicalization 流程 — 等同义节点真的多到爆炸再做
⏳ Survival Reason 的自动抽取 — 需要 LLM，当前 moratorium 不引入

---

## 认知熵检查

```yaml
entropy_check:
  new_active_concepts: 0       # 没有引入新概念
  existing_concepts_enhanced: 4  # LineageSystem(状态机+Gap规则)、ConceptHealth(打通)、EntropyMonitor(打通)、KnowledgeEvolution(对齐)
  concept_density_delta: "+0.00"  # 无新概念膨胀
  new_files_created: 0         # 全部写入已有文件
  judgment: "越学越稳。GPT 的5个观点验证下来：3对+1部分对+1ACE已有更完整实现。都是增量增强，没有架构侵入。"
```

---

## 相关文件

- 谱系系统：[lineage.py](file:///C:/Users/USER/Downloads/Telegram%20Desktop/ace_runtime/core/lineage.py)
- 概念健康度：[concept_health.py](file:///C:/Users/USER/Downloads/Telegram%20Desktop/ace_runtime/core/governance/concept_health.py)
- 经验健康度：[experience_health.py](file:///C:/Users/USER/Downloads/Telegram%20Desktop/ace_runtime/core/governance/experience_health.py)
- 熵监控：[entropy_monitor.py](file:///C:/Users/USER/Downloads/Telegram%20Desktop/ace_runtime/core/governance/entropy_monitor.py)
- 知识演化：[knowledge_evolution.py](file:///C:/Users/USER/Downloads/Telegram%20Desktop/ace_runtime/core/governance/knowledge_evolution.py)
- 词库：[lexicon.py](file:///C:/Users/USER/Downloads/Telegram%20Desktop/ace_runtime/core/lexicon.py)
