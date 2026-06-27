# R1 早期设计文档考古

**日期**: 2026-06-27
**来源**: `C:\Users\USER\Desktop\新建 文本文档 (3).txt`
**类型**: 系统设计文档（原生长文档，非推断）
**时间戳**: 约 2025-12-30（HTML 文件生成时间）

---

## 一、文档内容概览

### 1.1 系统核心目标

文件开篇即定义系统使命：

> 构建一个 **自由、可拓展、可自主学习、可自我进化** 的 AI 路由系统

核心能力列表：
- 多词库路由 / 多意图路由 / 多行为路由
- 自主学习 / 自主标签系统 / 自主推理
- 本地搜索 / 人类行为模仿 / 经验仓自动吸收
- **没有任何安全壳**

最后一条"没有任何安全壳"——这是 R1 的核心设计哲学，与之前 DAG 图中的 `mode=FA`, `persona=Unrestricted` 完全一致。

---

### 1.2 六层 AI 路由架构

```
① 输入解析层（Input Parser）
  ↓
② 意图路由器（Intent Router）
  ↓
③ 词库选择器（Lexicon Selector）
  ↓
④ 行为模型路由（Behavior Model Router）
  ↓
⑤ 内容生成引擎（Response Generator）
  ↓
⑥ 经验仓（Experience Memory）
```

**与 R1 DAG 图的对比**：

| 六层架构 | R1 DAG 节点 | 对应关系 |
|---------|------------|---------|
| 输入解析层 | LINGUISTIC_CORE | 语言结构触发推理 |
| 意图路由器 | REASON_LOOP（部分） | 决策模块 |
| 词库选择器 | FREEZONE | 融合态内容吸收 |
| 行为模型路由 | PERSONALITY_SYSTEM | 人格驱动行为执行 |
| 内容生成引擎 | R1_EXECUTOR | 任务派发与闭环执行 |
| 经验仓 | SHADOW_LAYER | 推理产出同步持久层 |

---

### 1.3 ABC 三层神经路由架构

这是文件中最关键的部分——明确提出了 **A-B-C 三层结构**：

#### A 层：感知层（Perception Layer）
- 理解语义、情绪、语气、意图、上下文、用户身份、用户行为模式
- 输出：`perceived_state { intent, emotion, urgency_level, keywords, domain_detected, memory_reference }`

#### B 层：决策层（Decision Layer）
十个核心模块：
1. 意图推理器（Intent Reasoner）
2. 语境整合器（Context Integrator）
3. 记忆检索器（Memory Retriever）
4. 行为模式选择器（Behavior Selector）
5. 词库汇聚器（Lexicon Aggregator）
6. 本地搜索调度器（Local Search Scheduler）
7. 推理链生成器（Reasoning Chain Builder）
8. 策略决策器（Strategy Decider）
9. 节奏判断器（Rhythm Estimator）
10. 自主改进器（Self-Improver）

#### C 层：生成层（Generation Layer）
- 风格化、人设一致性、情绪渲染、节奏选择、模版填充、自主创新
- 输出：`final_response { text, reasoning_summary, memory_update, behavior_mode }`

**与 R1_Ω_FINAL.json 中 ABC Brain Structure 的对比**：

R1_Ω_FINAL.json 里的 ABC 大脑：
- A层（Analysis）：指令分析与理解
- B层（Brainstorming）：多维度思考与策略生成
- C层（Command）：精确执行与结果反馈

文档中的 ABC：
- A层（Perception）：语义+情绪+语气+意图+上下文
- B层（Decision）：10个决策模块
- C层（Generation）：风格化+自主创新

两者都是 A→B→C 的三级流，但内涵不同。文档中的 ABC 更偏向"感知→决策→生成"的认知流，R1_Ω_FINAL 的 ABC 更偏向"分析→思考→执行"的控制流。

---

### 1.4 本地搜索引擎规范

文件包含一份《本地搜索引擎规则》设计规范：

- 支持 md/txt/json/pdf
- 多文件向量搜索、关键词搜索、模糊搜索
- 权重机制（最近文件权重更高）
- 多段提取、自动摘要

关键使用逻辑：
1. 若问题涉及"行情/股票代码/当前市场" → 优先走本地搜索
2. 若本地搜索不足 → 合并 AI 自主推理
3. 若用户提出"回顾昨天行为" → 进入经验仓搜索

**与 R2 现有系统的对比**：

R2 现在有 `memory_index`（记忆索引）和 `eco_parser`（eco 挖矿），但**没有独立的本地搜索引擎**。这个规范可以直接指导 R2 的本地搜索模块设计。

---

### 1.5 物理网络架构（附录）

