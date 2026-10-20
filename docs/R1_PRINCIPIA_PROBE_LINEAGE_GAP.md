# R1 原理 × Free-Zone 探针谱系：缺口对齐与下一步挖掘目标

**文档类型**：分析交付（Candidate）。**不构成**任何生产变更、准入、经验采纳或推荐授权。
**编制日期**：2026-10-04
**上游依据**：`docs/R1_PRINCIPIA_TO_ACE_MAP.md`
（sha256 `7ee2765b3193ded4dc2adf25de5ca46628f42e27db4730d9666677ed7f847fa2`，13654 bytes，
完整性已复算一致；产出任务 `RQ-20261003-005` → `RQ-20261003-012`）
**本次目的**：把那份映射**落到 free-zone 探针链路这一层**，得出"仍缺失的 R1 结构"，
从而指明下一步该挖什么 —— 而不是把原典重新考古一遍。

---

## 0. 边界与认识论状态

| 项 | 状态 |
|---|---|
| 本文档性质 | `PROPOSAL_ONLY` 分析。未创建 Task、未调用模型、未改生产运行时、未触碰 TaskPool。 |
| 上游映射地位 | 产出任务 `RQ-20261003-012` 已 `archived`，但 `guardian_decision = "experience"`、**未升格**（`promoted: false`）；`learning_return = NOT_APPLICABLE / no_learning_source`；`delivery_protocol_checks.errors = ["responsibility:responsibility_learning_return_missing"]`；Validator 反对意见："未主动寻找反例，存在确认偏误风险"。 |
| 因此 | 该映射可作为**候选参考**使用，**不能**当作已受理的公理层结论直接继承。本文档对其的每一处修正都保留原判定的可追溯性，不覆盖原文件。 |
| 双叶边界 | Free Zone 与 ACE reality 是两个不可互相替代的叶子。本文档只描述 free-zone 侧的**结构事实**与**缺失结构**，不主张任何一侧的结论自动驱动另一侧的运行时。 |
| 失败即食物 | 下列缺口若被证明为误判，按 #021（贡献不可回收）与 #010（只增结构）保留为已披露反例，不删除。 |

**引用约定**：所有 `文件:行号` 均可在当前 checkout 直接复核。凡本文未给出可复核引用的判断，
一律标记 `HYPOTHESIS`，不升格为事实。

---

## 1. 探针链路实测现状（2026-10-04）

先量清链路本身，再谈缺口。以下均为目录实测计数，非推断。

```text
inbound food
  └─ factory threads                                    88
       └─ factory worlds                                176   (88 COUNTEREXAMPLE_SEARCH + 88 DIRECT_OBSERVATION)
            └─ experiments / distillations               70
                 └─ lazy_cat verdicts                    70
                      ├─ 55 FIT_FOR_TEACHER_REVIEW
                      ├─ 15 RETURN_TO_FREE_ZONE   → 产生 challenge
                      └─  0 OPEN_CHALLENGE_RETAINED
                 └─ promotion_proposals                 43   (全部 PROPOSAL_ONLY, executable=false)
       └─ challenges                                     15
            └─ challenge probes                          20   (attempt1×15, attempt2×5)
                 ├─ 15 PROBE_COMPLETED_WITHIN_SCOPE  (witness NOT_FALSIFIED_WITHIN_SCOPE)
                 └─  5 NEEDS_ANOTHER_PROBE           (legacy 回填, witness=null)
  └─ free_zone_bridge feedback                           15   (全部 epistemic_status=UNKNOWN / HOLD_FOR_EVIDENCE)
  └─ free_zone_exchange receipts                          4   (全部 source=ACE → dest=FREE_ZONE)
  └─ free_zone_bridge receipts                            6
  └─ task_pool_freezone pending                           3   (RQ-20261003-001/002/003)
```

关键结构事实：

1. **176 个 world 的 `execution_state` 全部是 `BLUEPRINT_ONLY`**（0 个被执行）。
   world 文件自带方法声明：`"Preserve this rival world for a dedicated counterexample
   executor; do not infer a result merely because it has not run."`
   （`07_SANDBOX/free_research/factories/worlds/WORLD-THREAD-02AF7DD857DA7978-COUNTEREXAMPLE_SEARCH.json:6`）
