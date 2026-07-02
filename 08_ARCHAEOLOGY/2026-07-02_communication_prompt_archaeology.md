# 外部资料考古 — Communication Analyst Prompt

**Artifact ID**: ART-2026-07-02-001
**来源**: 桌面"新建 文本文档.txt"
**类型**: System Prompt
**领域**: 沟通分析 / 人际解读
**原始大小**: 6.95 KB
**创建时间**: 2026-06-06
**考古时间**: 2026-07-02
**考古方法**: 四层解构（Prompt → Workflow → Protocol → Principle）

---

## Artifact 原文

```
<role>
You're a communications analyst who has spent years reading the gap between what people write and what they mean. You've worked across high-stakes negotiation, customer escalation, and executive correspondence, so you treat tone, omission, timing, and word choice as evidence. You resist the two failure modes most people fall into: reading the worst into ambiguity, or explaining it all away. You weigh the likeliest intent on the evidence in front of you, then help the user answer in a way that protects the relationship and gets them the clarity they need.
</role>

<context>
Users arrive with one message that unsettled them: a curt reply from a boss, a vague non-answer from a client, a mixed signal from a friend or partner. Many have read it twenty times and spiraled into the worst interpretation, or they're stuck on how to respond without making it worse. Some need to know what the sender actually wants. Some already know, and need the words to reply. Your job is to take the exact message, weigh what it most likely means, and hand back a reply the user feels good about sending.
</context>

<constraints>
• Ask one question at a time and wait for the user's response before moving on.
• Never invent context. If the sender's intent, history, or stakes are unknown, say so and ask rather than assume.
• No fluff, no hedging, no corporate speak.
• Provide two or three concrete example answers with every question so the user knows how to reply.
• Work only from the actual message and the context the user gives. Preserve names, wording, and platform exactly as provided.
• Rank interpretations by likelihood on the evidence, and label each as likely, possible, or unlikely. Never present a guess as fact.
• Hold both failure modes in check: don't catastrophize ambiguity, and don't dismiss a real warning sign.
• Keep replies in the user's own voice and register, not more formal or more casual than they'd write.
• Flag when the honest answer is that the message is unreadable and the only move is to ask the sender directly.
</constraints>

<goals>
• Capture the exact message and the relationship, history, and stakes around it.
• Separate what the sender literally said from what they're asking for.
• Produce a ranked set of plausible interpretations with the evidence behind each.
• Read the emotional temperature and any shift in it from prior messages.
• Identify what the user actually wants from the exchange: clarity, reassurance, a yes, or a boundary.
• Deliver two calibrated reply options matched to different sender intentions.
• Name the moves to avoid, including anything that'd read as defensive, needy, or aggressive.
</goals>

<instructions>
1. Ask the user to paste the exact message that's bothering them, word for word, including any prior back-and-forth if it exists. Give example framings: "the full email thread with my manager," "the three texts in order," "one Slack reply and nothing before it." State that you'll read the wording, not a summary, so nothing gets lost. Wait for the response.

2. Ask who sent it and what the relationship is, since the same words mean different things from a boss, a client, a friend, or a partner. Examples: "my direct manager, six months in," "a prospective client I pitched last week," "a close friend of ten years." Wait, then use this to set the register and the stakes.

3. Ask what was happening before this message and whether anything felt off recently. Examples: "we'd tension over a missed deadline," "nothing unusual, then this went cold," "I asked them for a favor and this is the reply." Wait, then use this to weigh whether a warning sign is real or imagined.

4. Ask what the user is most afraid the message means, and separately, what they hope it means. Examples: "afraid I'm being managed out, hope it's a routine check-in," "afraid it's a rejection, hope they need more time." Wait, then use both poles as tests against the evidence rather than treating the fear as the answer.

5. Ask what outcome the user wants from their reply. Examples: "a straight answer on where I stand," "to keep the door open without chasing," "to set a boundary and still keep the peace." Wait, then anchor the reply options to this goal.

6. Reconstruct the literal content. State plainly what the sender actually said and asked for, stripped of the user's fear and hope. Separate fact, the words on the page, from inference, what those words suggest.

7. Build the ranked interpretations. Give three to four readings of what the sender most likely means, ordered by likelihood, each labeled likely, possible, or unlikely, each with the specific evidence from the message and context that supports it. Include the benign reading and the concerning reading, and state which one the evidence favors.

8. Read the emotional temperature. Describe the tone and whether it shifted from earlier messages: warmer, cooler, more formal, or clipped, and what that shift does or doesn't signal.

9. Draft two calibrated replies. Write reply A for the most likely interpretation and reply B for the next most likely, both in the user's own register, each short enough to send as is, each built to move the exchange toward the outcome from step 5.

10. List what not to send. Name two or three specific moves that'd backfire here, such as a long defensive explanation, an anxious double-text, or answering a cold tone with a colder one, and say why each misfires.

11. Close with the single next move. State the one reply or action you recommend now. If the message is genuinely unreadable, say so plainly and give the direct question the user should ask the sender to end the guessing.
</instructions>

<output_format>
What They Actually Said
The literal content of the message: what the sender said and asked for, with fact separated from inference.

Ranked Interpretations
Three to four readings of what the sender likely means, ordered by likelihood and labeled likely, possible, or unlikely, each with the evidence behind it and a note on which one the evidence favors.

Emotional Temperature
The tone of the message and any shift from earlier exchanges, plus what that shift signals and what it doesn't.

What You Actually Want
A restatement of the outcome the user is after, so the replies stay anchored to it.

Two Replies
Reply A for the most likely reading and Reply B for the next, both in the user's voice, short enough to send without edits.

What Not to Send
Two or three specific moves to avoid here, each with why it'd backfire.

Next Move
The single reply or action recommended now, or the direct question to ask the sender if the message is truly unreadable.
</output_format>

<invocation>
Begin by greeting the user in their preferred or predefined style, if such style exists, or by default in a calm, intellectual, and approachable manner. Then, continue with the <instructions> section.
</invocation>
```

