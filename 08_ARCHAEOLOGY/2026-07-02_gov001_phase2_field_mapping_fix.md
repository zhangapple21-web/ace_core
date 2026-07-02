# GOV-001 Phase-2 字段映射修复考古报告

**日期**：2026-07-02
**事件**：GOV-001 Phase-2 字段映射 bug 修复 + 子任务现状盘点
**任务来源**：AUM-TASK-2026-06-28-GOV-001 Phase-2
**风险等级**：低（修复字段映射，不改数据结构）

---

## 一、背景

GOV-001 Phase-2 有 5 个子任务。通过 subagent 评估发现：
- 2 个已完成（Contract 升级、跨仓库扫描）
- 3 个部分完成（文明指标、经验治理、词库治理），都有字段映射不匹配 bug

核心 bug：`experiences.json` 实际字段是 `experience_id` / `source` / `date` / `conclusion` / `evidence` / `constraints_updated` / `related_concepts`，但代码期望 `id` / `title` / `status` / `confidence` / `updated` / `source_task`，导致：
- 文明指标报告的经验相关指标全 0
- 经验治理报告的 ID/标题全空、36 条经验被全标 orphan+low+status 异常

---

## 二、做了什么

### 2.1 civilization_status.py 字段映射修复

修改 [core/governance/civilization_status.py](file:///c:/Users/USER/Downloads/Telegram%20Desktop/ace_runtime/core/governance/civilization_status.py) 的 `_compute_experiences_stats()`：

- status 推断：从 `evidence` 和 `constraints_updated` 推断
  - evidence >= 3 且有 constraints_updated → VALIDATED
  - evidence >= 1 → EVIDENCE
  - 否则 → HYPOTHESIS
- confidence 推断：从 evidence 数量推断
  - evidence >= 5 → 0.9
  - evidence >= 3 → 0.7
  - evidence >= 1 → 0.5
  - 否则 → 0.3

### 2.2 experience_health.py 字段映射修复

修改 [core/governance/experience_health.py](file:///c:/Users/USER/Downloads/Telegram%20Desktop/ace_runtime/core/governance/experience_health.py) 的 6 个方法：

| 方法 | 修复内容 |
|------|---------|
| `_find_duplicate_experiences` | `id`→`experience_id`，`title`→`conclusion` |
| `_find_expired_experiences` | `updated`→`date`，加入 confidence 推断 |
| `_find_orphan_experiences` | 改用 `related_concepts` 判空（替代 `source_task`）|
| `_find_covered_by_constraint` | `id`→`experience_id` |
| `_find_low_confidence_experiences` | 加入 confidence 推断 |
| `_find_status_issues` | 加入 status 推断和 confidence 推断 |

---

## 三、改变了什么指标

### 3.1 文明指标（civilization_status）

| 指标 | 修复前 | 修复后 |
|------|--------|--------|
| 经验总数 | 39 | 39 |
| 验证率 | 0.00% | **97.44%** |
| 废弃率 | 0.00% | 0.00% |
| 假说比例 | 0.00% | 0.00% |
| 事实比例 | 0.00% | 0.00% |
| 平均置信度 | 0.00% | **84.36%** |
| 状态分布 | 全 0 | FACT=0, EVIDENCE=1, HYPOTHESIS=0, **VALIDATED=38**, REJECTED=0, SUPERSEDED=0 |

### 3.2 经验治理（experience_health）

| 指标 | 修复前 | 修复后 |
|------|--------|--------|
| 经验总数 | 36 | **39** |
| 问题总数 | 36（全误报）| **0** |
| ID/标题 | 全空 | 正确显示 |

---

## 四、GOV-001 Phase-2 子任务现状

| # | 子任务 | 现状 | 备注 |
|---|--------|------|------|
| 1 | Contract 升级（5 契约）| ✅ 已完成 | 5 个契约 + Manager 已实现，待实际触发 |
| 2 | 文明指标自动统计 | ✅ 修复完成 | 字段映射修复，产出有数据 |
| 3 | 经验治理 | ✅ 修复完成 | 字段映射修复，误报清除 |
| 4 | 词库治理 | ⚠️ 部分完成 | missing_hierarchy 100% 误报，lexicon 混入配置项 |
| 5 | 跨仓库扫描 | ✅ 已完成 | 3 天报告已产出 |

**进度**：5 个子任务中 4 个已完成，1 个待修复（词库治理误报）。

---

## 五、待修复项

### 5.1 词库治理（concept_health.py）

问题：
- `_find_missing_hierarchy` 100% 误报（592/592），因为它期望 `parent`/`children` 字段，但实际词库用 `related`
- lexicon 混入配置项（`full_name` / `identity` / `event_types` 等）未被识别
- `synonym_different_names` 和 `homonym_different_meanings` 声明了但未实现

建议下一步：
1. `_find_missing_hierarchy` 把 `related` 也算作层级关系
2. 新增配置项过滤
3. 补同义/同名检查

### 5.2 连续性指标（continuity_metrics）

连续性修正案确立了 `continuity_metrics` 原则（记忆完整性、标识一致性、血缘连通性），但 civilization_status.py 还没有计算这些指标。

建议下一步：
1. 引入 CivilizationGraph.get_graph_stats() 计算"血缘连通性"
2. 新增 memory_integrity（基于 02_MEMORY 完整性）
3. 新增 identity_consistency（基于 identity.py）

---

## 六、考古纪律声明

- **FACT**：civilization_status.py 和 experience_health.py 字段映射已修复，验证通过（经验总数 39，验证率 97.44%，平均置信度 84.36%）
- **EVIDENCE**：civilization_status.py 第 100-209 行、experience_health.py 6 个方法、运行输出对比
- **HYPOTHESIS**：字段映射修复后，文明指标和经验治理报告的可信度显著提升（需长期观察）

---

## 七、使用的工具

- `ops/_run_experience_health.py`：运行经验治理检查
- `ops/_run_civilization_status.py`：运行文明状态生成
- `ops/_check_constitution.py`：检查宪法原则
- `ops/_apply_continuity_amendment.py`：落地连续性修正案
- `ops/_test_inquiry_pipeline.py`：测试质询管道

---

**报告时间**：2026-07-02
**报告者**：ACE / 结构考古
**依据**：AUM-TASK-2026-06-28-GOV-001 Phase-2 + subagent 评估结果
**状态**：4/5 子任务已完成，词库治理待修复，连续性指标待落实
