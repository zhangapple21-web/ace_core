# 质询管道考古报告

**日期**：2026-07-02
**事件**：TASK-003 质询管道落地
**任务来源**：EVOLVE-2026-07-01-civilization-os-activation 第一阶段最后一块
**风险等级**：中（新增流程，不修改核心数据结构）

---

## 一、背景

EVOLVE-2026-07-01 计划第一阶段三个任务：
- TASK-001 文明体检（趋势分析）— 2026-07-01 完成
- TASK-002 四人圆桌（议会）— 2026-07-01 完成
- TASK-003 质询管道（辩论）— 2026-07-02 完成 ← **本报告**

TASK-003 的目标：让 Validator 和 Researcher 从"一次过审"变成"多轮交锋"。

---

## 二、做了什么

### 2.1 新增模块

[core/inquiry_pipeline.py](file:///c:/Users/USER/Downloads/Telegram%20Desktop/ace_runtime/core/inquiry_pipeline.py) — InquiryPipeline 类

核心方法：
```
run(task, validate_result) → {
    inquiry_rounds: int,      # 实际质询轮数
    questions: List[str],     # 每轮质询问题
    answers: List[str],       # 每轮回答
    final_verdict: str,       # passed / rejected / inconclusive / skipped
    verdict_reason: str,      # 裁决理由
}
```

### 2.2 接入点

[ace_daemon.py](file:///c:/Users/USER/Downloads/Telegram%20Desktop/ace_runtime/ace_daemon.py) 修改两处：

1. **初始化**（第 364-376 行）：在 Validator 初始化后，初始化 InquiryPipeline
2. **任务处理流程**（第 1454-1474 行）：在 cross_validate 之后，如果验证未通过且有异议，启动质询管道

### 2.3 测试

[ops/_test_inquiry_pipeline.py](file:///c:/Users/USER/Downloads/Telegram%20Desktop/ace_runtime/ops/_test_inquiry_pipeline.py) — 5 个测试用例：

| 测试 | 场景 | 结果 |
|------|------|------|
| 测试0 | import 和初始化 | ✅ PASS |
| 测试1 | 验证通过时跳过质询 | ✅ PASS |
| 测试2 | 无异议时跳过质询 | ✅ PASS |
| 测试3 | 规则模式质询（3轮 inconclusive）| ✅ PASS |
| 测试4 | 规则模式证据充足时质询解决（1轮 passed）| ✅ PASS |

---

## 三、设计决策

### 3.1 不改现有 Validator/Researcher

**选择**：新增独立模块 InquiryPipeline，不改 validate_task / research_task 的现有逻辑。

**理由**：
- 现有 validate_task 内部会 move_task，改它风险高
- 独立模块可以独立测试，不影响现有流程
- 符合"笨但稳定"原则

### 3.2 LLM 不可用时降级为规则模式

**选择**：InquiryPipeline 在 LLM 不可用时，用规则模式（基于证据数量判断）。

**理由**：
- 系统要"活得久"，不能依赖 LLM 可用性
- 规则模式虽然笨，但能完成质询流程
- LLM 可用时自动升级为智能质询

### 3.3 质询链记录到 task 的 note

**选择**：用 add_validation_note / add_research_note 记录质询链。

**理由**：
- 遵循 append-only 原则
- 不新增数据结构，复用现有 note 机制
- 质询链随 task 一起归档，不断裂

### 3.4 质询通过后手动 move 到 approved

**选择**：如果质询通过，手动 move_task 到 approved。

**理由**：
- validate_task 在 passed=False 时已经 move 到 active
- 质询通过后需要"拉回"approved
- 这是唯一改 task 状态的地方，风险可控

---

## 四、流程对比

### 4.1 修正前（一次过审）

```
Researcher 研究 → Validator 验证
  ├── 通过 → approved → Guardian 终审
  └── 不通过 → 退回 active → Researcher 重新研究（被动）
```

### 4.2 修正后（多轮交锋）

```
Researcher 研究 → Validator 验证
  ├── 通过 → approved → Guardian 终审
  └── 不通过 → InquiryPipeline 质询
       ├── 质询解决 → approved → Guardian 终审
       └── 质询未决 → 退回 active（3轮后）
```

---

## 五、与其他系统的关系

### 5.1 连续性修正案

TASK-003 是连续性修正案 `mandatory_consistency_check` 的任务级实现：
- 系统级一致性检查：每天对整个记忆库做体检（待落实）
- 任务级一致性检查：InquiryPipeline 对单个任务做多轮质询（本任务）

### 5.2 现有验证流程

InquiryPipeline 不替代现有验证，是增强：
- validate_task：规则验证（证据数量、假设存在、反例、词库匹配）
- cross_validate：多模型交叉验证（LLM 背刺）
- **InquiryPipeline：多轮质询（Validator ↔ Researcher 辩论）** ← 新增

### 5.3 Guardian 终审

InquiryPipeline 不绕过 Guardian：
- 质询通过 → approved → Guardian 仍需终审
- 质询未决 → 退回 active → 不进入 Guardian

---

## 六、改变了什么指标

| 指标 | 修正前 | 修正后 |
|------|--------|--------|
| 验证流程 | 1轮（validate + cross_validate）| 最多 4 轮（validate + cross_validate + 3轮质询）|
| 任务级一致性检查 | 无 | 有（InquiryPipeline）|
| Validator ↔ Researcher 交互 | 单向（退回）| 双向（质询-回答）|
| EVOLVE-2026-07-01 第一阶段 | 2/3 完成 | 3/3 完成 ✅ |

---

## 七、考古纪律声明

- **FACT**：InquiryPipeline 已实现，5 个测试用例全部通过，ace_daemon.py 语法检查通过
- **EVIDENCE**：core/inquiry_pipeline.py（268行）、ace_daemon.py 第 364-376 行 + 第 1454-1474 行、ops/_test_inquiry_pipeline.py
- **HYPOTHESIS**：质询管道能提升任务验证质量（需长期观察 inquired / inquiry_passed 指标）

---

## 八、下一步

EVOLVE-2026-07-01 第一阶段全部完成。第二阶段预告（暂不执行）：
- Socrates 角色雏形：每天对 Top 3 重要发现提出 3 个问题
- 五人圆桌会议
- 趋势阈值自动触发（污染率 > 10% 启动孟婆）

剩余 pending 任务：
- GOV-001 Phase-2（5 个子任务）
- NIGHT-2026-06-29 演化计划（4 个任务）

---

**报告时间**：2026-07-02
**报告者**：ACE / 结构考古
**依据**：EVOLVE-2026-07-01-civilization-os-activation.md TASK-003 + 连续性修正案 mandatory_consistency_check
**状态**：已完成，待生产环境验证