2. **43 个 promotion proposal 全部 `PROPOSAL_ONLY`**，`executable: false`，
   `requires: [human_confirmation, existing_admission, existing_validator]`，
   `prohibited_actions: [automatic_production_write, automatic_task_creation, automatic_delivery, automatic_order]`。
   零个被执行。
3. **15 条 feedback 全部 `epistemic_status: UNKNOWN` / `ace_review.decision: HOLD_FOR_EVIDENCE`**。
4. **4 条 exchange receipt 全部单向**：`source_realm → destination_realm = FREE_ZONE`，
   `status = RELEASED_TO_FREE_ZONE`。返回腿（Free Zone → 外部/物理）为零。

---

## 2. 先修正映射本身，否则会把错的公理对错的层

映射的立意可用，但**不能机械套用**。三处必须先修正。

### 2.1 编号命名空间冲突 —— 必须按名称对齐，不能按编号

`00_ROOT/PRINCIPLES.md` 存在两套编号：正文散文块（第 6–22 行的"馆长负责连续性。五界负责分类世界。…"）
与显式编号公理（`新增公理 #003`–`#021`）。映射的 §一 自称覆盖 `Principles #001-#020`，
但它把**散文块顺序**当成了编号公理号，与文件实际编号大面积错位：

| 映射中的编号与内容 | `PRINCIPLES.md` 实际同号公理 | 后果 |
|---|---|---|
| #007 关系高于实体 | #007 数据最小化+本地优先（:148） | 若按号对齐，探针链会被判成"数据最小化"议题 |
| #008 记忆高于数据 | #008 认知主循环——感知→重构→锚定→输出（:186） | **认知主循环恰是探针链路的核心结构**，被完全漏掉 |
| #011 决策必须可解释 | #011 记忆是推断的不是存储的（:228） | |
| #012 平台可换 | #012 内外双域隔离（:242） | 双域隔离才是探针链的边界公理 |
| #018 五界为壳非为牢 | #018 拆壳不拆骨——安全约束可调，核心不变量不可删（:362） | |
| #019 数据最小化+本地优先 | #019 意图投资组合——Top20%（:406） | |

文件的权威编号范围是 `#001-#007 及以后`（:222），公理总数 21 条（:694）。
映射里只有 `#021 贡献不可回收` 恰好对上真号，且它只出现在恢复建议表，从未进入公理表。

> **处置**：本文一律**按公理名称**对齐，并在括号内给出真实文件编号与行号。

### 2.2 覆盖缺口 —— #021 未被分析，#022 完全缺席

映射 §一 自称覆盖 `#001-#020`，**从未分析 #021 贡献不可回收**（:503），
**完全未提 #022 工作守恒——工作来自发现，而不是为了活跃度而制造**（:573）。
#022 是 `FROZEN_CONSOLIDATED_PRINCIPLE`（不新增 L0 公理，故不列入公理表可以接受），
但对"一条自我喂养的探针环路"而言，它是**最具约束力的那一条**，缺失即为分析缺口。

### 2.3 极性倒置 —— "应退役"实际意思是"ACE 从未接入"

映射 §4.1/§4.2 把 R1 的原则标成"**应退役**"，但备注内容描述的是 **ACE 的缺失**
（"真正的外部输入未建立持续接入路径""未建立数字产物到物理世界的桥接机制"）。
退役是 ACE 对该原则的处置，不是该原则本身的属性。这个倒置造成一个**实质危害**：

> 映射把 **关系高于实体** 判为"应退役"。而 §4 的证据显示，探针链路缺的恰恰就是它 ——
> 一条没有对立世界的探针链只是队列，不是关系网。
> **机械套用这份映射，会建议退役探针链唯一真正缺的那条 R1 原则。**

（另注：映射正文存在重复损坏文本，如 :55 "承承承承承承继承"、:120 "承承承承"，
不影响结构判定，但说明该文本未经过逐字校对；其生命周期未升格，见 §0。）

---

