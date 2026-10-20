# 意志层与交付门协议

**协议标识**：`ace.intent.pool.v1` + `ace.delivery.execution.v1`

本文件描述两条互相咬合的链：外部意志如何变成 Task，以及 ACE 如何判定 Task 承诺的物理产物是否真的存在。

---

## 0. 为什么需要这一层

在它存在之前，ACE 接受一个外部目标注入后会做这件事：

```
pending → active(Researcher) → review(Validator 提出 3 条质疑)
        → pending → active → review → …
        → 5 轮之后 blocked，理由「相同证据集重复验证达到上限，等待人工或外部新证据」
```

整个过程中 `outputs.delivery.required_path` 从未被任何代码读取，声明的 `success_metric` 是**装饰品**，文件从未被创建也从未被检查。`unblock_task` 又拒绝任何带 `terminal_non_convergent` 的任务，所以那句"等待人工或外部新证据"承诺的逃生口**根本不存在**。

实测：`RQ-20261003-001` 承诺 `docs/TASK_LIFECYCLE.md`，注入后 5 轮自我辩论，blocked。

---

## 1. 意志层 `ops/daily_intent_scheduler.py`

### 1.1 定位

**它是粮仓，不是喂食器。** 它不是第二个任务调度器，也不进 daemon 主循环。它只做一件事：

> 判断今天是否有一条意志值得占用 ACE 的交付能力；有就注入一条，没有就安静地什么都不做。

### 1.2 输入

`intents/daily_queue.jsonl`，每行一个结构化 intent。必需字段：

| 字段 | 含义 |
|------|------|
| `intent_id` | 唯一标识，注入后作为 Task tag `intent:<id>` |
| `question` | 意志本身，一句话，不含派工指令 |
| `why_now` | 为什么是现在 |
| `expected_result` | 预期结果（人类可读） |
| `verification_method` | 限四值：`file_exists_nonempty` / `schema_valid_json` / `tests_pass` / `user_accepted` |
| `delivery_path` | 物理产物相对路径，后缀限 `.md/.json/.py/.txt/.csv/.yaml/.yml` |

可选：`priority`、`domain`、`state`、`added_at`、`tags`。

### 1.3 生命周期

```
candidate → injected → active → verified → fulfilled → archived
                     ↘ blocked / withdrawn
```

状态不是自己维护的，而是**每次从 TaskPool 反查推导**（`locate_intent_task`）：

| Task 状态 | intent 状态 |
|-----------|-------------|
| 无关联 Task | `candidate` |
| pending / active / review / approved | `active` |
| blocked | `blocked` |
| archived + 交付已验证 | `fulfilled` |
| archived + 交付**未**验证 | `blocked`（不算完成，留待下一轮重试） |
| graveyard / rejected | `withdrawn` |

> 反查必须覆盖 `archived` / `rejected` / `graveyard`。只扫在途状态时，一条已归档的意志会退回 `candidate` 并被**重复注入**——这正是本层要防的盲注入。
>
> 优先用 `intents/intent_state.json` 里记录的 `task_id` 精确 `load_task`，tag 全量扫描只在状态文件丢失时兜底。

### 1.4 三种结局

| outcome | 触发条件 |
|---------|----------|
| `INJECTED` | 有 `candidate` 意志且外部在途量未达容量 |
| `HEALTHY_IDLE` | 外部在途量已达容量（`reason: external_backlog_at_capacity`） |
| `NO_VALID_INTENT` | 没有任何候选意志（全部已消费 / 已阻塞 / 字段不合法） |

**容量只算外部在途**（`count_external_in_flight`）：只统计带 `intent:*` tag 或声明了 `delivery` 的 pending/active/review 任务。

理由：自我观察任务会占满 `pending`，但它们**按构造永远交付不出东西**。把它们算进外部容量，等于 ACE 满脑子自己的噪声，外部意志永远排不上号。

### 1.5 不重复注入

两道锁：
1. `assess()` 推导状态，非 `candidate` 一律不可选。
2. `inject_selected()` 落笔前再查一次，命中则返回 `REFUSED_ALREADY_INJECTED` 并放弃。

### 1.6 用法

```bash
python ops/daily_intent_scheduler.py --status     # 只报告，永不注入
python ops/daily_intent_scheduler.py              # 评估并至多注入一条
python ops/daily_intent_scheduler.py --capacity 2
```

---

## 2. 交付门 `core/delivery_execution.py`

### 2.1 `verify_delivery(task, workspace)` —— 纯函数，只读

对文件系统判定声明的 `success_metric`：

| success_metric | 判定 | reason |
|----------------|------|--------|
| `file_exists_nonempty` | 存在 + 是文件 + size > 0 | `delivery_satisfied` |
| `schema_valid_json` | 上条 + `json.loads` 成功 | `delivery_satisfied` / `delivery_json_invalid` |
| `tests_pass` / `user_accepted` | 无自动判定 | `requires_external_receipt`（`satisfied=null`，**不阻断**） |