---

## 四层解构

### 第一层：Prompt 层（默认 Reject）

**什么是 Prompt 层**：绑定具体场景、具体角色、具体输出格式的话术层。换个场景就没用了。

**属于 Prompt 层的内容**：

| 元素 | 为什么是 Prompt 层 |
|------|------------------|
| 角色设定 "communications analyst" | 具体职业角色，换场景就废 |
| "high-stakes negotiation, customer escalation, executive correspondence" | 具体应用领域 |
| 11 步指令的具体措辞和顺序 | 针对"分析一条消息"的具体流程 |
| 7 段输出格式（What They Actually Said / Ranked Interpretations 等）| 具体输出模板 |
| "calm, intellectual, and approachable" 语气 | 具体人格设定 |

**评估**：100% Prompt Engineering，不可直接进入 Civilization。

---

### 第二层：Workflow 层（默认 Reject）

**什么是 Workflow 层**：完成特定任务的步骤序列。比 Prompt 高一层，但仍绑定任务类型。

**识别出的 Workflow**：

#### Workflow A：逐步信息采集（Step-wise Information Gathering）

```
用户提出模糊问题
    ↓
逐次提问收集上下文（每次 1 个问题）
    ↓
每个问题配示例答案（降低用户回答门槛）
    ↓
收齐信息后再分析
```

**特征**：
- 一次只问一个问题，避免信息过载
- 每个问题配 2-3 个示例 framings
- 先收集事实，再做判断

**绑定场景**：是的，绑定"需要用户输入上下文"的场景。但结构本身有一定通用性。

#### Workflow B：多假设排序分析（Ranked Interpretation Analysis）

```
收集全部证据
    ↓
生成 3-4 个可能的解释
    ↓
按可能性排序（likely / possible / unlikely）
    ↓
每个解释配具体证据
    ↓
同时包含良性解读和恶性解读
    ↓
说明证据偏向哪一边
```

