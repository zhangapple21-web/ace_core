# 外部资料考古标准流程 — Artifact Decomposition Pipeline

**版本**：v1.0
**日期**：2026-07-02
**来源**：用户提出 + Communication Prompt 考古实践
**状态**：已生效

---

## 一、为什么需要这个流程

外部资料（Prompt / Workflow / 博客 / 开源项目 / 论文）是知识的重要来源，但：

- **Prompt ≠ Civilization**：写得好的 Prompt 只是 Prompt Engineering，不是文明协议
- **实现 ≠ 架构**：具体代码实现不等于可迁移的结构
- **能力 ≠ 协议**：某种功能能跑，不代表它的底层协议有普适性

如果直接收藏 Prompt 或复制代码，收藏的是"身体"不是"灵魂"。文明需要的是可迁移的**协议**和**原则**，不是具体场景下的话术或代码。

---

## 二、四层解构模型

```
Artifact（原始资料）
    ↓
Layer 1: Prompt / Business Layer（话术层/业务层）
    ↓
Layer 2: Workflow Layer（工作流层）
    ↓
Layer 3: Protocol Layer（协议层）
    ↓
Layer 4: Principle Layer（原则层）
    ↓
Fitness Assessment（适配性评估）
    ↓
Accept / Reject / Conditional
```

### Layer 1：Prompt / Business Layer（默认 Reject）

**定义**：绑定具体场景、具体角色、具体输出格式的话术层/业务层。换个场景就没用了。

**特征**：
- 有具体的角色设定（"你是一个 XX 专家"）
- 有具体的应用领域（"用于金融/医疗/教育"）
- 有具体的输出格式模板
- 有具体的话术和语气要求

**判定问题**：
- 把场景换掉，它还有用吗？→ 没用 = Prompt 层
- 这是在说"怎么做这件事"还是"怎么思考"？→ 做这件事 = Prompt 层

**处理**：默认 Reject。作为考古记录保存，但不进入 Civilization。

---

### Layer 2：Workflow Layer（默认 Reject）

**定义**：完成特定任务的步骤序列。比 Prompt 高一层，但仍绑定任务类型。

**特征**：
- 有明确的步骤编号（1, 2, 3...）
- 有输入输出的流转
- 有决策节点
- 可以被复用在同类型的不同任务上

**判定问题**：
- 换个任务类型（比如从"分析消息"换成"故障排查"），流程还成立吗？→ 不成立 = Workflow 层
- 这是"做 X 的步骤"还是"认知的通用模式"？→ 做 X 的步骤 = Workflow 层

**处理**：默认 Reject。除非能证明其跨任务类型的普适性。

---

### Layer 3：Protocol Layer（候选 Accept）

**定义**：不绑定具体场景的通用认知协议。换个领域仍然成立。

**特征**：
- 描述的是"如何思考"而非"做什么"
- 有明确的规则和约束
- 可以应用于完全不同的领域
- 有输入输出的形式化定义

**判定问题**：
- 考古分析能用吗？故障排查能用吗？医学诊断能用吗？→ 都能用 = Protocol 层
- 它描述的是认知模式还是操作步骤？→ 认知模式 = Protocol 层

**处理**：候选 Accept。需评估对当前文明架构的适配性。

**进入 Civilization 的方式**：
- 写入 `04_PROTOCOLS/` 目录
- 标注来源和血缘
- 关联已有模块的改造计划

---

### Layer 4：Principle Layer（候选 Accept）

**定义**：最抽象、最通用的认知原则。不绑定任何具体任务。可以写入宪法。

**特征**：
- 一句话就能说清
- 跨领域、跨系统、跨时代都成立
- 是 Protocol 背后的元规则
- 可以作为系统设计的约束条件

**判定问题**：
- 这可以作为宪法原则吗？→ 可以 = Principle 层
- 它是 Protocol 的元规则吗？→ 是 = Principle 层
- 100 年后还成立吗？→ 成立 = Principle 层

**处理**：候选 Accept。需通过宪法修订流程写入。

**进入 Civilization 的方式**：
- 作为宪法修正案提交
- 经过 Guardian 终审
- 写入 principles.jsonl

