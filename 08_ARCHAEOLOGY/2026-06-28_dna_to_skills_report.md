# DNA → 技能自动沉淀机制报告

**日期**: 2026-06-28
**任务编号**: AUM-TASK-2026-06-28-001
**状态**: 已完成

---

## 一、概述

本报告记录了ACE系统中"DNA → 技能自动沉淀机制"的实现过程和结果。该机制使ACE能够从已完成的任务中自动提取可复用的执行模式，沉淀为"技能"，并在后续遇到类似任务时直接调用，从而提高任务执行效率和系统演化能力。

---

## 二、可复用任务模式清单

通过对15个已归档任务的分析，共识别出7种可复用模式：

| 模式名称 | 任务数 | 共同标签 | Worker类型 | 状态 |
|---------|-------|---------|-----------|------|
| experience_validation | 4 | constraint, experience, experience_pattern | research | ✅ 已生成技能 |
| local_archaeology_absorption | 3 | absorption, category:考古报告, local_archaeology, rate_0 | research | ✅ 已生成技能 |
| fragment_archaeology | 3 | fragment_archaeology | research | ✅ 已生成技能 |
| archaeology_report_analysis | 1 | archaeology, report | synthesis | ⏳ 样本不足 |
| lexicon_gap_filling | 1 | lexicon, gap_filling | lexicon | ⏳ 样本不足 |
| axiom_candidate_promotion | 1 | axiom_candidate | research | ⏳ 样本不足 |
| structure_research | 1 | research, structure | research | ⏳ 样本不足 |

**说明**: 技能生成阈值为>=2个相似任务，样本不足的模式将在任务积累到足够数量后自动生成。

---

## 三、已生成的技能列表

### 1. experience_validation（经验验证）

- **技能类型**: research
- **来源任务**: RQ-20260627-004, RQ-20260627-005, RQ-20260627-007, RQ-20260627-019
- **使用次数**: 2次
- **任务模板**:
  - 标题模式: `经验验证: {topic}`
  - 优先级: high
  - 共同标签: constraint, experience, experience_pattern
- **匹配规则**:
  - 标签匹配: constraint, experience, experience_pattern
  - 标题关键词: 经验验证, 可以推广到更广泛的场景, 薄弱分类的概念积累不足

### 2. local_archaeology_absorption（本地考古吸收）

- **技能类型**: research
- **来源任务**: RQ-20260627-011, RQ-20260627-012, RQ-20260627-013
- **使用次数**: 0次
- **任务模板**:
  - 标题模式: `本地考古吸收: {topic}`
  - 优先级: high
  - 共同标签: absorption, category:考古报告, local_archaeology, rate_0
- **匹配规则**:
  - 标签匹配: local_archaeology, absorption
  - 标题关键词: 本地考古吸收

### 3. fragment_archaeology（碎片考古）

- **技能类型**: research
- **来源任务**: RQ-20260627-009, RQ-20260627-010, RQ-20260627-014
- **使用次数**: 0次
- **任务模板**:
  - 标题模式: `碎片考古: {topic}`
  - 优先级: medium
  - 共同标签: fragment_archaeology
- **匹配规则**:
  - 标签匹配: fragment_archaeology
  - 标题关键词: 碎片考古

---

## 四、技能系统架构

### 4.1 核心组件

| 组件 | 文件路径 | 职责 |
|------|---------|------|
| SkillGenerator | core/skill_generator.py | 技能生成、匹配、注册、使用记录 |
| TaskCreator (增强) | core/task_creator.py | 创建任务时优先检索匹配技能 |
| AceDaemon (增强) | ace_daemon.py | 主循环中集成技能注册和生成 |

### 4.2 技能模板格式

```json
{
  "skill_name": "技能名称",
  "skill_version": "1.0",
  "skill_type": "research/pattern/synthesis/lexicon",
  "description": "技能描述",
  "created_at": "创建时间",
  "created_from": ["来源任务ID列表"],
  "usage_count": 使用次数,
  "last_used_at": "最后使用时间",
  "task_template": {
    "title_pattern": "标题模式",
    "priority": "默认优先级",
    "common_tags": ["共同标签"],
    "hypothesis_template": "假设模板",
    "depends_on_pattern": ["依赖模式"],
    "outputs_expected": ["预期输出字段"]
  },
  "worker_config": {
    "worker_type": "Worker类型",
    "tools": ["使用的工具"],
    "data_sources": ["数据源"],
    "validation_required": true,
    "guardian_review": true
  },
  "examples": [
    {
      "task_id": "示例任务ID",
      "title": "示例标题",
      "priority": "优先级",
      "tags": ["标签"],
      "hypothesis_preview": "假设预览",
      "output_keys": ["输出字段"]
    }
  ],
  "matching_rules": {
    "tag_match": ["匹配标签"],
    "title_keywords": ["标题关键词"],
    "creator_match": ["创建者匹配"]
  }
}
```

