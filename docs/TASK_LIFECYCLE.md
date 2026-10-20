# ACE Task 生命周期说明

**交付契约**：`docs/TASK_LIFECYCLE.md`
**验收标准**：`file_exists_nonempty`
**来源**：`RQ-20261003-001`（`ace.target.inject.v1` 外部目标注入）
**文档生成者**：临时 Worker（外部会话）—— ACE 自身不写文件，见文末「已知缺口」

---

## 1. 任务状态机

`core/task.py` 定义 8 个状态：

| 状态 | 目录 | 含义 | 可执行 |
|------|------|------|--------|
| `pending` | `task_pool/pending/` | 已入池，等待领取 | 是 |
| `active` | `task_pool/active/` | 已被租约领取，执行中 | 是 |
| `blocked` | `task_pool/blocked/` | 被外部条件或治理规则阻断 | 否 |
| `review` | `task_pool/review/` | 研究完成，等待验证 | 否 |
| `approved` | `task_pool/approved/` | 验证通过，等待判决与归档 | 否 |
| `archived` | `task_pool/archived/` | 终态，已归档 | 否 |
| `rejected` | `task_pool/rejected/` | 终态，被否决 | 否 |
| `graveyard` | `task_pool/graveyard/` | 终态，坟场 | 否 |

合法迁移表（`ALLOWED_TRANSITIONS`，`core/task.py:73`）：

```
pending  → active | blocked | rejected | graveyard
active   → pending | blocked | review | rejected | graveyard
blocked  → pending | rejected | graveyard
review   → pending | active | approved | blocked | rejected | graveyard
approved → archived | rejected
rejected → graveyard
archived → (终态)
graveyard→ (终态)
```

`rejected → graveyard` 是唯一允许的「终态再迁移」，用于收敛墓碑体积。

---

## 2. 谁在什么阶段动任务

一轮 `_run_task_lifecycle_unlocked()`（`ace_daemon.py`）按固定顺序执行：

| 顺序 | 阶段 | Actor | 产出 |
|------|------|-------|------|
| 1 | 状态恢复 / 租约回收 | `recover_task_pool` | 清理僵尸 `active` |
| 2 | 日学习 | `daily_learning` | 学习闭环 |
| 3 | 受治理外部矿源 | `governed_external_miner` | 只读抓取 |
| 4 | MineSeed 扫描 | `mine_seed_scanner` | 考古任务 |
| 5 | 文件扫描 | `file_scanner` | 碎片任务 |
| 6 | 自我演化 | `self_evolution` | Observation |
| 7 | 事件监听 | `event_listener` | 事件转任务 |
| 8 | 观察者 | `observer.observe_and_create` | 候选任务（默认 ≤2） |
| 9 | 模型工作发现 | `model_work_discovery` + `obs_to_task_converter` | 准入任务 |
| 10 | 依赖解锁 | `task_pool.unblock_ready_dependencies` | blocked → pending |
| 11 | **研究** | `researcher.research_task`（本轮 ≤2） | pending → active → review |
| 12 | **交付执行与验证** | `delivery_executor` | 见第 4 节 |
| 13 | **验证** | `validator.validate_task`（≤3） | review → approved / pending / blocked |
| 14 | 质询 | `inquiry_pipeline`（本轮 ≤1） | 单轮有界质询 |
| 15 | 判决 | `guardian.judge`（≤5） | 批准/否决 |
| 16 | 政策卡投影 | `_project_verified_policy_cards` | 策略沉淀 |
| 17 | 归档 | `archivist.archive_task`（≤5） | approved → archived + 回执 |
| 18 | 经验沉积 | `_deposit_archived_experience` | 经验仓 |

每一步都被 `try/except` 包裹并记入 `daemon_state["errors"]`，单点失败不会中断整轮。

---

## 3. 关键机制

### 3.1 租约（Lease）

