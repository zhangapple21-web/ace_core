# 连续性指标落地考古报告

**日期**：2026-07-02
**事件**：连续性指标从宪法原则落地为可观测指标
**任务来源**：连续性修正案 continuity_metrics 原则
**风险等级**：低（只读计算，不修改数据）

---

## 一、背景

连续性修正案写入宪法后，`continuity_metrics` 原则（记忆完整性、标识一致性、血缘连通性）只存在于宪法声明中，未在 civilization_status 中作为可观测指标计算。

**核心问题**：灵魂层的原则如果没有身体层的指标来度量，就等于不存在。

---

## 二、做了什么

在 [core/governance/civilization_status.py](file:///c:/Users/USER/Downloads/Telegram%20Desktop/ace_runtime/core/governance/civilization_status.py) 中新增 5 个方法 + 1 个 Markdown 章节：

| 方法 | 作用 |
|------|------|
| `_compute_continuity_metrics()` | 主方法，聚合三个子指标 |
| `_compute_lineage_connectivity()` | 血缘连通性计算 |
| `_compute_memory_integrity()` | 记忆完整性计算 |
| `_compute_identity_consistency()` | 标识一致性计算 |
| `_human_readable_size()` | 字节数格式化辅助 |
| `_generate_continuity_section()` | Markdown "七、连续性指标"章节 |

### 三个连续性指标

#### 1. 血缘连通性（Lineage Connectivity）
- **数据源**：优先 `CivilizationGraph.get_graph_stats()`，不可用时降级为词库 `related` 关系统计
- **计算方式**：有关系的概念数 / 总概念数
- **当前值**：**92.56%**（1169 概念中 1082 个有关联）
- **宪法依据**：`traceability`（可追溯性）+ `lineage_track`（血缘追踪）

#### 2. 记忆完整性（Memory Integrity）
- **数据源**：`02_MEMORY/` 目录
- **计算方式**：基础分(0.3) + 文件数量分(对数缩放, 最高 0.4) + 索引加分(0.3)
- **当前值**：**100.00%**（269 个文件 / 6.65 MB / 有索引）
- **宪法依据**：`long_memory_non_reset`（长期记忆不可重置）+ `never_delete`（永不删除）

#### 3. 标识一致性（Identity Consistency）
- **数据源**：依次查找 `02_MEMORY/identity.json` → `01_CORE/identity.json` → `identity.json`
- **检查项**：唯一 ID、创建时间、名称（每个字段多个别名兼容）
- **计算方式**：通过检查项 / 总检查项
- **当前值**：**0.00%**（`01_CORE/identity.json` 存在但为空对象 `{}`）
- **宪法依据**：`identity_isolation`（标识隔离）

### 综合连续性得分

**64.19%**（三指标等权平均）

---

## 三、设计决策

### 3.1 所有指标都有降级路径

| 指标 | 首选数据源 | 降级路径 |
|------|-----------|---------|
| 血缘连通性 | CivilizationGraph | 词库 related 统计 |
| 记忆完整性 | 02_MEMORY + 索引 | 只有文件数 |
| 标识一致性 | identity.json | 返回 0 分 |

**理由**：笨但稳定。数据源缺失时降级，不报错。

### 3.2 所有得分都是 0~1 浮点数

方便归一化、加权、趋势分析。

### 3.3 只改一个文件

所有实现都在 civilization_status.py 中，不新增模块。

### 3.4 不为了数字好看而造假数据

标识一致性 0% 是真实发现——`01_CORE/identity.json` 确实是空的。系统有 Identity 类（从 00_ROOT/PRINCIPLES.md 动态加载），但 identity.json 作为静态身份锚点确实是空的。

**判断**：不手动修复 identity.json。理由：
1. 身份锚点应该由 Identity 类自己维护，不是手动填的
2. 0% 的指标更有价值——它指出了一个真实的 gap
3. 系统后续可以通过 self_healing 机制自己补

---

## 四、发现的问题

### 4.1 标识一致性 0%

**问题**：`01_CORE/identity.json` 是空对象 `{}`

**根因**：Identity 类从 `00_ROOT/PRINCIPLES.md` + `ace_config.json` 动态加载身份，不往 `identity.json` 写入。`identity.json` 是预留的静态锚点，但从未被填充。

**影响**：连续性指标中的标识一致性项为 0，拉低综合得分。

**建议**：后续在 Identity 类中增加 `_ensure_identity_anchor()` 方法，在初始化时如果 identity.json 为空，自动从现有数据源生成并写入。属于 self_healing 范畴。

### 4.2 血缘连通性用的是降级模式

**问题**：当前用的是词库 related 统计，不是 CivilizationGraph。

**根因**：CivilizationGraph 需要更完整的图数据，当前可能初始化不完整。

**影响**：血缘连通性只反映词库层面，不反映跨模块（经验-概念-约束-协议）的血缘关系。

**建议**：后续接入完整的 CivilizationGraph，计算跨模块连通性。

---

## 五、改变了什么指标

| 指标 | 落地前 | 落地后 |
|------|--------|--------|
| 连续性指标 | 0 个（只有宪法声明）| **3 个 + 1 个综合得分** |
| civilization_status 章节 | 6 个 | **7 个**（新增"七、连续性指标"） |
| 可观测的宪法原则比例 | 低 | 提升（continuity_metrics 从声明变为可度量）|

---

## 六、与其他系统的关系

```
宪法层（principles.jsonl）
  ├── continuity_metrics ← 本任务将其落地为可观测指标
  ├── memory_priority_over_generation
  ├── identity_isolation  ← 标识一致性是它的度量
  ├── long_memory_non_reset ← 记忆完整性是它的度量
  └── traceability        ← 血缘连通性是它的度量

身体层（civilization_status.py）
  ├── 一、知识总量
  ├── 二、状态分布
  ├── 三、词库健康
  ├── 四、演化统计
  ├── 五、假设库
  ├── 六、趋势分析
  └── 七、连续性指标 ← 新增
       ├── 血缘连通性
       ├── 记忆完整性
       └── 标识一致性
```

---

## 七、考古纪律声明

- **FACT**：连续性指标已实现，三个子指标 + 综合得分已加入 civilization_status，Markdown 章节已生成
- **EVIDENCE**：civilization_status.py 第 323-636 行（计算）+ 第 1154 行起（Markdown），运行验证输出：血缘 92.56% / 记忆 100% / 标识 0% / 综合 64.19%
- **HYPOTHESIS**：连续性指标能帮助系统发现退化点，提升长期存活率（需长期观察）

---

## 八、下一步

1. **Identity 自修复**：Identity 类增加 identity.json 锚点自动生成（self_healing 范畴）
2. **CivilizationGraph 接入**：血缘连通性从降级模式升级为完整图计算
3. **连续性告警**：综合得分低于阈值时触发告警
4. **趋势追踪**：连续性指标纳入趋势分析（当前已有趋势模块，需补充连续性指标的历史提取）

---

**报告时间**：2026-07-02
**报告者**：ACE / 结构考古
**依据**：连续性修正案 continuity_metrics 原则 + civilization_status.py 现有框架
**状态**：已落地，标识一致性 0% 待系统自修复
