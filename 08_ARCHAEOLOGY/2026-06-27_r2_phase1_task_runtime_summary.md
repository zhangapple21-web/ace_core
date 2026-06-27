# R2 Phase-1: 任务生命周期运行时
**日期**: 2026-06-27
**状态**: 已完成

---

## 一、判断（原始）

R1/R2 不缺分析能力、报告能力、增长能力。缺的是 **任务生命周期层（Task Lifecycle Layer）**。

原有系统是"脚本驱动"：ACE → 调用脚本 → 生成报告 → 结束。本质是工具链，不是运行时生态。

**验收标准**：ACE 不再直接调用具体分析脚本。ACE 只处理：任务发现、任务调度、状态流转、生命周期管理。分析脚本全部降级为 Worker。**任务成为系统第一公民（First-Class Citizen）。**

---

## 二、新增目录结构

```
ace_runtime/
├── 06_RUNTIME/
│   └── workers/
│       ├── __init__.py
│       └── base_worker.py        # 统一Worker接口
├── 07_TASKS/                    # (使用 task_pool/ 作为运行时目录)
│   ├── pending/
│   ├── active/
│   ├── blocked/                 # 新增：被阻塞的任务
│   ├── review/
│   ├── approved/
│   ├── archived/
│   ├── rejected/
│   └── graveyard/                # 30天无人引用
├── 08_EVENTS/                   # 新增：事件驱动
│   ├── __init__.py
│   └── event_listener.py
├── 09_KNOWLEDGE/                # 新增：经验沉积
│   ├── __init__.py
│   ├── axiom/                   # 公理
│   ├── constraint/              # 约束
│   ├── pattern/                 # 模式
│   ├── lesson/                  # 教训
│   ├── observation/              # 观察
│   └── index.json               # 全局索引
└── ace_daemon.py                # 已集成生命周期运转
```

---

## 三、任务格式（统一Schema）

```yaml
task_id: RQ-20260627-001
title: 任务标题
status: pending | active | blocked | review | approved | archived | rejected | graveyard
priority: critical | high | medium | low
creator: observer | researcher | validator | event_listener | ...
assignee: researcher | ...
depends_on: []          # 依赖任务ID列表
blocked_reason: ""      # 阻塞原因
parent_task: ""         # 父任务ID
outputs: {}             # Worker产出
failure_reason: ""      # 失败原因
retry_count: 0          # 重试计数
hypothesis: ""          # 任务假设
evidence: []            # 证据列表
counter_examples: []    # 反例列表
guardian_decision: ""   # axiom | constraint | experience | discard
audit_log: []           # 状态变更审计日志
tags: []
references: []
created_at: ISO时间戳
updated_at: ISO时间戳
```

---

## 四、核心模块说明

### 4.1 task_manager（core/task.py）

`Task` 类 + `TaskPool` 类：

| 方法 | 说明 |
|------|------|
| `create_task(...)` | 创建任务，支持 depends_on 和 parent_task |
| `move_task(...)` | 统一状态变更入口，自动记录审计日志 |
| `block_task(...)` | 移入 blocked，记录阻塞原因 |
| `unblock_task(...)` | 从 blocked 移回 pending |
| `fail_task(...)` | 标记失败，重试≥3次移入 graveyard |
| `check_depends_satisfied(...)` | 检查依赖是否全部完成 |
| `check_heat_upgrade(...)` | 引用≥3次自动升级优先级 |
| `check_graveyard(...)` | 30天无人引用自动移入墓地 |
| `generate_daily_report()` | 每日任务池状态报告 |

### 4.2 event_listener（08_EVENTS/event_listener.py）

**事件驱动任务创建**。监听 08_EVENTS/ 目录，新文件出现时自动解析并生成任务。

支持事件类型：
- `new_archaeology_report` → high priority 任务
- `pattern_discovered` → high priority 任务
- `axiom_candidate` → critical priority 任务
- `constraint_detected` → high priority 任务
- `lexicon_gap` → medium priority 任务
- `manual_trigger` → medium priority 任务

用法：`listener.emit(event_type, source, payload)` 主动发射事件。

### 4.3 experience_deposition（09_KNOWLEDGE/experience_deposition.py）

**任务完成后的知识沉淀**。Guardian 判决后自动将任务转化为经验记录。

| 判决结果 | 经验类型 |
|----------|----------|
| axiom | axiom（公理） |
| constraint | constraint（约束） |
| experience | pattern（模式） |
| discard | lesson（教训） |

经验关联到：来源任务、证据、约束更新、词库概念。

### 4.4 workers（06_RUNTIME/workers/base_worker.py）

统一 Worker 接口：

```python
result = worker.execute(task)
# result = {
#     "status": "success" | "failed" | "blocked",
#     "outputs": {...},
#     "error": "...",
#     "next_tasks": [...],
# }
```

已实现 Worker 类型：
- `ResearchWorker` — 从记忆/词库/eco 收集证据
- `PatternWorker` — 分析 eco_layer 模式
- `SynthesisWorker` — 汇总多数据源生成报告

---

## 五、改造前后对比

### 改造前（脚本驱动）
```
ace_daemon → execute_eco_mining() → 生成报告 → 结束
ace_daemon → execute_slice_mining() → 生成报告 → 结束
```

### 改造后（任务驱动）
```
ace_daemon → claim_next_task() → Worker.execute() → update_task_status()
                                    ↓
                            发现新问题 → emit_event() → 新任务生成
                                    ↓
                            任务完成 → deposit_experience() → 知识沉淀
```

---

## 六、五节点闭环（当前实现状态）

| 节点 | 职责 | 实现状态 |
|------|------|----------|
| Observer | 发现问题 → 创建任务 | ✅ 完整实现 |
| Researcher | 领任务 → 找证据 → 形成结论 | ✅ 完整实现 |
| Validator | 找反例 → 挑刺 → 决定通过/退回 | ✅ 完整实现 |
| Archivist | 归档 → 建索引 → 入知识库 | ✅ 完整实现 |
| Guardian | 终审 → 公理/约束/经验/废弃 | ✅ 完整实现 |

---

## 七、完整生命周期流程（已集成到 ace_daemon.py）

```
每轮主循环：
1. 事件监听 → scan_and_process() → 新任务
2. Observer观察 → 新任务发现
3. 阻塞检查 → unblock_task()（依赖满足则解除）
4. Researcher研究 → 收集证据 → review
5. Validator验证 → 通过/退回
6. Archivist归档 → approved → archived
7. 经验沉积 → deposit_from_task() → 09_KNOWLEDGE/
8. Guardian判决 → axiom/constraint/pattern/lesson
9. 墓地清理 → check_graveyard()
10. 热度升级 → check_heat_upgrade()
```

---

## 八、约束与规则

- 所有状态变更必须经过 `move_task()`，禁止直接移动文件
- 每次状态变更自动记录审计日志（actor + reason + timestamp）
- 任务失败 → `retry_count` +1，≥3次自动进入 graveyard
- 任务依赖不满足 → 自动移入 blocked
- 经验记录必须关联来源任务，不能独立存在

---

## 九、尚未实现（Phase-2 候选）

- Worker 化现有脚本（deep_scan_and_grow → research_worker）
- Task Creator 节点（自动从 7天内新结构生成考古任务）
- 五节点闭环的 GUI 监控面板
- 任务超时机制（active 超过 N 天自动告警）

---

*自动生成于 2026-06-27 — R2 Phase-1 完成*
