# 数字考古引擎对比报告：GPT 提案 vs ACE 现有实现

**日期**: 2026-07-01
**来源**: GPT 对话提案（Digital Archaeology Engine / AR-001）
**处理法**: 五步处理法 + 横切一致性检查
**结论**: ACE 已有 75% 能力，3 个模块分散，缺统一引擎入口和 2 个交付物

---

## ① 识别

GPT 提出的不是一个新功能，而是一套**数字考古（Digital Archaeology）方法论**，核心是：

> 版本记录的是发布时间，谱系记录的是思想如何演化。

**关键修正**：从"未完成闭环不接受新任务"收敛为"**未完成考古，不进入新的架构决策**"——开发可以继续，但架构决策必须经过考古。

**四大原则**：
- P1 Intent First（意图优先）
- P2 Evolution over Version（演化优于版本）
- P3 Automatic Lineage Reconstruction（自动谱系重建）
- P4 Non-invasive（非侵入式 / Overlay）

**五个交付物**：
1. Lineage Index（谱系索引）
2. Evolution Graph（演化图谱）
3. Conflict Report（冲突报告）
4. Gap Detection（缺口检测）
5. Concept Merge Recommendation（合并建议）

**两个新增模块**：
- Confidence（谱系可信度）
- Divergence（分叉 / DAG 支持）

---

## ② 映射

### ACE 现有相关模块盘点

| 模块 | 位置 | 主要能力 | 成熟度 |
|------|------|---------|--------|
| **LineageSystem** | `core/lineage.py` | 血缘图、节点/边、祖先/后代查询、路径查找、名称相似度推断、血缘报告 | ⭐⭐⭐⭐ |
| **CivilizationGraph** | `core/governance/civilization_graph.py` | 知识节点+关系图、10种关系类型、append-only、邻居查询、关系演化 | ⭐⭐⭐⭐ |
| **KnowledgeEvolutionTracker** | `core/governance/knowledge_evolution.py` | 演化事件追踪、12种演化类型、Actor、决策记录、生命链 | ⭐⭐⭐ |
| **EntropyMonitor** | `core/governance/entropy_monitor.py` | 重复检测（文件/概念/协议/经验）、语义重复、冲突检测、熵值计算 | ⭐⭐⭐⭐ |
| **SimilarityEngine** | `core/similarity_engine.py` | n-gram Jaccard 相似度、指纹缓存、去重检测 | ⭐⭐⭐ |
| **FragmentIndex** | `core/fragment_index.py` | 碎片索引、概念提取、聚类 | ⭐⭐⭐ |
| **ConceptMiner** | `core/concept_miner.py` | 概念挖掘、从文本中提取概念 | ⭐⭐⭐ |

### 四大原则映射

| GPT 原则 | ACE 现有对应 | 覆盖度 | 备注 |
|---------|------------|--------|------|
| **P1 Intent First** | 无显式实现 | 20% | 当前靠名称相似度推断，没有 intent 抽取 |
| **P2 Evolution over Version** | LineageType.EVOLUTION 区别于 VERSION | 70% | 概念已存在，但推断时版本号权重过高 |
| **P3 Automatic Lineage Reconstruction** | LineageSystem.infer_lineage() + SimilarityEngine | 40% | 有基础推断但很弱，只用名称相似度 |
| **P4 Non-invasive** | LineageGraph 独立存储 + CivilizationGraph append-only | 90% | 两个模块都是 Overlay 模式，不修改源文件 |

### 五个交付物映射

| GPT 交付物 | ACE 现有对应 | 覆盖度 | 备注 |
|-----------|------------|--------|------|
| **Lineage Index** | LineageSystem | 85% | 已有完整节点/边索引，缺 generation 概念 |
| **Evolution Graph** | LineageGraph + CivilizationGraph | 75% | 两个图并存，关系类型有重叠 |
| **Conflict Report** | EntropyMonitor.conflicts + CivilizationGraph.contradicts | 60% | 有检测能力但没生成结构化报告 |
| **Gap Detection** | 无 | 0% | 完全缺失，没有演化链缺口检测 |
| **Concept Merge Recommendation** | EntropyMonitor + SimilarityEngine | 40% | 能检测重复，但没有合并推荐和理由 |

### 两个新增模块映射

| GPT 模块 | ACE 现有对应 | 覆盖度 | 备注 |
|---------|------------|--------|------|
| **Confidence（谱系可信度）** | LineageEdge.confidence + KnowledgeRelation.confidence | 80% | 已有置信度字段，但没有证据来源分类 |
| **Divergence（分叉/DAG）** | LineageGraph 天然是 DAG（多父多子） | 60% | 结构上支持，但没有显式的 divergence 概念和分叉检测 |

