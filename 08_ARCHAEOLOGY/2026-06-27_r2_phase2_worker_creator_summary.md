# R2 Phase-2: Worker 化与 Task Creator 自动考古闭环
**日期**: 2026-06-27
**状态**: 已完成

---

## 一、原始任务清单 vs 实际完成

| 任务 | 状态 | 说明 |
|------|------|------|
| Worker化 ResearchWorker | ✅ 完整实现 | base_worker.py 已有完整骨架 |
| Worker化 PatternWorker | ✅ 完整实现 | 从 eco_parser 收集模式证据 |
| Worker化 SynthesisWorker | ✅ 完整实现 | 汇总多数据源生成报告 |
| Task Creator 自发现生成器 | ✅ 完整实现 | 扫描考古报告/经验模式/词库缺口 |
| Task Creator 接入主循环 | ✅ 完整实现 | _run_task_lifecycle 中调用 scan_and_create |
| 自主循环模式 | ✅ 完整实现 | _run_autonomous_loop，pending扫描→执行→直到阻塞 |
| 热度升级考古任务 | ✅ 已实现 | check_heat_upgrade 已在生命周期中 |
| Phase-2 总结文档 | ✅ 本文档 | — |

---

## 二、新增文件

| 文件 | 说明 |
|------|------|
| `core/task_creator.py` | Task Creator 自发现考古任务生成器 |
| `06_RUNTIME/workers/base_worker.py` | 统一 Worker 接口 + 三种 Worker 类型 |

---

## 三、Worker 化后调用链

```
ace_daemon._run_autonomous_loop()
  └── pick_up_task() → 从 pending/ 按优先级领取任务
        ↓
  _execute_task_with_worker(task)
        ├── 根据 task.tags 路由到对应 Worker
        │   ├── archaeology/report → SynthesisWorker
        │   ├── pattern/eco       → PatternWorker
        │   └── 默认              → ResearchWorker
        │
        ├── worker.execute(task) → {"status": "...", "outputs": {...}, "next_tasks": [...]}
        │
        ├── 更新 task.outputs + task.failure_reason
        │
        ├── 状态流转
        │   ├── failed → fail_task() → retry_count+1，≥3次进graveyard
        │   └── success → move_task(task_id, "review")
        │
        └── 派生任务处理
            └── next_tasks → create_task(depends_on=[parent_id])
                → emit_event("task_completed", ...)
```

---

## 四、Task Creator 触发条件

| 来源 | 条件 | 优先级 |
|------|------|--------|
| `08_ARCHAEOLOGY/*.md` | 最近7天内修改 + 未处理 | medium |
| `09_KNOWLEDGE/axiom/*.json` | 最近7天内新增 | critical |
| `09_KNOWLEDGE/constraint/*.json` | 最近7天内新增 | high |
| `09_KNOWLEDGE/pattern/*.json` | 最近7天内新增 | high |
| 词库薄弱分类 | 概念数 ≤2 | medium |

去重机制：检查 pending/active/review 中是否有相同标题任务，有则跳过。

---

## 五、实测效果（2026-06-27 15:03）

```
自主循环执行:
  循环迭代: 10 次
  Worker执行: 10 个任务
  阻塞停止: 0 次
  失败跳过: 0 次
  派生事件: 0 个

经验库: 1 条 pattern
任务池: 7 个任务（pending=4, active=2, archived=1）
```

---

## 六、运行模式变化

### Phase-1 之前
```
人工派单 / 事件文件 → Observer发现 → 生命周期运转 → 结束
```

### Phase-2 之后
```
Task Creator自发现 → 事件监听 → Observer → 生命周期运转
                                            ↓
                               自主循环 → Worker执行 → 派生任务
                                            ↓
                               经验沉积 → 知识沉淀 → 墓地清理
                                            ↓
                               若无新任务 → 等待下次运行
```

---

## 七、当前系统架构总览

```
ace_daemon (AceDaemon)
  ├── Scheduler (lexicon + memory_index)
  ├── Miners (eco_parser, slice_clusterer)
  ├── Export/Sync (ArchaeologyExporter, RepoSyncer)
  │
  ├── 任务生命周期层
  │   ├── TaskPool (task_pool/pending|active|blocked|review|approved|archived|rejected|graveyard)
  │   ├── Observer        — 发现问题 → create_task()
  │   ├── Researcher      — 领取 → 找证据 → review
  │   ├── Validator       — 找反例 → 退回/通过
  │   ├── Archivist       — 归档 → 经验沉积
  │   ├── Guardian        — 终审 → axiom/constraint/pattern/lesson
  │   ├── TaskCreator     — 自发现 → 自动生成考古任务
  │   ├── EventListener   — 事件 → 任务
  │   └── 自主循环模式     — pending扫描 → Worker执行 → 直到阻塞
  │
  └── Workers (Research / Pattern / Synthesis)
```