### 4.3 目录结构

```
09_KNOWLEDGE/
  skills/
    manifest.json          # 技能清单（索引）
    SKILL-xxx.json         # 技能模板文件
    ...
```

---

## 五、技能调用记录

### 5.1 已验证的技能调用

- **任务**: RQ-20260628-005 (经验验证: 该文件（协议层）吸收率仅 10%...)
- **使用技能**: experience_validation
- **证据**: 任务带有 `skill_based` 标签，标签中包含技能模板的共同标签 (constraint, experience, experience_pattern)
- **结果**: 成功进入review状态

- **任务**: RQ-20260628-006 (经验验证: ...)
- **使用技能**: experience_validation
- **证据**: 任务带有 `skill_based` 标签
- **结果**: 成功进入review状态

---

## 六、主循环集成

### 6.1 技能注册步骤（第零步）

在每日主循环开始时执行：
1. 扫描所有已归档任务
2. 按标签/创建者/输出格式聚类
3. 判断聚类是否达到可复用阈值（>=2个任务）
4. 检查是否已有相似技能（标签重叠>=2）
5. 生成新技能模板并存入 09_KNOWLEDGE/skills/
6. 更新 manifest.json 技能清单

### 6.2 技能生成步骤（归档后）

每个任务归档后：
1. 检查是否有同类型的已归档任务
2. 如果形成聚类（>=2个相似任务）
3. 检查是否已有相似技能
4. 如无，则自动生成技能

### 6.3 技能调用步骤（任务创建时）

TaskCreator创建任务时：
1. 先在技能库中查找匹配的技能
2. 匹配分数计算: 标签重叠*2 + 标题关键词命中 + 创建者匹配
3. 匹配分数>=2时，认为匹配成功
4. 应用技能模板（优先级、标签、假设模板等）
5. 记录技能使用次数

---

## 七、设计原则与约束

### 7.1 核心设计原则

1. **技能只存储执行模式，不存储具体任务数据**
   - 技能模板是抽象的模式描述
   - 具体任务数据保留在任务池中

2. **技能生成是可选的，由系统判断**
   - 只有>=2个相似任务才生成技能
   - 避免过早抽象和过度泛化

3. **技能注册是自动的，每日主循环开始执行**
   - 确保技能库与任务池同步
   - 新技能自动被发现和注册

4. **技能调用是优先的，但不是强制的**
   - 有匹配技能时优先使用
   - 无匹配技能时走原有流程

### 7.2 约束

- ✅ 不删除现有任务池中的任务定义（DNA保留）
- ✅ 技能模板只存储"执行模式"，不存储具体任务数据
- ✅ 技能生成是可选的（由ACE判断是否可复用）
- ✅ 技能注册是自动的（每日主循环开始执行）

---

## 八、额外补充：技能演化机制

在实现过程中，补充了以下未在原始任务中明确提到的机制：

### 8.1 技能去重机制

- **问题**: 不同聚类方法可能生成相似的技能（如中英文名称重复）
- **解决方案**: `_find_similar_skill()` 方法，基于标签重叠（>=2个共同标签）判断技能相似性，避免重复创建
- **效果**: 确保技能库的精简性，避免技能冗余

### 8.2 技能使用统计

- **问题**: 无法知道哪些技能被频繁使用
- **解决方案**: 每个技能记录 `usage_count` 和 `last_used_at`
- **效果**: 可以识别高频技能，为后续技能优化和淘汰提供数据支撑

### 8.3 技能示例提取

- **问题**: 技能模板过于抽象，难以理解具体用法
- **解决方案**: 每个技能包含最多3个来源任务的示例
- **效果**: 技能具有可解释性，便于人类审查和调试

---

## 九、未来优化方向

1. **技能质量评估**: 根据任务成功率、验证通过率等指标评估技能质量
2. **技能演化**: 随着更多任务使用技能，动态优化技能模板
3. **技能组合**: 支持多个技能组合使用，处理复杂任务
4. **技能淘汰**: 长期未使用的技能可以降级或归档
5. **技能参数化**: 支持更灵活的模板变量替换，不仅限于标题
6. **Worker类型扩展**: 增加更多Worker类型（如lexicon、scan等）
7. **技能依赖关系**: 技能之间可以有依赖关系，形成技能图谱

---

## 十、结论

DNA → 技能自动沉淀机制已成功实现并集成到ACE主循环中。当前系统拥有3个可用技能，其中`experience_validation`技能已被成功调用2次，验证了端到端流程的正确性。

该机制使ACE具备了从经验中学习、自动沉淀可复用模式的能力，是系统从"一次性任务执行"向"技能积累与复用"进化的关键一步。

---

*报告生成时间: 2026-06-28*
*生成者: ACE SkillGenerator v1.0*