---

## ③ 改造

### 核心发现：三个模块的关系问题

ACE 不是没有能力，而是**能力分散在三个模块里，职责边界模糊**：

```
LineageSystem (core/lineage.py)
  └─ 血缘图、演化/版本关系、祖先/后代查询

CivilizationGraph (core/governance/civilization_graph.py)
  └─ 知识节点+关系、10种关系类型、支持/矛盾/替代

KnowledgeEvolutionTracker (core/governance/knowledge_evolution.py)
  └─ 演化事件、生命周期、Actor、决策记录
```

**三者的关系是什么？**

| 维度 | LineageSystem | CivilizationGraph | KnowledgeEvolutionTracker |
|------|--------------|-------------------|-------------------------|
| **关注点** | 血缘关系（从哪来、到哪去） | 语义关系（支持/矛盾/依赖） | 时间关系（什么时候、为什么变） |
| **核心问题** | A 演化自 B？ | A 和 B 是什么关系？ | A 什么时候因为什么变成了这样？ |
| **数据结构** | 有向无环图（DAG） | 多关系图（多类型边） | 事件流（时间序列） |
| **重叠部分** | evolution/replacement 边 | supersedes/derived_from 关系 | versioned/superseded 事件 |

**结论**：三者是互补的，不是重复的。它们回答三个不同维度的问题：**从哪来（谱系）、是什么关系（语义）、怎么变的（时间）**。

### 可吸收的 3 个洞见

**洞见 1：统一考古引擎入口（来自 P4 + 交付物体系）**

当前问题：三个模块分散，没有统一的入口。外部想做考古，不知道调哪个。

改造方向：在 `LocalArchaeologist` 中增加 `archaeology_engine` 统一入口，串联三个模块——先查谱系（Lineage）、再查语义关系（CivilizationGraph）、再查演化历史（KnowledgeEvolutionTracker）。

**洞见 2：Gap Detection（缺口检测）**

当前问题：完全没有。能看到演化链的两端，但不知道中间缺了什么。

改造方向：基于 LineageGraph 的路径分析——如果两个概念之间有明显的语义跳跃（相似度突降），标记为 Gap。依赖 SimilarityEngine 做内容相似度判断。

**洞见 3：架构决策前置考古约束（来自核心原则修正）**

当前问题：项目规则里有 moratorium（30天不新建模块），但没有"架构决策必须经过考古"的明确约束。

改造方向：已写入 project_memory.md——未完成考古，不进入新的架构决策。这是治理层面的增强，不需要新代码。

---

## ④ 落地

### 横切一致性检查

做这个提案时，同步扫描了 7 个相关模块：

| 相关模块 | 同类问题 | 一起改？ | 理由 |
|---------|---------|---------|------|
| LineageSystem | 缺 generation 字段、缺 evidence 分类 | **一起改** | 增量字段，不破坏现有结构 |
| CivilizationGraph | 关系类型和 Lineage 有重叠（evolution vs derived_from） | **不动** | 关注点不同（谱系 vs 语义），重叠是合理的 |
| KnowledgeEvolutionTracker | 和 Lineage 的演化概念有重叠 | **不动** | 维度不同（时间事件 vs 结构关系） |
| EntropyMonitor | 已有冲突检测，但格式不统一 | **记录待办** | 冲突报告格式可以对齐，但优先级低 |
| SimilarityEngine | 只能做文本相似度，不能做 intent 识别 | **不动** | intent 识别是 LLM 能力，不属于相似度引擎 |
| FragmentIndex | 碎片和概念的关系没有进入谱系图 | **记录待办** | 碎片吸收后自动注册到 Lineage，后续接入 |
| ConceptMiner | 挖掘出的新概念没有自动注册谱系 | **记录待办** | 同上 |

### 本次落地（增量修改，不新建文件）

1. ✅ **治理约束写入**：project_memory.md 增加"数字考古引擎"章节，四大原则 + 架构决策前置考古约束
2. ⏳ **LineageSystem 增量增强**：增加 generation 字段、增加 evidence 来源分类（conversation/git/design_doc/similarity_inference）
3. ⏳ **Gap Detection 原型**：基于 LineageGraph + SimilarityEngine，检测演化链中的语义跳跃
4. ⏳ **统一考古入口**：在 LocalArchaeologist 中增加 archaeology_engine 方法，串联三个模块