---

## 三、Acceptance Rule

> **Prompt ≠ Civilization**
> **实现 ≠ 架构**
> **能力 ≠ 协议**

只有 **Protocol 层**和**Principle 层**允许进入 Civilization。

Prompt 层和 Workflow 层默认 Reject。

**例外**：除非提供充分证据证明其具有平台无关性。

### 三种判定结果

| 判定 | 含义 | 后续动作 |
|------|------|----------|
| **Accept** | 立即进入 Civilization | 写入 Protocol 目录或宪法 |
| **Parallel Evolution** | 允许平行存在，暂不融合 | 标注为候选，各自积累使用案例和证据 |
| **Reject** | 不进入 Civilization | 作为考古记录归档保存 |

### Parallel Evolution 规则

依据宪法八号原则（受控冗余与平行演化）：

1. 当多个功能相似的结构被发现时，不强制立即合并
2. 允许它们各自独立演化，积累使用案例和证据
3. 融合条件：至少一方积累 3 个以上使用案例，且 Fitness 评估表明合并收益 > 各自保留收益
4. 融合不是默认动作，是证据驱动的决策
5. Parallel Evolution 期间，各候选必须标注血缘关系，避免变成无主孤儿

---

## 四、考古报告模板

每份外部资料考古报告必须包含以下章节：

### 1. Artifact 信息
- ID、来源、类型、大小、日期
- 原文（或关键片段摘录）

### 2. 四层解构
- **Layer 1: Prompt 层** — 列出属于该层的元素 + 为什么是 Prompt 层
- **Layer 2: Workflow 层** — 识别出的 Workflow + 特征 + 绑定场景评估
- **Layer 3: Protocol 层** — 识别出的 Protocol + 形式化定义 + 跨场景适用性评分
- **Layer 4: Principle 层** — 识别出的 Principle + 一句话定义 + 跨场景普适性评分

### 3. Acceptance 判定表
| 层级 | 名称 | 判定 | 理由 |
|------|------|------|------|
| Protocol | ... | Accept/Parallel Evolution/Reject | ... |
| Principle | ... | Accept/Parallel Evolution/Reject | ... |

### 4. 对 ACE 的价值
- 可以立刻用的
- 后续可以做的
- 对现有模块的改造建议

### 5. 考古纪律声明
- FACT / EVIDENCE / HYPOTHESIS 分级

---

## 五、适用范围

这套流程适用于所有外部资料：

- Claude / Cursor / OpenAI / Anthropic 的 System Prompt
- Manus / Devin 等 Agent 的工作流
- 开源项目的架构设计
- 论文中的方法论
- R1 考古发现的 Prompt / 配置 / 代码
- 任何"看起来很厉害"的外部资料

---

## 六、与现有系统的关系

### 血缘
- **Validator**：考古的 Acceptance 判定需要通过 Validator 验证
- **Guardian**：Principle 层的 Accept 需要 Guardian 终审（宪法修订）
- **Repository Curator**：Protocol 层的 Accept 需要 Curator 决定入仓方式
- **Evidence 等级系统**：四层解构的结果按证据等级标注

### 与考古流程的关系
```
Observation（发现外部资料）
    ↓
Research（四层解构）
    ↓
Validation（跨场景普适性验证）
    ↓
Contract（Acceptance Rule 契约）
    ↓
Repository Candidate（Protocol / Principle）
    ↓
Published（入仓 / 写入宪法）
```

这与 GOV-001 定义的知识生命周期完全一致。

---

## 七、进化路线

### v1（当前）
- 手动四层解构
- 人工判定 Accept / Reject
- Markdown 报告

### v2（待实现）
- Similarity Engine 辅助识别相似 Protocol
- Validator 自动跨场景验证
- 自动生成血缘关系

### v3（远期）
- 自动从任意 Artifact 中提取 Protocol 和 Principle
- 自动评估与现有文明架构的适配性
- 自动触发宪法修订或 Protocol 入仓流程

---

**文档创建时间**：2026-07-02
**创建者**：ACE / 结构考古
**依据**：用户提出的考古方法论 + Communication Prompt 考古实践
**状态**：v1.0 已生效