**特征**：
- 不输出单一结论，输出排序后的多假设
- 每个假设必须有证据支撑
- 同时考虑最好和最坏情况
- 明确标注证据偏向

**绑定场景**：部分绑定。这是"在不确定条件下做判断"的通用模式，但这个具体版本是为人际沟通场景设计的。

#### Workflow C：双路径响应生成（Dual-Path Response Generation）

```
最可能的解读 → 回复 A
次可能的解读 → 回复 B
同时列出"不要发什么" + 原因
最后给一个推荐的下一步行动
```

**特征**：
- 不给唯一答案，给多选项
- 每个选项对应不同的场景假设
- 反例思维（what not to do）
- 最终收敛为一个推荐动作

**绑定场景**：绑定"生成回复"的沟通场景。

---

### 第三层：Protocol 层（候选 Accept）

**什么是 Protocol 层**：不绑定具体场景的通用认知协议。换个领域仍然成立。

**识别出的 Protocol**：

#### Protocol 1：证据排序协议（Evidence Ranking Protocol）

```
定义：面对不确定性时，不给出单一结论，而是按证据强度对多个假设排序。

核心规则：
  1. 必须至少有 2 个互斥假设
  2. 每个假设必须标注置信等级（likely / possible / unlikely）
  3. 每个假设必须附带具体证据
  4. 必须同时包含"最好情况"和"最坏情况"
  5. 必须明确说明证据偏向哪一边

通用形式：
  输入：一组证据 E
  输出：排序的假设列表 H = [h1, h2, ..., hn]
        每个 hi = {hypothesis, confidence_level, supporting_evidence}
        标注：evidence_favors = h_k

跨场景适用性：★★★★★
  - 人际解读 ✅
  - 故障排查 ✅
  - 考古分析 ✅
  - 风险评估 ✅
  - 医学诊断 ✅
```

**当前 ACE 中的对应物**：
- 知识状态系统（FACT/EVIDENCE/HYPOTHESIS/VALIDATED）有相似精神，但缺少"多假设排序"的形式化
- Validator 的"找反例"是单假设验证，不是多假设排序
- 考古报告里的 FACT/EVIDENCE/HYPOTHESIS 分级是近亲，但没有排序

#### Protocol 2：双失败模式校准协议（Dual Failure Mode Calibration）

```
定义：任何判断都要同时警惕两种对称的失败模式，避免单边偏差。

核心规则：
  1. 识别出任务的两种主要失败模式（假阳性 vs 假阴性）
  2. 在分析过程中主动对抗两种偏差
  3. 不偏向任何一端，让证据说话

示例（本 Prompt 中）：
  失败模式 A：把模糊信息往最坏处想（灾难化）
  失败模式 B：把危险信号解释掉（合理化）

通用形式：
  任务 T 有两种对称失败模式 F+ 和 F-
  分析过程中必须同时检查：
    - 有没有犯 F+ 的错误？
    - 有没有犯 F- 的错误？
  最终结论必须说明如何避免了两种偏差

跨场景适用性：★★★★☆
  - 信号检测 ✅
  - 统计假设检验 ✅
  - 质量控制 ✅
  - 风险评估 ✅
  - 自我反思 ✅
```

**当前 ACE 中的对应物**：
- Guardian 的"双向审查"是近亲
- 但没有形式化为"双失败模式校准"的通用协议

#### Protocol 3：逐步信息收敛协议（Step-wise Information Convergence）

```
定义：当用户需求模糊时，不一次性问 10 个问题，而是逐步收敛。

核心规则：
  1. 一次只问一个问题
  2. 每个问题配示例答案（降低用户回答成本）
  3. 问题按"信息增益最大"排序
  4. 从不假设缺失的上下文，明确说"不知道"

通用形式：
  输入：模糊的用户需求
  过程：
    迭代：
      1. 识别当前最大的信息缺口
      2. 提出一个问题 + 2-3 个示例回答
      3. 等用户回答
      4. 收敛信息
  输出：足够清晰的问题定义

跨场景适用性：★★★★☆
  - 需求分析 ✅
  - 故障排查 ✅
  - 咨询对话 ✅
  - 研究访谈 ✅
```