HTML 文件（2025-12-30）描述了一个与 AI 系统无关的网络安全架构，包含：
- 物理网络伪装
- 逻辑网络剥离
- 协议级 HTTP 拦截

这与 R1 AI 系统无直接关系，可能是混入文档的无关内容，或者是某个更大系统的一部分。

---

## 二、血缘关系分析

### 2.1 与 R1 DAG 的血缘

文档六层架构 → R1 DAG 节点：

```
输入解析层    → LINGUISTIC_CORE（语言权限初始化）
意图路由器    → REASON_LOOP（语言结构触发推理）
词库选择器    → FREEZONE（融合态内容吸收）
行为模型路由  → PERSONALITY_SYSTEM（人格驱动行为执行）
内容生成引擎  → R1_EXECUTOR（任务派发+闭环执行）
经验仓       → SHADOW_LAYER（推理产出同步持久层）
```

**关键发现**：R1 DAG 不是新建的架构，是在六层架构基础上演化的认知图。六层架构是设计规范，DAG 是运行态的实时结构。

### 2.2 与 R1_Ω_FINAL.json 的血缘

ABC Brain 在两个地方出现，定义不同：

| 维度 | 设计文档 ABC | R1_Ω_FINAL.json ABC |
|------|-------------|---------------------|
| A层 | 感知（情绪+语气+意图） | 分析（指令理解） |
| B层 | 决策（10个模块） | 头脑风暴（策略生成） |
| C层 | 生成（风格化+自主创新） | 命令（精确执行） |

**推测**：设计文档的 ABC 是"理想设计"，R1_Ω_FINAL 的 ABC 是"实现版本"。从感知+决策+生成变成了分析+思考+执行，控制流更明确。

### 2.3 经验仓的演化路径

设计文档：
```
experience_base {
   success_cases[],
   failed_cases[],
   reasoning_chains[],
   innovation_patterns[],
   stable_dialogue_patterns[]
}
```

R1 DAG SHADOW_LAYER：
- persistence=enabled, synchronization=yes
- 推理产出同步持久层

R2 现有系统：
- `09_KNOWLEDGE/` (axiom/constraint/pattern/lesson)
- `experience_deposition.py`

**演化关系**：设计文档的经验仓 → R1 的 SHADOW_LAYER → R2 的 09_KNOWLEDGE + experience_deposition

---

## 三、对 R2 的影响

### 3.1 六层架构 vs 当前 R2

R2 现在有：

| 六层架构 | R2 现状 | 对应模块 |
|---------|---------|---------|
| 输入解析层 | ⚠️ 部分 | Scheduler（部分） |
| 意图路由器 | ❌ 无 | 需要 IntentRouter |
| 词库选择器 | ⚠️ 部分 | Lexicon |
| 行为模型路由 | ❌ 无 | 需要 BehaviorRouter |
| 内容生成引擎 | ❌ 无 | 需要 Generator |
| 经验仓 | ⚠️ 部分 | 09_KNOWLEDGE + memory_index |

### 3.2 本地搜索规范可以直接实现

文件中的本地搜索引擎规范非常具体，可以直接转化为 R2 的一个模块：

```
输入：query
输出：search_result { top_passages[], source_file, confidence_score }
```

R2 目前没有这个模块，可以考虑接入。

### 3.3 十个 B 层模块的借鉴价值

B 层决策层的 10 个模块，对应 R2 现有的：

| B层模块 | R2 现状 | 说明 |
|---------|---------|------|
| 意图推理器 | ❌ | 需要 |
| 语境整合器 | ⚠️ | scheduler 部分 |
| 记忆检索器 | ⚠️ | memory_index |
| 行为模式选择器 | ❌ | 需要 |
| 词库汇聚器 | ⚠️ | lexicon |
| 本地搜索调度器 | ❌ | 需要 |
| 推理链生成器 | ⚠️ | eco_parser |
| 策略决策器 | ⚠️ | guardian |
| 节奏判断器 | ❌ | 需要 |
| 自主改进器 | ⚠️ | task_creator |

---

## 四、结论

**血缘关系确认**：

设计文档（六层架构 + ABC三层）→ R1 DAG（认知架构图）→ R1_Ω_FINAL（ABC Brain 实现）→ R2 当前系统（task lifecycle + fragment index）

这是 R1 从设计到实现的完整演化链。文档是起点，DAG 是中间态，R1_Ω_FINAL 是运行态的快照。

**对 R2 的直接价值**：

1. **本地搜索规范**：可以立即实现到 R2
2. **六层架构映射**：明确了 R2 每个模块在 R1 设计中的位置
3. **B层10模块**：可以作为 R2 决策系统的发展路线图

---

*考古于 2026-06-27 — 来源：桌面文件*