`claim_task()` 领取任务时写入 `claim_id` / `lease_expires_at`。`active` 是**租约态**：`update_task()` 在「落盘状态与存储状态不同且任一侧为 `active`」而存储侧没有 `claim_id` 时拒绝写入，防止无主推进。

### 3.2 执行纪律（ExecutionDiscipline）

`core/execution_discipline.py`。`ensure_execution_discipline(task)` 在每次 `_transition` 时被调用，保证任务携带 `ACE-EXECUTION-DISCIPLINE-1.1` 信封：复杂度分级、路由约束、事件流、检查点。`execution_gate()` 决定任务能否离开 `prepared` 进入实际执行。

### 3.3 准入校验（Admission）

`core/task_admission.py`。`create_task()` 无条件调用 `validate_admission()`，要求 `source_type` 在白名单内、`evidence` 非空、`verification_method` 非空。`SOURCE_TYPES` 现包含 `external_target`（外部目标注入通道）。

### 3.4 索引与一致性

`task_pool/task_index.json` 记录 `task_id → status/priority/created_at/updated_at`。`_rebuild_index()` 遍历 8 个状态目录重建；`recover_task_pool()` 删除同一 `task_id` 的重复文件并重建索引。

> 统计文件数必须用 `glob("RQ-*.json")` 逐状态目录遍历，顶层 `glob("*.json")` 只能看到 `task_index.json` 一个文件。

---

## 4. 交付执行与验证（`core/delivery_execution.py`）

任务可以通过 `outputs.delivery` 承诺一个**物理产物**：

```json
{"required_path": "docs/EXAMPLE.md",
 "success_metric": "file_exists_nonempty",
 "domain": "document"}
```

`verify_delivery(task, workspace)` 是纯只读函数，对文件系统判定 `success_metric`：

| `success_metric` | 判定 | 收据 `reason` |
|------------------|------|---------------|
| `file_exists_nonempty` | 存在、是文件、size > 0 | `delivery_satisfied` |
| `schema_valid_json` | 上条 + `json.loads` 成功 | `delivery_json_invalid` |
| `tests_pass` | 无自动判定 | `requires_external_receipt`（`satisfied=null`，不阻断） |
| `user_accepted` | 无自动判定 | `requires_external_receipt`（同上） |

失败原因区分 `delivery_file_missing` / `delivery_file_empty` / `delivery_json_invalid` / `delivery_path_escapes_workspace`。

**路径安全**：`required_path` 必须是相对路径、后缀在 `.md/.json/.py/.txt/.csv/.yaml/.yml` 白名单内，且解析后必须落在工作区内，`..` 越界返回 `delivery_path_escapes_workspace`。

**收据来源**：收据永远来自 `verify_delivery()` 读磁盘的结果，**不采信 Worker 自报的 `success`**。测试 `test_executor_receipt_comes_from_disk_not_from_worker_claim` 用一个「谎报成功但没写文件」的 Worker 断言状态为 `WORKER_FAILED`。

**失败即停**：产物缺失时，任务被一次性 `block_task(reason="delivery_not_produced:<path>", actor="delivery_executor", block_type="external_condition_blocked")`，不再退回 pending 重做研究。

---

## 5. 已知缺口

**ACE 自己不生产文件。** `DeliveryExecutor` 需要外部注入 `worker_runner`；daemon 在 `_delivery_worker_runner()` 中尝试绑定 OpenCode CLI，若 `opencode` 不在 `PATH` 上则返回 `None`，执行结果为 `NO_WORKER_AVAILABLE`，任务诚实地保持未交付。

这条链路是：

```
外部意志 → Intent Pool → Task → Researcher → DeliveryExecutor → 外部 Worker → 写盘
                                                                    ↑
                                                          ACE 只验证，不代劳
```

`_execute_task_with_worker()` 目前是桩实现，返回 `blocked / superseded_by_task_lifecycle`。把 Worker 接进 daemon 主循环是下一步，尚未完成。