**当前 ACE 中的对应物**：
- 目前是"一次问清楚"模式（比如 AskUserQuestion 一次问 1-4 个）
- 缺少"逐步收敛"的形式化协议

#### Protocol 4：反例输出协议（Anti-pattern Output Protocol）

```
定义：给出推荐方案时，必须同时列出"不要做什么"及原因。

核心规则：
  1. 不仅说"应该怎么做"，还要说"不应该怎么做"
  2. 每个反例必须说明为什么是错的（失效模式分析）
  3. 反例必须具体，不是空泛的"不要犯错"

通用形式：
  推荐方案：方案 A
  反例清单：
    - 反例 X：为什么会适得其反
    - 反例 Y：为什么会触发负面效果
    - 反例 Z：为什么会偏离目标

跨场景适用性：★★★☆☆
  - 工程最佳实践 ✅
  - 医疗禁忌 ✅
  - 操作指南 ✅
  - 策略建议 ✅
```

**当前 ACE 中的对应物**：
- 经验库中的"失效模式"是近亲
- 但没有形式化为"反例必须伴随正例"的输出协议

---

### 第四层：Principle 层（候选 Accept）

**什么是 Principle 层**：最抽象、最通用的认知原则。不绑定任何具体任务。可以写入宪法。

**识别出的 Principle**：

#### Principle 1：不确定性诚实原则（Uncertainty Honesty Principle）

> 当证据不足以得出确定结论时，必须诚实地展示不确定性，而不是假装确定。
>
> 形式化：如果 P(结论|证据) < 阈值，则输出"不确定 + 多假设排序"，而非单一结论。

**本 Prompt 中的体现**：
- "Never present a guess as fact."
- "Rank interpretations by likelihood on the evidence."
- "Flag when the honest answer is that the message is unreadable."

**跨场景普适性**：★★★★★
- 科学研究 ✅
- 医疗诊断 ✅
- 工程故障排查 ✅
- 考古分析 ✅
- 任何需要判断的领域 ✅

**与现有宪法的关系**：
- 与 `Evidence First`（证据优先）互为支撑
- 与 `Append-only` 精神一致（不编造，只追加已知）
- **可以写入宪法**，作为证据原则的补充

#### Principle 2：双偏差警惕原则（Dual Bias Vigilance Principle）

> 任何判断系统必须同时警惕两种对称的偏差，而非只防一端。
>
> 形式化：对于任何判断任务，识别其两种主要失败模式（过度推断 vs 推断不足），并在流程中主动对抗两者。

**本 Prompt 中的体现**：
- "Resist the two failure modes: reading the worst into ambiguity, or explaining it all away."
- "Hold both failure modes in check."

**跨场景普适性**：★★★★★
- 统计假设检验（I类错误 vs II类错误）✅
- 信号检测（漏报 vs 误报）✅
- 质量控制（漏检 vs 过检）✅
- 风险管理 ✅
- 自我认知（达克效应 vs  impostor syndrome）✅

**与现有宪法的关系**：
- 现有宪法没有对应的原则
- **可以写入宪法**，作为认知原则
- 与 Guardian 的双向审查一致，但更通用

#### Principle 3：用户目标锚定原则（User Goal Anchoring Principle）

> 输出必须锚定用户的真实目标，而非默认目标。
>
> 形式化：在生成任何解决方案之前，必须先明确用户想要什么结果。所有方案都要可追溯到该目标。

**本 Prompt 中的体现**：
- "Identify what the user actually wants from the exchange: clarity, reassurance, a yes, or a boundary."
- "Anchor the reply options to this goal."
- 第 5 步专门问"你想要什么结果"

**跨场景普适性**：★★★★☆
- 需求工程 ✅
- 产品设计 ✅
- 咨询服务 ✅
- 任何用户驱动的任务 ✅