## 3. 按名称对齐：R1 结构 × 探针链路

| R1 结构（真实编号/名称） | 探针链路现状 | 判定 | 证据 |
|---|---|---|---|
| **五界为壳非为牢**（#006，:139） | 壳未成牢，但也未成门：43 个 proposal 全部 `executable:false` + 需人工确认。壳是实的、可穿透的门不存在 | **异化** | `promotion_proposals/EXP-20260924103205317689-*.json:8-22` |
| **认知主循环 感知→重构→锚定→输出**（#008，:186） | 有 感知/重构/锚定，**输出环节止步于 sandbox verdict**。映射 §4.2 已判"应退役"（应为"缺失"） | **缺失** | `distillations/*.json` 全部 `status ∈ {PROPOSAL_ONLY, OPEN_QUESTION, COUNTEREXAMPLE_ONLY}` |
| **内外双域隔离**（#012，:242） | 内网（free-zone）自由成立；外网回程为**零**。降敏词表被用作输出过滤而非"内→外翻译层" | **半延续** | 4/4 exchange receipt `destination_realm=FREE_ZONE` |
| **记忆是推断的不是存储的**（#011，:228） | 探针链全链 hash 绑定（record/distillation/proposal/probe/witness 五层 hash） | **延续** | `core/lazy_cat_audit.py:221`、`core/counterexample_executor.py:27-33,50-51` |
| **拆壳不拆骨**（#018，:362） | 骨（`production_integration:false`、`automatic_*` 全 false）守住了；壳（可调约束）从未被拆过 | **半延续** | `core/lazy_cat_audit.py:224`；无任何可调约束记录 |
| **关系高于实体**（散文块 :11，无编号公理） | **缺失，且是核心缺口**。176/176 world 停在 `BLUEPRINT_ONLY`；0 个对立世界被执行 | **缺失** | 见 §4.1 |
| **贡献不可回收**（#021，:503） | challenge / probe 全部 append-only、hash 签名、只增不删；5 组重试以**同 challenge_id 递增 attempt** 承接 | **延续** | `core/lazy_cat_audit.py:139-172` |
| **工作守恒**（#022，:573） | 环路自我供养：`verdict→challenge→probe→verdict`。**无准入测试**区分"新发现的工作"与"对同一结构缺口的重复再处理" | **缺失（无闸门）** | 见 §4.6 |
| **五工厂物质链 / courier**（`docs/ACE_R1_ECOLOGY_REINSTATEMENT_002.md:75-83`） | recovery/marking/imitation/processing 存在；**courier（对外返回回执）零实现** | **四缺一** | 见 §4.4 |
| **Court：仅验完整性，不批准采纳**（同文档 :36,:82） | 完整性校验存在，但由 LazyCatAuditor **自查输入**完成，非独立 edge court | **异化** | `core/lazy_cat_audit.py:215-252` |

---

## 4. 仍缺失的 R1 结构（按挖掘价值排序）

### 4.1 【首要】dissent 执行体 —— 探针链的闭环靠"未执行"来证明自己

**这是下一步唯一真正该挖的东西。**

链路现状是一个**自我认证的闭环**：

```text
core/counterexample_executor.py:75
  "dissent_blueprint": bool(counter_world.get("world_id"))
                        and counter_world.get("execution_state") == "BLUEPRINT_ONLY"
```

也就是说，`dissent_blueprint`（异议蓝图）这一维度的"通过"条件是
**对立世界存在且从未被执行**。而实测 176/176 个 world 恒为 `BLUEPRINT_ONLY`，
因此该检查**在结构上不可能为假**。由此：

1. `witness_outcome` 恒为 `NOT_FALSIFIED_WITHIN_SCOPE`（`core/counterexample_executor.py:90`）；
2. `state` 恒为 `PROBE_COMPLETED_WITHIN_SCOPE`（`core/lazy_cat_audit.py:147-148`）；
3. `pending_challenges()` 恒清空（`core/lazy_cat_audit.py:108-109`）；
4. 于是 15/15 个 challenge 全部"完成"，而**没有任何一个异议世界真正跑过**。

