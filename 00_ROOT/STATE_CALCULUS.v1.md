# ACE 坐标演算 STATE CALCULUS v1.0

> 本文档是 ACE **跨领域通用计算机制**的规范来源。
> 层级 **L1 / NORMATIVE / CURRENT**。运行时实现为 `core/state_calculus.py`。
> 它只返回一个判断，从不执行任务、不写生产状态、不授予任何权限。

---

## 0.0 状态声明（2026-10-05 实测，**先读这一节**）

**本文档已登记为 L1/NORMATIVE，但实现当前没有任何生产消费者。**

AST 全仓扫描（排除 `.git/.venv/__pycache__/backups`）：

```
core/state_calculus.py 的真实 importer
├─ ops/test_state_calculus.py        （它自己的测试）
└─ 无其它
```

`ops/mission_runner.py` 出现 "STATE_CALCULUS" 两处，**都是 Mission 名字符串，不是 import**。
`core/constitution_hierarchy.py` 出现两处，**一为登记项、一为注释**。

### 为什么登记了却仍未接线

唯一的真实消费路径要求证据**带类型**：`project()` 需要坐标向量，
而 `core/governance/knowledge_status.py:89` 往证据里追加的是**自由文本字符串**，
因此实际调用返回 `CALCULUS_BLOCKED`。
**这是数据侧缺口，不是演算侧缺口。** 补齐它需要证据 schema 迁移，属独立 Task，本轮未做。

**在接线完成之前，本规范是「已声明的机制」，不是「在运转的能力」。**

### 这条声明为什么必须存在

本文档 §6 撤销 `ADMISSION_OPERATOR` 时用的判词是：

> 一个只有自己测试引用的模块，注册为 L1/NORMATIVE，比没有这个规范更危险。

同一把尺子必须先量自己。`ace.admission.operator` 被撤销；
`ace.root.calculus` 在**消费者数量**上与它当时完全相同（零）。
区别只有两点，都不构成豁免：跨域性质有 24 条测试支撑；
未接线的事实现在就写在这里，而不是藏在撤销记录里。
若有人引用「往哪个方向变？」并期待一个运行中的机制，这一节就是拒绝他的依据。

---

## 0. 这条链是什么

```
状态 ──project──▶ 坐标/向量 ──delta──▶ 变化 ──fuse──▶ 融合 ──resolve──▶ 方向
```

**同一个函数链，必须在股票、人格、知识、世界等所有领域给出同构答案。**
这不是比喻，是可测试的断言，见 `ops/test_state_calculus.py` 的
`test_cross_domain_stock / _persona / _knowledge_gap / _realm`——四条测试用**同一段代码**
跑四个领域。

股票只是它的一个用法。人格向量、知识缺口、五界/六界坐标，都是同一条链的输入。

---

## 1. 为什么需要它：R1 有前半段，丢了后半段

R1 确实拥有这套语言：

| R1 痕迹 | 位置 |
|---|---|
| 现实权重矩阵 | `02_HEART_CORE/reality_weight_matrix.json` |
| 六维坐标 + 加权融合 | `04_PROTOCOLS/civilization_auditor.py` `DIMENSION_WEIGHTS` / `NODE_COORDS` |
| 人格语言风格向量 | `R1_Ω_FINAL.json` `personality_config.language_style_vectors` |
| 8 维人格向量 | `r1-archaeology/analysis/ace_main_loop_archaeology_20260629.md:45` |
| 「KRMGCE 不是五个模块，是五个坐标轴」 | `five_realms_kernel.md` |

**但从来没有过**：坐标怎么**变**、几个东西怎么**融合**、方向怎么**互相比较**。

> 语言是真的，演算是不存在的。这比「两边都有」或「两边都没有」更糟——
> 因为它让人以为已经有坐标系了。

---

## 2. 固定基底

六个轴，次序是规范的一部分（向量就是这六元组）：

