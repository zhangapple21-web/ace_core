# 意志层修复记录：已消费意志被重开的那次事故

时间：2026-10-03 16:49:38 – 16:50:39（约 1 分钟内 10 次）

## 现象

`intents/intent_state.json` 里 `r1_principia_alignment` 的 history 出现 10 组
`injected` 记录，全部指向 `RQ-20261003-012`，而记录的状态字段停在 `candidate`。
该意志的任务早已 `archived` 且 `delivery.verification.satisfied = true`。

## 三个独立缺陷叠加

### 1. `sys.path` 成对守卫（会静默失效）

```python
if str(ROOT) not in sys.path:          # 仓库根通常已经在 sys.path 里
    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(ROOT / "ops"))   # 于是这行永远不执行
```

daemon 里 `from ops import daily_intent_scheduler` 时，仓库根必然已在 `sys.path`，
所以 `ops/` 从未被加入，`from inject_target import ...` 抛
`ModuleNotFoundError`。**每个晚班都会 `status=ERROR`**，而单测全绿——因为单测把
scheduler 当脚本跑，走的是另一条路径。

### 2. 观察值落盘顺序倒置

`record_observations()` 用的是 `assess()` 的结果，而 `assess()` 读池子发生在注入
**之前**。原代码先注入、后记录，于是注入前的 `candidate` 覆盖了 `injected`，
history 变成 `injected → candidate`（时间倒流），状态落后于真相。

### 3. 状态可被陈旧观察降级（放大了上面两条）

`record_observations()` 无条件 `record["state"] = item["state"]`，并且
`record["task_id"] = task.get("task_id") or record.get("task_id")` 在观察没有 task
时虽然保住了 `task_id`，但**状态**照样被降级。一次 `candidate` 观察就能把
`fulfilled` 打回 `candidate`，下一轮 assess 就会认为它可注入。

此外 `find_intent_task()` 按 `SEARCH_ORDER`（按 status 分组）遍历，命中多个
archived 时返回的是**排序最靠前**的那个，而不是最新的那个；`locate_intent_task()`
却优先用 state 文件里的 `task_id`。同一个问题两个答案，分歧本身就是重注的温床。

## 修复

| 缺陷 | 修复 | 守卫测试 |
|---|---|---|
| 1 | 两个独立守卫；import 加 `ops.` 回退 | `test_scheduler_imports_under_the_daemon_module_path`（子进程里断言 `ops.daily_intent_scheduler` 可导入） |
| 2 | 先 `record_observations` 再 `inject_selected`（daemon 与 scheduler 两侧同修） | `test_a_candidate_intent_is_injected_once_and_recorded` |
| 3 | `STATE_RANK` 单调性：陈旧观察不得降级，降级尝试记入 history 并标 `rejected` | `test_a_stale_candidate_observation_cannot_demote_fulfilled` |
| 4 | `find_intent_task` 改为跨全部终态取**最新**（`created_at` + 数值化任务号排序） | `test_tag_scan_returns_the_newest_task_when_two_carry_the_intent`、`test_task_id_order_is_numeric_not_lexicographic` |

## 为什么没有产生一堆重复任务

`create_task()` 按 admission 去重，所以 10 次注入都返回同一个 `RQ-20261003-012`。
**任务池是干净的**（已核对：只有 `RQ-20261003-005` 和 `-012` 携带该 tag）。
损坏的只有 `intent_state.json` 的记录——但那正是防重注机制的唯一依据。

## 顺带修掉的相邻问题

- `inject_target.inject()` 硬编码 `TaskPool(ROOT/"task_pool")`，无视调用方传入的
  pool。任何一次 scheduler 自测都会把 intent 任务写进**生产**任务池——测试即污染。
  现在接受可选 `pool`，默认值不变，CLI 仍是唯一注入入口。
- `validate_target()` 放行纯空白 title（`"   "` 是 truthy，而 `inject()` 会 strip
  成空串）。

## 状态文件修复

已用 `assess()` 对着真实池子重建，保留全部 23 条 history，未删证据。
损坏原件备份在 `intent_state.corrupt.bak`。当前：

```
r1_principia_alignment     fulfilled  task=RQ-20261003-012
unfinished_will_index      fulfilled  task=RQ-20261003-008
free_zone_probe_lineage    candidate  task=None
```