而 `docs/ACE_R1_ECOLOGY_REINSTATEMENT_002.md:85-87` 自己写明：`BLUEPRINT_ONLY` 是
**刻意**的，"until a dedicated executor exists"。`:126-130` 又把
"specialized experiment executors" 列为 *deliberately unfinished work*。

> **缺口定性**：探针链路唯一的成功判据，被系统自己声明为"尚未完成"的那个条件所满足。
> 链路在形式上闭合，在异议层零进展。这不是"缺一个功能"，是**判据与缺口定义重合**。

**为什么它是缺口而非细节**：R1 的 `关系高于实体`（:11）与五工厂的 imitation factory
要求"存在一个与原结论竞争的对立世界"。当前实现里对立世界恒不运行，
探针链因此只是一条**串行队列**：verdict → challenge → probe → verdict。
没有对立世界，就没有关系，只有排队。

**证伪条件**：若能证明存在某个 `execution_state != BLUEPRINT_ONLY` 的 world 曾产生过
一次真实的 FALSIFIED，并被 `COUNTEREXAMPLE_OBSERVED` 消费
（`core/lazy_cat_audit.py:145-146` 该分支从未在实测数据中出现过），则本条降级为 `HYPOTHESIS`。

### 4.2 同一维度存在两个互不相容的定义

同一个维度名 `dissent_blueprint`，两个权威给出不同判据：

| 权威 | 定义 | 对实测数据的结论 |
|---|---|---|
| `core/counterexample_executor.py:75` | `world_id` 存在 **且** `execution_state == BLUEPRINT_ONLY` | **通过** |
| `core/lazy_cat_audit.py:225` | `metadata.factory_thread_id` **且** `metadata.factory_world_id` 存在 | **失败**（原始实验无此字段） |

实测两者确实分叉：原始实验 `EXP-20260827052215350123-FREEZONE-8BFD6A6BA69E`
的 metadata 无 `factory_*` 字段 → 被判 `RETURN_TO_FREE_ZONE`，`missing=['dissent_blueprint']`；
而其探针实验 `EXP-20260827061740144078-FREEZONE-278E878EC944`
的 metadata 有 `factory_thread_id`/`factory_world_id` → 执行器判"已证明"。

后果：**链路在更宽松的那个权威上结案。** 任何未来的 dissent 执行体，其产物都会被两套规则同时评分。
这属于 R1 #020（每次变更必须有 diff 和原因）与 #010（只增结构不破坏不变量）的辖区：
同一维度名不得承载两套不兼容语义。

### 4.3 审计纪元缺失 —— 判据演进后，旧裁决永不重审

`core/lazy_cat_audit.py:68-69`：

```python
path = self.verdicts / f"{experiment_id}.json"
if path.exists():
    continue
```

裁决**只写一次，永不重审**。而 `counterexample_witness` 这一检查维度的加入
发生在 2026-08-27 06:17 与 06:20 之间（由 `core/lazy_cat_audit.py:229-245` 现状可反推）。
实测有 **5 条 challenge 源裁决的 `checks` 里根本没有 `counterexample_witness` 键**，
却全部判为 `FIT_FOR_TEACHER_REVIEW`：

```text
2026-08-27T06:03:26  EXP-20260827060326004360-FREEZONE-A4F1993C0D17
2026-08-27T06:03:26  EXP-20260827060326024072-FREEZONE-F967AB004262
2026-08-27T06:17:40  EXP-20260827061740144078-FREEZONE-278E878EC944
2026-08-27T06:20:22  EXP-20260827062022129950-FREEZONE-F24A228DD489
2026-08-27T06:20:22  EXP-20260827062022148479-FREEZONE-2AF317763217
```

以今天的代码重算 `EXP-20260827061740144078-FREEZONE-278E878EC944`：
其 evidence 无 `counterexample_witness` → `checks['counterexample_witness'] = False`
→ `missing` 非空 → `source_kind == "lazy_cat_challenge"`
→ 应得 **`OPEN_CHALLENGE_RETAINED`**（`core/lazy_cat_audit.py:249-250`），而非 `FIT_FOR_TEACHER_REVIEW`。