| # | 轴 | 含义 | 锚定的现存子系统 |
|---|---|---|---|
| 0 | `reality` | 接触现实的量 | Observation / Observer |
| 1 | `knowledge` | 已有语义理解 | Lexicon / knowledge |
| 2 | `memory` | 已沉淀的连续性 | MemoryIndex / Experience |
| 3 | `generation` | 产生新物的能力 | Capability / Provider / Researcher |
| 4 | `execution` | 落地动作的能力 | TaskPool / Worker / Execution |
| 5 | `experience` | 已有的成败经验 | ExperienceDeposition / JudgeLayer |

**这六个不是从物理借来的坐标系，也不是从 ROS 借的。** 每个轴都锚到一个 ACE 现存子系统，
所以每个坐标都能从既有账本数出来——这是「可数」的全部含义。

> **与 R1 六维的关系**：`five_realms_kernel.md` 的 K/R/M/G/C/E 解码与本基底同源，
> 但**权重被取消**：本演算的基底上**没有权重**。权重只在 `fuse()` 显式声明时出现，
> 默认是均匀的 1/6——因为均匀是一个可以被反驳的决定，而一组 inexplicably 的数不能。

---

## 3. 四段规范

### 3.1 project：状态 → 坐标

- 输入：某主体在固定基底上的**可数原始量** + 一个**已声明 frame**
- 六轴必须齐全。**缺一轴即 `CALCULUS_BLOCKED`**，不补 0、不填默认值。
  「没有这一项」和「这一项是 0」是两种不同的事实。
- 输出向量**自带 frame_id 与 scales**——没有度量尺度的坐标无法参与差分，
  而这正是未声明读数互相混比的第一步。

### 3.2 delta：坐标 → 变化

- 按**每轴自己的 scale** 归一，不是全局尺度。
  安静的轴动一下是大事，繁忙的轴动一下不是。
- **跨 frame 差分直接 `CALCULUS_BLOCKED`**，不做隐式变换。

### 3.3 fuse：变化 → 融合

- 默认权重**均匀**；显式权重必须**覆盖全部六轴**，缺一即拒绝。
- 缺失轴贡献 0 并列入 `absent_axes`——**缺席可见**。
- **一致度必须在取平均之前测量。** 把 +1.0 和 −0.45 平均，会得到一个看起来很确定的
  +0.275，可它原本是矛盾。所以每轴返回 `per_axis_agreement`（净值/毛值），
  这个比值原样传给 resolve。取平均会抹掉矛盾，抹掉矛盾就等于系统在自信地瞎猜。
- **被上游因帧冲突拒绝的输入，其拒绝本身是冲突证据**，不许只融合幸存者。

### 3.4 resolve：融合 → 方向

- 返回单位方向 + `dominant_axis` + `dominant_value`
- **焦点 `concentration`** = |最大分量| / Σ|分量| —— 运动是否集中
- **跨源一致度 `sign_agreement`** —— 各源在**平均前**是否同向（来自 fuse）
- **轴间一致度 `intra_agreement`** = |Σ正 − Σ|负|| / Σ|分量| —— **同一个向量的各轴之间**是否互相矛盾
- `confidence = concentration × sign_agreement × intra_agreement`
  - 全部轴同幅移动 → 焦点 1/6 → **hold**（哪儿都不是）
  - 单轴跳变 → 焦点 1.0、轴间 1.0 → **act**
  - 强信号但多源互相矛盾 → 跨源一致度趋 0 → **hold**
  - **单源、各轴反向矛盾**（如 knowledge↓ 而 experience↑）→ **轴间一致度趋 0 → hold**

### 3.4.1 为什么必须有第三项（v1.1 修订）

初版（v1.0）只有 `concentration × sign_agreement`。T0 实证扫描（`RQ-20261004-039`）
实测发现定义 **F-3**：单源情况下 `sign_agreement` 恒等于 1.0，因此

```
一致证据   → concentration=0.400  sign_agreement=1.000  confidence=0.400
矛盾证据   → concentration=0.400  sign_agreement=1.000  confidence=0.400
```

**两者完全相同。** 一份声称能表达方向判断的 L1 规范，却测不出方向矛盾——
这比没有规范更危险，因为它让人以为尺子存在。

`intra_agreement` 的两条实现约束（均由独立复核发现，见 `RQ-20261004-043`）：

