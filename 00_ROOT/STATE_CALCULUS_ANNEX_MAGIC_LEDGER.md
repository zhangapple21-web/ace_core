# 附录 A — 存量魔数台账与外来算法挂号规则

> **本附录原为独立 L1 规范 `ADMISSION_OPERATOR.v1.md`（代号 KERNEL_OPERATOR），已于 2026-10-05 撤销。**
> 撤销理由：其两个实现 `core/kernel_operator.py`（W=F×I×G）与 `core/kernel_admission.py`
> **零生产消费者**——机器普查确认无任何 `core/` 或 `ops/` 非测试代码 import 它们，
> 只有它们自己的测试引用。
>
> **一个只有自己测试引用的模块，注册为 L1/NORMATIVE 规范，比没有这个规范更危险**：
> 它让系统看起来已经拥有一套准入算子，而实际上没有任何决策在用它。
> 这条判断本身写在 `STATE_CALCULUS.v1.md` §3.4.1（F-3 修订），此处是它对自己的应用。
>
> **保留原因**：台账内容有真实价值——它记录了 ACE 现存 18+ 处无源系数，
> 以及其中两处互相矛盾的事实。这是可执行的债务清单，不能跟着死代码一起删掉。
>
> **状态**：`REFERENCE`。本附录**不授予任何权威，不被 `constitution_registry()` 登记**，
> 不得据此改动任何生产行为。台账的归约须走既有 Admission → Validator → Guardian。

---

## A. 出处与谱系（保留：`00_ROOT/PRINCIPLES.md` 的相空间克制）


| 来源 | 层级/状态 | 说明 |
|---|---|---|
| `00_ROOT/PRINCIPLES.md:406-414` 公理 #019 | `HISTORICAL/REFERENCE` | 「老板设计：意图投资组合=频率×影响×缺口」+ 四处矿场映射 |
| `00_ROOT/PRINCIPLES.md:202-210` 公理 #009 | `HISTORICAL/REFERENCE` | 「R1是全局相空间调节律」「**约束不是规则，是相空间中的吸引子**」 |
| 本文档 | `L1/NORMATIVE/CURRENT` | 把 #019 升格为当前唯一算子，并给出可执行口径 |

**关于「相空间」的边界声明**：#009 使用了相空间语言，但**从未**声称坐标、权重或维度矩阵。
本算子**继承这一克制**：只声称「吸引力来自账本事实」，不声称坐标系、维度或权重空间。
R1 的 `reality_weight_matrix.json` / 六维坐标权重属 `EXTERNAL_REFERENCE`，
**不构成本系统的算子来源**，详见 `08_ARCHAEOLOGY/2026-10-04_CROSS_REPO_SOUL_SURVEY_v1.md` §4.3。

---

---

## B. 外来算法的唯一合法形态：FOREIGN LENS（保留为登记要求）


外来算法（ROS TF tree、Autoware 加权融合、Raft 共识等）**可以借用，但必须挂号**。

一个新增 `*_score` / `*_priority` / 排序函数，必须二选一：

1. **归约为 W = F × I × G** —— 三个因子都要能指回已登记账本的条目；
2. **声明为 FOREIGN LENS** —— 必须提供：
   - `source`：借自何处（系统、论文、标准或仓库 + 提交号）
   - `scope`：只在什么条件下成立
   - `expires_at`：何时必须重新评估
   - `why_not_kernel`：为什么不归约到 W

未归约、未挂号的新评分函数 = **准入阻断**（`KERNEL_ADMISSION_BLOCKED`）。

**这就是「始终属于自己内部」的准确含义：内核自产，外来受管。**
不是拒绝借，而是拒绝**偷偷借**。

---

---

## C. 存量魔数台账（冻结中，不改行为）


以下 18+ 处按本轮决策 **冻结**：登记不改写、不声称归约、不改生产行为。
新建功能受第 4 节约束；存量归约需走既有 Admission → Validator → Guardian 生命周期。

| # | 位置 | 现状 | 状态 |
|---|---|---|---|
| 1 | `core/governance/daily_civilization_report.py:964` | `fitness×0.4+pass_rate×0.3+knowledge×0.3` | `FROZEN_MAGIC` |
| 2 | `core/governance/civilization_status.py:404` | `degree×0.6+ratio×0.4` | `FROZEN_MAGIC` |
| 3 | `core/stock_data_reliability.py:1088` | `0.30/0.20/0.15/0.20/0.15` 五项 | `FROZEN_MAGIC` |
| 4 | `core/research_pipeline.py:162` | `0.40/0.35/0.25` | `FROZEN_MAGIC` |
| 5 | `core/research_pipeline.py:176` | `0.45/0.35/0.20` | `FROZEN_MAGIC` |
| 6 | `core/research_pipeline.py:190` | `0.35/0.35/0.30` | `FROZEN_MAGIC` |
| 7 | `core/task_roles.py:1665` | `0.40/0.35/0.25` | `FROZEN_MAGIC_CONFLICTS_WITH_1` |
| 8 | `core/value_scorer.py:123` | `novelty×0.3+…` | `FROZEN_MAGIC_CONFLICTS_WITH_7` |
| 9 | `core/governance/governor_protocol.py:633/657/661` | `0.2/0.4/0.2` | `FROZEN_MAGIC` |
| 10 | `core/slice_clusterer.py:158` | `count×0.5+chars×0.3` | `FROZEN_MAGIC` |
| 11 | `core/governance/knowledge_evolution.py:900/911/933/934` | `0.1/0.05/0.05/0.02` | `FROZEN_MAGIC` |
| 12 | `core/governance/knowledge_status.py:96` | `evidence×0.05` cap0.4 | `FROZEN_MAGIC` |
| 13 | `core/governance/stable_kernel.py:621` | `gap×0.5` | `FROZEN_MAGIC` |
| 14 | `core/local_miner.py:384/386` | `0.3` / `0.7` | `FROZEN_MAGIC` |
| 15 | `core/governance/mengpo.py:189/204` | `0.2/0.01/0.3` | `FROZEN_MAGIC` |
| 16 | `core/governance/entropy_monitor.py:344` | `conflict×0.5` | `FROZEN_MAGIC` |
| 17 | `core/hindsight_memory_adapter.py:221` | `overlap×0.5` | `FROZEN_MAGIC` |
| 18 | `core/companion/desktop_pet.py:154` | `0.15−i×0.04` | `FROZEN_MAGIC` |

**冲突登记项 C-7**：`#7` 与 `#8` 对新颖性权重给出相反判断（0.4 vs 0.3 且互补性主导）。
按 `ACE_CONSTITUTION_HIERARCHY.v1.md` 冲突裁决第 4 条，此项保持 `NEEDS_REVIEW`，
**不得**由时间、文件名或「看起来更合理」静默选择。

---

---

## D. 撤销记录

| 时间 | 事件 |
|---|---|
| 2026-10-04 | 建立为 `KERNEL_OPERATOR.v1.md`，登记 `ace.kernel.operator`（L1/NORMATIVE/CURRENT） |
| 2026-10-04 | 用户纠正方向：内核应是跨域坐标演算，不是准入分诊算子 → 文件改名 `ADMISSION_OPERATOR.v1.md`，登记项改为 `ace.admission.operator` |
| 2026-10-05 | 全面自审：机器普查确认两个实现零生产消费者 → 撤销登记，规范降级为本附录，删除死代码 |

**撤销不是否定历史。** 上面每一行都保留，因为「曾经声称有、后来发现自己没有」
本身就是这条系统最该记住的一课。