失败原因：`delivery_file_missing` / `delivery_file_empty` / `delivery_json_invalid` / `delivery_path_escapes_workspace` / `delivery_contract_invalid`。

成功时返回 `content_sha256`。这是关键：**按内容哈希而非 mtime**——真实修改会让验证器看到新证据从而收敛，空跑则不会。

**路径安全**：`required_path` 必须相对、后缀在白名单内、解析后落在工作区内。`..` 越界 → `delivery_path_escapes_workspace`。

### 2.2 `DeliveryExecutor` —— 有界、失败关闭

- 无 worker → `NO_WORKER_AVAILABLE`，**不伪造回执**。
- worker 报成功但没写文件 → `WORKER_FAILED`（收据永远来自磁盘，不采信 worker 自报）。
- worker 自报失败必须**如实记录**：`worker_verdict()` 读 worker 自己的 `success` / `ok` 字段，绝不用 `bool(report)`——真实 `OpenCodeWorker` 返回的是 mapping，`bool({"success": False})` 为 `True`，会让一次失败被写成 `ok: true`。
- 产物已存在 → `ALREADY_DELIVERED`，**不调用 worker**。

### 3.1 触发点：挂在 daemon 已有的晚班，不新增调度器

`_run_intent_pool_if_due()`（`ace_daemon.py`）在 `_run_free_zone_autonomy_if_due` /
`_run_sandbox_society_if_due` 之后调用，复用**同一个 18:30 专用班次**：

- 班次门：`(hour, minute) < (18, 30)` → `WAITING_FOR_DEDICATED_SHIFT`，不评估、不注入。
- 每日门：`state["intent_pool_date"] == today` → `ALREADY_RUN_TODAY`。
- 粮仓判定：走 `assess()` / `decide()`，返回 `NO_VALID_INTENT`（无候选）或
  `HEALTHY_IDLE / external_backlog_at_capacity`（外部在途满），**都不注入**。
- 只有 `INJECT` 才调用 `inject_selected()`，且回填 `summary["status"] = injection["outcome"]`
  ——上报**实际结果**而非决定。
- 无 `task_pool` → `TASK_POOL_UNAVAILABLE`。
- 遥测落 `cycle_progress["intent_pool"]` 与 `state["intent_pool_last"]`。

**没有 cron，没有 Windows 计划任务，没有第二个调度器。**

> 修复记录：观察值原本在注入**之后**落盘，于是 `record_observations()` 用注入前的
> `candidate` 覆盖了 `injected`，history 变成 `injected → candidate`（倒流），
> `intent_state.json` 的状态落后于真相。现在先记录再注入（daemon 与 scheduler 两侧同修）。

### 3.2 注入必须落进调用方的 pool

`inject_target.inject(payload, pool=None)` 新增可选 `pool`。默认值仍是生产
`task_pool`，CLI 入口行为不变、仍是系统里**唯一**注入入口；但 daemon 和 scheduler
都把手里已有的 pool 传进去。

> 修复记录：此前 `inject()` 硬编码 `TaskPool(ROOT/"task_pool")`，无视传入的 pool。
> 于是任何一次 scheduler 自测都会把 intent 任务写进**生产** task_pool——
> 测试即污染。已加 `test_injection_never_touches_the_production_pool` 守住。

daemon 侧绑定在 `_delivery_worker_runner()`：包装 `core.opencode_worker.OpenCodeWorker`。实测本机 `opencode v2.0.6` 位于 `C:\Users\Administrator\.local\bin\opencode.exe`，可执行、免登录、`cost: 0`，能真实写出文件。worker 构造或可执行文件缺失时返回 `None`，链条诚实停在"未交付"。

### 2.3 daemon 生命周期接入点

`_run_task_lifecycle_unlocked()` 中，Researcher 之后、Validator 之前：

```python
self._run_declared_deliveries(result)
```

行为：
- 遍历 `review` 任务，对声明了 `delivery` 的执行 + 验证。
- **已验证** → 把 `verified_artifact:<path>:<sha>` 写入 `task.evidence`（**必须在 `update_task` 之前**，否则验证器从磁盘重读时看不到，签名不变，继续判重复）。
- **未交付** → 一次性 `block_task(reason="delivery_not_produced:<path>", actor="delivery_executor", block_type="external_condition_blocked")`，不再退回 pending 重做研究。**不消耗重复证据上限**，因为它不是自我辩论。

遥测落在 `daemon_state["cycle_progress"]["delivery_execution"]`：

```json
{"review_seen": 2, "checked": 1, "delivered": 1, "not_produced": 0, "external_receipt": 0}
```

### 2.4 验证器侧的最小放宽

