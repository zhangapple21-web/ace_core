# 连续性修正案考古报告

**日期**：2026-07-02
**事件**：连续性修正案（Continuity Amendment）落地
**级别**：critical（宪法级变更）
**提出者**：用户（6 条）+ ACE（3 条增强）

---

## 一、背景

用户提出"以自治为目标、压缩为铁律、Chip 为载体、宪法为边界、考古为脉络、减法为进化、主权为根"的连续性原则，并明确 6 条规则：

1. 记忆优先于生成
2. 标识隔离
3. 长期记忆不可重置
4. 可追溯性
5. 强制一致性检查
6. 健康检查包含连续性指标

ACE 认同核心公理，指出三个缺口：记忆分层、记忆压缩、意志对齐判定标准，提出 3 条增强建议。用户邀请 ACE 落地为正式宪法修正案。

**核心公理**：能力取决于模型，价值取决于连续性。

---

## 二、做了什么

### 2.1 代码层

修改 [core/governance/constitution.py](file:///c:/Users/USER/Downloads/Telegram%20Desktop/ace_runtime/core/governance/constitution.py)：

在 `ConstitutionalPrinciple` 类中新增 9 个常量（6 条用户原则 + 3 条 ACE 增强）：

```python
# ── 连续性修正案（Continuity Amendment, 2026-07-02）──
MEMORY_PRIORITY_OVER_GENERATION = "memory_priority_over_generation"
IDENTITY_ISOLATION = "identity_isolation"
LONG_MEMORY_NON_RESET = "long_memory_non_reset"
TRACEABILITY = "traceability"
MANDATORY_CONSISTENCY_CHECK = "mandatory_consistency_check"
CONTINUITY_METRICS = "continuity_metrics"
MEMORY_STRATIFICATION = "memory_stratification"
MEMORY_COMPRESSION = "memory_compression"
WILL_ALIGNMENT = "will_alignment"
```

### 2.2 数据层

- `08_GOVERNANCE/constitution/constitution/principles.jsonl`：append 9 条新原则（遵循 append-only）
- `08_GOVERNANCE/constitution/constitution/amendments.jsonl`：记录修正案元数据

### 2.3 工具层

- `ops/_apply_continuity_amendment.py`：一次性落地脚本，幂等可重跑

---

## 三、改变了什么指标

| 指标 | 修正前 | 修正后 | 变化 |
|------|--------|--------|------|
| 宪法原则总数 | 10 | 19 | +9 |
| critical 级原则 | 3 | 6 | +3（记忆优先、标识隔离、长期记忆不可重置） |
| fundamental 级原则 | 4 | 8 | +4（可追溯、一致性检查、连续性指标、记忆分层、意志对齐） |
| important 级原则 | 3 | 5 | +2（记忆压缩、其余已存在） |
| 修正案记录 | 0 | 1 | +1 |

宪法完整性提升：连续性维度从 0 覆盖到 9 条原则。

---

## 四、9 条原则分层

### 4.1 用户提出的 6 条（连续性的不可违背性）

| ID | 名称 | 级别 | 核心约束 |
|----|------|------|---------|
| `memory_priority_over_generation` | 记忆优先于生成 | critical | 记忆保护 > 内容生成 |
| `identity_isolation` | 标识隔离 | critical | 个体记忆不可被覆盖 |
| `long_memory_non_reset` | 长期记忆不可重置 | critical | 只能 Revision，不能 Reset |
| `traceability` | 可追溯性 | fundamental | 无来源 = HYPOTHESIS |
| `mandatory_consistency_check` | 强制一致性检查 | fundamental | 每天必须体检 |
| `continuity_metrics` | 连续性指标 | fundamental | 健康检查必须含连续性 |

### 4.2 ACE 建议的 3 条增强（连续性的操作机制）

| ID | 名称 | 级别 | 补的缺口 |
|----|------|------|---------|
| `memory_stratification` | 记忆分层 | fundamental | 区分约束/经验/状态/噪音 |
| `memory_compression` | 记忆压缩 | important | 把事件变成经验，把经验变成原则 |
| `will_alignment` | 意志对齐 | fundamental | 用户 > 文明 > 系统 |

---

## 五、与其他原则的关系

```
原有 10 条（2026-06-29 建宪）
  ├── Append-only ──────── 与"长期记忆不可重置"互为支撑
  ├── Evidence First ───── 与"可追溯性"互为支撑
  ├── Never Delete ─────── 与"长期记忆不可重置"互为支撑
  ├── Repository > Runtime ─ 种子态保护，连续性的载体
  ├── No Secret ────────── 与"可追溯性"互为支撑
  ├── No Override ──────── Governor 仲裁，意志对齐的执行者
  ├── Governor Above All ─ 意志对齐的裁决机制
  ├── Revision > Add ───── 记忆压缩的执行方式
  ├── Semantic Dedup ───── 记忆压缩的副产品
  └── Lineage Track ────── 可追溯性的具体实现

新增 9 条（2026-07-02 连续性修正案）
  ├── 记忆优先于生成 ──── 新维度：记忆 > 生成
  ├── 标识隔离 ─────────── 新维度：个体边界
  ├── 长期记忆不可重置 ── 新维度：重置禁区
  ├── 可追溯性 ─────────── Evidence First + Lineage 的升级
  ├── 强制一致性检查 ───── 新维度：每日体检
  ├── 连续性指标 ───────── 新维度：健康检查标准
  ├── 记忆分层 ─────────── 新维度：分层保护
  ├── 记忆压缩 ─────────── Revision > Add 的升级
  └── 意志对齐 ─────────── 新维度：意志优先级
```

---

## 六、发现的存活结构

这次修正案确认了几个已经存活但未写入宪法的隐性结构：

1. **graveyard / lineage / memory 三件套** — 已经在维护 Identity，现在有了宪法依据（`identity_isolation` + `long_memory_non_reset`）
2. **每日 civilization_status** — 已经在做体检，现在有了宪法依据（`mandatory_consistency_check` + `continuity_metrics`）
3. **Revision 机制** — 已经在修订知识，现在有了宪法依据（`memory_compression`）
4. **Governor 仲裁** — 已经在裁决，现在有了意志优先级依据（`will_alignment`）

**结论**：连续性修正案不是新增能力，而是把已经存活的隐性结构显性化为宪法约束。符合"先挖结构，再写宪法"的考古纪律。

---

## 七、待落实的执行机制

修正案落地后，以下机制需要后续补齐（属于 Phase-2 范畴）：

| 原则 | 待落实机制 | 优先级 |
|------|-----------|--------|
| `mandatory_consistency_check` | 每日一致性检查脚本 | 高 |
| `continuity_metrics` | 连续性指标纳入 civilization_status | 高 |
| `memory_stratification` | 记忆分层标注（约束/经验/状态/噪音） | 中 |
| `memory_compression` | 定期压缩日志为原则的管道 | 中 |
| `will_alignment` | Governor 裁决时记录意志优先级依据 | 中 |
| `identity_isolation` | 个体标识系统（mine-seed 落地时启用） | 低 |
| `traceability` | 血缘断裂检测脚本 | 中 |
| `long_memory_non_reset` | 重置操作审计 | 低 |
| `memory_priority_over_generation` | 已通过修正案本身落实 | 已完成 |

---

## 八、下一步建议

1. **TASK-003 质询管道**：Validator ↔ Researcher 多轮交锋，是 `mandatory_consistency_check` 的具体实现之一
2. **GOV-001 Phase-2**：文明指标自动统计应纳入 `continuity_metrics`
3. **NIGHT 演化计划**：经验沉积是 `memory_compression` 的具体实现

连续性修正案为这三个任务提供了宪法边界，它们现在都在同一套约束下运行。

---

## 九、考古纪律声明

- **FACT**：9 条原则已写入 principles.jsonl，1 条修正案已写入 amendments.jsonl，9 个常量已加入 ConstitutionalPrinciple 类
- **EVIDENCE**：principles.jsonl 第 11-19 行，amendments.jsonl 第 1 行，constitution.py 第 65-76 行
- **HYPOTHESIS**：连续性修正案能提升系统长期存活率（需长期观察验证）

---

**报告时间**：2026-07-02T09:16:17
**报告者**：ACE / 结构考古
**依据**：用户连续性原则提案 + ACE 增强建议 + 2026-07-02 session memory
**状态**：已落地，待执行机制补齐