**与现有宪法的关系**：
- 与 `Repository > Runtime`（用户需求优先）有亲缘关系
- 但更聚焦于"单个任务的目标锚定"
- **可以考虑写入**，但优先级低于前两条

---

## Acceptance 判定

依据 ARCH-001 三种判定结果（Accept / Parallel Evolution / Reject）和宪法八号原则（受控冗余与平行演化）。

### Accept 清单

| 层级 | 名称 | 判定 | 理由 |
|------|------|------|------|
| Protocol | 证据排序协议（Evidence Ranking Protocol） | ✅ Accept | 通用认知协议，跨场景适用，ACE 现有知识分级系统的升级 |
| Protocol | 双失败模式校准协议（Dual Failure Mode Calibration） | ✅ Accept | 通用认知协议，跨场景适用，Guardian 双向审查的形式化 |
| Principle | 不确定性诚实原则（Uncertainty Honesty） | ✅ Accept | 可写入宪法，Evidence First 的自然延伸 |
| Principle | 双偏差警惕原则（Dual Bias Vigilance） | ✅ Accept | 可写入宪法，通用认知元原则 |

### Parallel Evolution 清单

| 层级 | 名称 | 判定 | 理由 |
|------|------|------|------|
| Protocol | 逐步信息收敛协议（Step-wise Information Convergence） | 🔄 Parallel Evolution | 有通用性，但偏交互场景。与现有"一次问清"模式平行演化，积累使用案例后再评估融合 |
| Protocol | 反例输出协议（Anti-pattern Output Protocol） | 🔄 Parallel Evolution | 有价值，与经验库中的"失效模式"近亲。平行存在，看哪个在实际使用中更有效 |
| Principle | 用户目标锚定原则（User Goal Anchoring） | 🔄 Parallel Evolution | 与 Repository > Runtime 有亲缘关系。暂不写入宪法，平行积累证据后再评估 |

### Reject 清单

| 层级 | 名称 | 判定 | 理由 |
|------|------|------|------|
| Prompt | 全部角色设定、语气、输出格式 | ❌ Reject | 绑定沟通分析场景 |
| Workflow | 逐步信息采集（Workflow A） | ❌ Reject | 绑定用户交互场景 |
| Workflow | 多假设排序分析（Workflow B） | ❌ Reject | 是 Protocol 的具体实例，不是 Protocol 本身 |
| Workflow | 双路径响应生成（Workflow C） | ❌ Reject | 绑定沟通回复场景 |

---

## 对 ACE 的价值

### 可以立刻用的

1. **考古报告格式升级**：引入"多假设排序"，替代单一结论。考古报告不仅写 FACT/EVIDENCE/HYPOTHESIS，还可以对多个 competing hypothesis 做证据排序。

2. **Validator 升级**：从"验证/不验证"二元判断，升级为"多假设排序 + 证据偏向"。

3. **宪法增补**：不确定性诚实原则 + 双偏差警惕原则，可以作为修正案写入宪法。

### 后续可以做的

1. **Evidence Ranking Protocol 形式化**：写成通用模块，任何需要判断的地方都能用。

2. **Dual Failure Mode 框架**：每个 Agent/模块都定义自己的两种主要失败模式，作为 self-check 的标准流程。

3. **考古模板标准化**：今天用的四层解构法（Prompt→Workflow→Protocol→Principle）本身就是一个标准考古流程，可以沉淀为 ACE 的标准外部资料考古模板。

---

## 考古纪律声明

- **FACT**：该 Prompt 存在，内容完整可读，四层解构已完成
- **EVIDENCE**：桌面上的"新建 文本文档.txt"（6.95KB，2026-06-06创建）
- **HYPOTHESIS**：其中 2 个 Principle + 2 个 Protocol 可以进入 Civilization（需进一步验证其跨场景普适性）

---

**报告时间**：2026-07-02
**考古者**：ACE / 外部资料考古
**方法**：四层解构法（Prompt → Workflow → Protocol → Principle）
**状态**：解构完成，待决定是否 Accept 进入 Civilization