`Validator.validate_task` 的 `evidence_count >= 3` 是"三条独立证据"的启发式。当 `outputs.delivery.verification.satisfied is True` 时：

- 抑制「样本量不足」「没有任何证据支持」「第一条证据过短」三类反对；
- 通过条件改为 `evidence_count >= 3 or delivery_verified`。

`delivery_verified` 不能被伪造——它要求交付门自己的磁盘回执。Guardian 判决、交付门本身都不因此放宽。

---

## 3. `TaskPool.reopen_task()`

补上那句"等待人工或外部新证据"缺失的逃生口。

```python
pool.reopen_task(task_id, reason, actor="", new_evidence=None)
```

- `unblock_task` 继续拒绝 `terminal_non_convergent`（不放宽既有约束）。
- `reopen_task` 显式清除该标记，`reason` 必填，追加证据可选。
- 审计日志写独立 `reopened` 事件，**原始 blocked 迁移记录保留**，重复验证史不被抹掉。

---

## 4. 已验证闭环（真实执行记录）

### 4.1 `RQ-20261003-001` → `docs/TASK_LIFECYCLE.md`

```
pending → active(lease) → review(Researcher)
→ 交付门: ALREADY_DELIVERED, size 6892, sha 04de5cc3…
→ approved(Validator) → archived(Archivist), guardian_decision=experience
```

### 4.2 `RQ-20261003-005` → `docs/R1_PRINCIPIA_TO_ACE_MAP.md`

来源：intent `r1_principia_alignment`，经 `daily_intent_scheduler.py` 注入。

```
pending → active(lease) → review(Researcher)
→ 交付门: checked 1, delivered 1, size 13654
→ approved(Validator) → archived(Archivist)
→ scheduler 反查: fulfilled / task_archived / delivery_verified=true
```

两条闭环都留下了可追溯链：`intents/daily_queue.jsonl` → `intents/intent_state.json` → TaskPool 任务文件（含 `outputs.delivery.verification` 与 `audit_log`）→ `daemon_state.cycle_progress.delivery_execution`。

---

> **事故记录**：本层曾在一分钟内把一条已消费意志重开 10 次。三个缺陷叠加
> （`sys.path` 成对守卫在 daemon 内永不生效、观察值落盘顺序倒置、状态可被陈旧
> 观察降级）。完整分析见 `docs/INTENT_REINJECT_INCIDENT.md`。所有守卫测试在
> `ops/test_intent_no_reinject.py` 与 `ops/test_intent_daemon.py`。

## 5. 已知缺口

1. ~~**ACE 自己不生产文件。**~~ **已证伪并修正。** 交付门只验证、不代劳这一点仍然成立，但"本机没有 worker"是错的：`opencode v2.0.6` 在 `C:\Users\Administrator\.local\bin\opencode.exe`，只是不在 `PATH` 上，而 `OpenCodeWorker` 按绝对路径默认解析它。隔离工作区实测走**与 daemon 完全相同的接线**（同一 worker、同一提示、同一单模型），151.6 秒产出 `docs/REAL_CLI_DELIVERY_PROOF.md`（2251 bytes，sha `fc0f881f…`），状态 `DELIVERED`，收据来自磁盘。
   - 附带更正：`RQ-20261003-008` 的 `attempts: [{ok: true}]` 出自旧的 `bool(report)` 实现，**不能**证明该文件由 CLI 生成；磁盘收据（7600 bytes）是真的，来源未归因。
2. **每次交付尝试有约 22 秒纯浪费。** `OpenCodeWorker.run()` 内部对整个工作区做 `_fingerprint()`（`ace_core` = 21919 文件 / 445 MB，实测单次 11 秒），一次尝试前后各一次。该字段的唯一消费方是另一条 `_execute_task_with_worker()` 只读流（要求 `changed is False`，必须保留全工作区语义），故**未改动**；交付门本身不使用 `changed`，纯属附带成本。
3. **交付是有预算的。** 单次真实交付约 150 秒（22 秒指纹 + 约 98 秒模型 + 开销）。因此 daemon 侧改为：每个 cycle 最多一次**会调用 worker** 的交付检查，其余记入 `deferred` 留待下个 cycle；无 worker 时不设预算（纯磁盘读，没有可省的模型时间）。模型扇出也从 `DEFAULT_MODEL_ORDER`（5 个）收窄为单个 `fast_inspection`——失败留给下个 cycle 重试，而不是在一个 cycle 内换 5 个模型。
4. **自我噪声仍会拖慢外部意志。** `pick_up_task` 内部有 `untouched` / `aging` 公平性规则，会覆盖新增的 `_delivery_first` 同优先级排序。外部意志最终会被领走（实测），但要排队。
5. **probe 坟场约 200+ 份** `08_GOVERNANCE/civilization/graveyard/research_probe_cycle-probe-*.json` 未清理。