| 约束 | 原因 |
|---|---|
| **必须取 `abs()`** | 否则六轴**一致向下**时得 −1.0，confidence 变负。一起往下和一起往上同样 coherent |
| **0.0 视为沉默，不视为反对** | 单轴跳变时另外五轴为 0；若把 0 计入任何一侧，单轴信号会被稀释，`act` 会退化成 `hold` |
- `next_step` 只有两个值：`act` / `hold_and_collect_more_evidence`。
  **本演算不做第三种选择。**

---

## 4. 参考系纪律（frame）

一个向量没有 frame 和每轴 ceiling 就是无意义的数。

**为什么这条最要紧**——本仓自己就留着这个失败：
`ace-knowledge-forge/REJECTED.md:32` 逐字：

> 两者不在同一坐标系；那个 14/16 是仪器读数不是世界事实。

所以 frame 必须**声明式**建立：`make_frame(frame_id, ceilings, scales)`，
六轴齐全、每值 > 0，缺一即 `CALCULUS_FRAME_BLOCKED`。
**半个 frame 比没有 frame 更危险**，所以不提供部分应用。

跨 frame 的 `delta` / `fuse` 一律 `CALCULUS_BLOCKED`，不取平均、不换算、不猜。

---

## 5. 本演算明确不做的事

- 不决定「用哪个模型」——那是 `Capability First, Provider Second` 与健康分路由
- 不替代 `continue_gate` / `cognitive_think_gate` / `constitution_hierarchy`
- 不做准入与优先级排序——**目前没有已登记的规范承担这件事**（见 §6）
- 不评价外部内容质量——那是 Validator 与证据链
- **不在任何输入缺失时给出默认分数**，不跨 frame 换算，不在矛盾时替源和解

---

## 6. 准入与优先级排序：**当前空缺，不假装拥有**

2026-10-04 曾建立 `ADMISSION_OPERATOR.v1.md`（W = F×I×G 的准入算子），
2026-10-05 **撤销**。撤销理由：其两个实现零生产消费者——机器普查确认无任何
非测试代码 import `core/kernel_operator.py` / `core/kernel_admission.py`，
只有它们自己的测试引用。

**一个只有自己测试引用的模块，注册为 L1/NORMATIVE，比没有这个规范更危险。**
这正是本文档 §3.4.1 记录 F-3 时用过的同一条判断，此处是对它自己的应用。

保留下来的：那份 18+ 处无源系数的台账，以及其中两处互相矛盾的事实，
已降级为 `00_ROOT/STATE_CALCULUS_ANNEX_MAGIC_LEDGER.md`（**REFERENCE，未登记**）。

### 6.1 因此，以下问题目前**没有**已登记规范回答

| 问题 | 现状 |
|---|---|
| 往哪个方向变？ | **本文档**，`ace.root.calculus` |
| 先做哪一件？ | **空缺。** 由既有 TaskPool 优先级与 Validator/Guardian 生命周期承担，但没有自产的算子 |
| 新评分函数是否合规？ | **空缺。** 无准入门，`core/` 下的新 `*_score` 函数可自由引入新的无源系数 |

### 6.2 补齐它需要的不是权重，是一个可数的准入依据

若日后重建准入算子，**不得**重蹈 `0.4/0.3/0.3` 的覆辙。
`PRINCIPLES.md` 公理 #019（`HISTORICAL/REFERENCE`）留有唯一的自产线索：
「意图投资组合 = 频率 × 影响 × 缺口，优先优化 Top20%」——乘法形式，
且 `Top20%` 本身被登记为**待验证参数**而非公理。
详细推导与撤销记录见附录 A。

---

## 7. 演进规则

修改基底、四段语义、frame 纪律或 `confidence` 定义，必须完成
`baseline → change → test → evaluation → compare` 并留治理收据
（沿用 `ACE_CONSTITUTION_HIERARCHY.v1.md` 演进规则）。

新增一个领域适配时，只允许新增 **frame**（含每轴 ceiling 与 scale 及其账本出处）；
**不允许新增轴、不允许改基底次序、不允许在某域偷偷用不同基底。**
如果某域确实装不进六轴，那是本演算的边界被撞到了，应记为缺口上报，
而不是给那个域开一套私有坐标系。