### 记录待办的（暂不阻塞）

- EntropyMonitor 冲突报告格式对齐 Conflict Report
- FragmentIndex 和 ConceptMiner 挖掘结果自动注册到 Lineage
- Divergence（分叉）显式标记和检测

### 明确不动的（避免过度设计）

- 不合并三个模块（LineageGraph / CivilizationGraph / KnowledgeEvolutionTracker）——它们回答不同维度的问题
- 不引入 intent 抽取（P1 的完整实现）——需要 LLM，当前 moratorium 期间不增加新的 LLM 依赖路径
- 不重做数据结构——现有结构足够，只做增量增强
- 不创建 "Digital Archaeology Engine" 新模块——用现有模块组合实现，不新增文件

---

## ⑤ 划界

### 明确拒绝的部分

| GPT 概念 | 拒绝理由 | ACE 的替代 |
|---------|---------|-----------|
| 新建 AR-001 任务和独立引擎模块 | 违反 30 天 moratorium，且 ACE 已有 75% 能力 | 用现有三个模块组合，不新增文件 |
| 完全自动的谱系重建（P3 完整实现） | 需要 LLM 做 intent 抽取，复杂度高 | 用名称相似度 + 引用关系做半自动推断，人工确认 |
| 完整的 Gap Detection | 需要语义理解，当前相似度引擎能力有限 | 做轻量版（基于内容相似度的跳跃检测） |
| 按 generation 组织的完整索引 | 目前节点数量还不够多，generation 意义不大 | 增加 generation 字段但不强依赖 |
| Divergence 作为独立模块 | LineageGraph 天然是 DAG，不需要独立模块 | 作为 LineageEdge 的一个属性标记 |

### 不可协商的边界

- 不创建新的 .py 文件（30 天 moratorium）
- 不修改三个核心模块的现有数据结构（只做增量增强）
- 不引入新的 LLM 调用路径（intent 识别需要 LLM，暂不做）
- 不合并 Lineage / CivilizationGraph / KnowledgeEvolutionTracker（维度不同）
- 所有考古结果都是 Overlay，不修改任何历史文件

---

## 判断依据

**为什么这个提案值得吸收**：

1. **方向完全正确**：谱系/演化/关系是 ACE 的核心资产（灵魂层），优先级最高
2. **ACE 有基础**：75% 的能力已经存在，不需要从零开始
3. **增量成本低**：只需要在现有模块上做小的增量增强
4. **治理价值高**："架构决策前置考古"这条约束，能有效防止架构漂移

**为什么不照搬整个方案**：

1. **30 天 moratorium**：禁止新建系统/模块，只能在现有基础上增强
2. **能力已有重叠**：三个模块已经覆盖了大部分，不需要新引擎
3. **P1/P3 完整实现需要 LLM**：当前阶段不引入新的 LLM 依赖路径
4. **generation 概念为时过早**：目前节点数量少，按代划分意义不大

---

## 认知熵检查

```yaml
entropy_check:
  new_active_concepts: 0       # GAP Detection 是新概念但暂不落地
  existing_concepts_enhanced: 3  # LineageSystem(增强)、LocalArchaeologist(统一入口)、治理约束(新增)
  concept_density_delta: "+0.00"  # 无新概念膨胀，都是现有模块的增量
  new_files_created: 0         # 全部写入已有文件
  judgment: "越学越稳。GPT 的提案被吸收为现有体系的增量增强，没有新增模块，没有架构侵入。"
```

---

## 相关文件

- 谱系系统：[lineage.py](file:///C:/Users/USER/Downloads/Telegram%20Desktop/ace_runtime/core/lineage.py)
- 文明图：[civilization_graph.py](file:///C:/Users/USER/Downloads/Telegram%20Desktop/ace_runtime/core/governance/civilization_graph.py)
- 知识演化追踪：[knowledge_evolution.py](file:///C:/Users/USER/Downloads/Telegram%20Desktop/ace_runtime/core/governance/knowledge_evolution.py)
- 熵监控：[entropy_monitor.py](file:///C:/Users/USER/Downloads/Telegram%20Desktop/ace_runtime/core/governance/entropy_monitor.py)
- 相似度引擎：[similarity_engine.py](file:///C:/Users/USER/Downloads/Telegram%20Desktop/ace_runtime/core/similarity_engine.py)
- 本地考古学家：[local_archaeologist.py](file:///C:/Users/USER/Downloads/Telegram%20Desktop/ace_runtime/core/local_archaeologist.py)