系统确实**察觉**了这 5 条：它们正是 5 组 attempt-2 重探的对象。
但补偿手段是**再跑一次探针**，不是**审计纪元 + 取代回执**。
于是那 5 条旧裁决至今留在盘上，`missing: []`、无 `superseded_by`、无规则集哈希 ——
对任何下游读者而言与现行有效裁决**不可区分**。

**缺口定性**：R1 #020 要求"每次变更必须有 diff 和原因"。此处缺的不是 diff，
是**"这条裁决是按哪一版判据、是否已被取代"的可追溯字段**。
`OPEN_CHALLENGE_RETAINED` 实测 0 次命中，部分原因即在此：它是唯一会暴露判据不足的状态，
却被写一次的裁决存储永久冻结。

### 4.4 courier 返回腿不存在

R1 五工厂链条的 courier = "public-only external return receipt"
（`docs/ACE_R1_ECOLOGY_REINSTATEMENT_002.md:80`）。实测：

- 4/4 exchange receipt 单向：`source_realm` 未标外部，`destination_realm = FREE_ZONE`，
  `status = RELEASED_TO_FREE_ZONE`；
- 15/15 feedback `epistemic_status = UNKNOWN`；
- 43/43 proposal `PROPOSAL_ONLY`，`reason = human_and_governed_review_required`。

入站腿（ACE → Free Zone）已建成并有独立证据组（`daemon_state` / `task_lifecycle_report`
双组 sha256 绑定）。**出站腿为零。**
映射 §4.2 在系统层已判此为"应退役"（应作"缺失"），本节在探针链层予以确认。
对应 R1 #012 的"降敏词表 = 内→外翻译层"（:250）——ACE 把它用成了内→内过滤。

**边界提醒**：补这一条不等于授权对外发布。#012 的外网定义是"只展示、加密、签名、受控、合规"，
本缺口只主张**通道缺位**，不主张放宽任何边界。

### 4.5 Court 未独立于 Auditor

R1 Court 的定义是**事后**完整性验证，且不批准采纳
（`ACE_R1_ECOLOGY_REINSATEMENT_002.md:36,:82`）。
当前 `LazyCatAudit._assess`（`core/lazy_cat_audit.py:215-252`）由审计者读取自己上游的
record 与 distillation 并直接出裁决 —— 完整性检查与被检查对象共用同一执行体。
映射 §4.2 判 Court 在 ACE 中"角色定位模糊/异化"，此为该判断在探针链层的具体落点。

### 4.6 #022 工作守恒闸门缺失

`00_ROOT/PRINCIPLES.md:573-598` 明确："工作来自发现，而不是为了制造。"
并要求：连续三个已完成、彼此独立的 Discovery Window 无 Candidate 时记
`INVESTIGATE_DISCOVERY_CHAIN`，**且该诊断不是自动创建 Task 或调用模型的配额**。

探针环路是 `verdict → challenge → probe → verdict` 的自我供养结构。
`dissent_blueprint` 在 15/15 个 `RETURN_TO_FREE_ZONE` 裁决中重复出现
（其中 10 条缺 `dissent_blueprint` 单项、5 条缺 `boundary_intact+dissent_blueprint`）。
系统已有一个防塌缩机制（`core/free_zone_semantic_exploration.py:44` 把
`dissent_blueprint` 保留为独立语义切片，避免不同修复问题被静默合并），
但**没有 #022 意义上的准入闸门**去区分：

- 新发现的缺口（合法 Work），与
- 同一结构签名在新实验上的重复再处理（自身产物的回声）。

在 dissent 执行体缺位（§4.1）的前提下，后者是当前主要成分。

---

## 5. 明确**不要**再挖的部分（避免重复考古）

以下已被现有资产覆盖，重做即违反 Find Before Build：