---

## 八、自愈过程记录（2026-06-27 下午）

本次自愈发现了三个深层BUG，已全部修复。

### BUG-1：review_count 持久化失败（最深层的BUG）

**现象**：Validator 终审保护机制无法触发，任务在 active↔review 之间无限循环。

**根因**：`Task.to_dict()` 有 `review_count` 字段（保存正确），但 `Task.from_dict()` → `Task.__init__` 中没有 `review_count` 显式参数，导致 `review_count` 进了 `**kwargs` 从未被赋值到 `self.review_count`。

```python
# 错误：review_count 被 kwargs 吸收，未赋值到 self
def __init__(self, ...):
    ...
    self.__dict__.update(kwargs)  # review_count 在这里，但 self.review_count 未定义

# 修复：在 __init__ 中显式提取
self.review_count = kwargs.get("review_count", 0)
```

**定位过程**：
1. 观察到任务文件里 `review_count=2` 但实际流转了11次
2. 推理：文件保存正确 → `to_dict` 没问题 → `from_dict` 读取时丢失
3. 验证：`Task.from_dict` → `__init__` 中确实没有 `self.review_count = ...`

**修复**：在 `Task.__init__` 中加 `self.review_count = kwargs.get("review_count", 0)`

---

### BUG-2：move_task 覆盖内存修改

**现象**：`update_task()` 保存后，`move_task()` 从磁盘 reload task，覆盖了内存中的所有修改（如 `review_count` 递增）。

**根因**：调用顺序 `update_task()` → `move_task()`，后者从磁盘读取旧版本，覆盖了前者的修改。

```python
# 修复前
self.task_pool.update_task(task)      # 保存 rc=1
self.task_pool.move_task(task.task_id, "review")  # reload 磁盘，rc变回0

# 修复后：move_task 支持直接传 task 对象
self.task_pool.move_task(task.task_id, "review", task=task)  # 不reload
```

**修复**：`move_task` 增加 `task: Optional[Task] = None` 参数，优先使用传入的 task 对象，不重新加载磁盘。

---

### BUG-3：Validator 死锁（active↔review 无限循环）

**现象**：即使 evidence>=3，但 Validator 提了多个异议就退回；每次退回旧 evidence 保留，Researcher 再找还是那些，Validator 再提更多异议，永不到 approved。

**根因**：终审保护阈值 `>=3` 加上之前 `review_count` 不持久化，导致保护机制从未触发。

**修复**：
1. 修复 review_count 持久化
2. 过滤无意义异议（"未发现明显逻辑漏洞"）
3. `review_count >= 3` 强制进入终审

---

### 端到端验证（2026-06-27 15:17）

```
Archivist归档: 1 个任务
经验沉积: 1 条（constraint类型）
Guardian判决: 1 个（constraint）
经验库: 2 条（constraint×1, pattern×1）
```

---

## 九、当前系统状态

| 组件 | 状态 |
|------|------|
| 任务池 | 7个任务（pending=4, active=1, archived=2）|
| 经验库 | 2条（constraint×1, pattern×1）|
| RQ-20260627-004 | active循环中，下次Validator到rc=3触发终审保护 |

---

## 十、已知问题 & 待优化

| 问题 | 现状 | 建议 |
|------|------|------|
| Worker 结果的 evidence 未走 Validator 流程 | Worker直接归档 | 需要验证 Worker 输出是否经过 Validator |
| Task Creator 7天内无新发现时无反馈 | 只打印日志 | 可降级扫描历史记忆生成任务 |
| blocked 任务积累后无告警 | check_graveyard 会处理 | 可增加 blocked 任务超时告警 |
| 自主循环 max_iterations=10 硬编码 | 当前可工作 | 后续按任务复杂度自适应 |

---

## 十一、自主循环运行规则（已确立）

根据用户指令确立：

> "从现在开始，我不再手动派单。你自行完成当前任务后，自动扫描 pending/，按优先级领取下一个任务并执行。执行完后再次扫描，直到所有可执行任务完成或遇到必须阻塞的任务。每完成一项，把状态和产出记录到 08_ARCHAEOLOGY/ 摘要中。不需要等我确认。"

当前已实现的自主循环逻辑：
1. 每次 `run_once` 中 `_run_autonomous_loop()` 自动执行
2. 优先级顺序：high → any（先处理紧急任务）
3. 遇到依赖阻塞 → `block_task()` → 停止循环
4. Worker 失败 → `fail_task()` → retry_count+1，≥3次进 graveyard → 跳过继续
5. 派生任务自动创建并记录 `depends_on`
6. 每轮结束自动生成考古摘要

---

*自动生成于 2026-06-27 — R2 Phase-2 完成*