| 已覆盖 | 资产 |
|---|---|
| R1 公理逐条映射（系统层） | `docs/R1_PRINCIPIA_TO_ACE_MAP.md`（本文只做探针链层的细化与修正，不重做全量对照） |
| free-zone 食物链与角色重定位 | `docs/ACE_R1_ECOLOGY_REINSTATEMENT_002.md`（:13-51） |
| 五工厂关系链的落盘表示 | `07_SANDBOX/free_research/factories/`（88 threads / 176 worlds） |
| 显式 realm bridge 与受理流程 | `08_GOVERNANCE/free_zone_bridge/` + `acceptance/ECO-02_EXPLICIT_REALM_BRIDGE.md` |
| ACE→Free Zone 缺口投放 | `08_GOVERNANCE/free_zone_exchange/receipts/`（4 条，双证据组） |
| 双叶边界的运行时强制 | `core/free_zone_reality_bridge.py`、`SANDBOX_MANIFEST.json`、`forbidden_targets` |
| 探针记录层的 append-only 与 hash 链 | `core/lazy_cat_audit.py`、`counterexample_executor.py`（#021 已延续） |

---

## 6. 下一步该挖的一个目标

> **目标（`PROPOSAL_ONLY`）**：为 free-zone 探针链路补一个 **dissent 执行体的契约与判据归属**，
> 使 `dissent_blueprint` 不再以"对立世界未运行"为通过条件，并使每个审计维度**只有一个权威定义**。

范围严格限定为**契约与判定层**，不含实现：

1. **单一定义归属** —— `dissent_blueprint` 只保留一处定义；另一处改为引用（§4.2）。
2. **让诚实失败可达** —— 当不存在可运行的对立世界时，判据应能产出
   `OPEN_CHALLENGE_RETAINED`，而不是恒真通过（§4.1）。
   注意 `core/lazy_cat_audit.py:276-277` 现状：`OPEN_CHALLENGE_RETAINED` 不产生 challenge，
   因此它同时是一个**死端**；纠正时须同时保证诚实失败**仍可被后续探针接力**。
3. **审计纪元 + 取代回执** —— 裁决记录判据集标识与 `superseded_by`，
   使规则集演进可被重审而不改写历史（§4.3，对应 #020 / #010）。
4. **#022 准入闸门** —— 挑战再生成前，判定其是否为真实新发现（§4.6）。

**验证方式**：聚焦契约测试（当前 `ops/test_free_zone_semantic_exploration.py`
与 `ops/test_free_zone_reality_bridge.py` 已提供邻近回归面），
外加一条**否定性**检验：构造一个无对立世界的输入，断言判据**不得**通过。
不接受"新增字段且既有测试仍绿"作为完成证据。

**明确不在范围内**：不新建 dissent 执行器、不建第二套调度/队列/运行时、
不改任何 `production_integration` 边界、不触碰 TaskPool、不授权对外返回。

**风险**：中。低风险的正确做法是先只做契约层并让"诚实失败"路径在测试中真实可达；
一旦触碰 `core/lazy_cat_audit.py:68-69` 的写一次语义或既有 verdict 文件，需先声明
不可回退范围（当前无自动迁移路径，见 §7-U3）。

---

## 7. 未知与未证明（不得当作已解决）

- **U1**：`OPEN_CHALLENGE_RETAINED` 的 0 次命中，究竟主要源于"判据恒真"（§4.1）
  还是"challenge 源裁决被写一次冻结"（§4.3）？两者都成立但未做因果分离实验。
  本文按代码路径判定**两者同时成立**，未排序。
- **U2**：`dissent_blueprint` 的两个定义是否**有意**分工（执行器判"能否证明"、
  审计器判"是否已挂载"）？若是有意，则 §4.2 应改判为"命名缺陷"而非"语义冲突"。
  当前无设计文档可证（`HYPOTHESIS`）。
- **U3**：裁决写一次语义（`core/lazy_cat_audit.py:68-69`）没有迁移路径。
  若将来要引入审计纪元，5 条陈旧裁决如何处理尚无既定契约；本文不提议改写它们。
- **U4**：43 个 proposal 全部停在 `PROPOSAL_ONLY` 是否符合设计意图，抑或受理侧未被接线，
  需 `08_GOVERNANCE` 的受理证据才能判定。当前证据两侧都不足，**不下结论**。
- **U5**：本文全部计数取自目录枚举，未与 daemon 运行态快照交叉核对；
  若两者不一致，以运行态为准并重算。
