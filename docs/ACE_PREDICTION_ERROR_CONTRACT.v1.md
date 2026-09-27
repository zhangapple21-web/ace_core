# ACE 预测误差契约 v1

## 目的

ACE 不把“模型返回成功”“任务结束”或“文件生成”当作现实成功。每个需要
行动的闭环可以在现有 `ClosedLoopEngine` 上附带一份预测误差收据：

```text
expected_state
    ↓
success_observables
    ↓
actual_observation
    ↓
matched / mismatched / unknown
    ↓
KEEP / RETRY / ROLLBACK / UNKNOWN
    ↓
现有 failure replay / capability growth 门
```

这是一层反馈契约，不是第二个调度器、第二套晋升系统，也不授予执行权。

## 收据入口

- 实现：`core/prediction_error_contract.py`
- 既有闭环接入：`core/closed_loop_engine.py::ClosedLoopEngine.run_cycle(prediction=...)`
- 运行时收据：`09_KNOWLEDGE/closed_loop/prediction_error_receipts.jsonl`
- 执行授权和生产集成永远固定为 `false`。

## 最小输入

```python
prediction = {
    "subject": "镜头表演",
    "expected_state": {
        "performance": {"hand_action": "raise_hand", "listener_reaction": "turn_head"}
    },
    "success_observables": [
        {"name": "hand_action", "path": "performance.hand_action"},
        {"name": "listener_reaction", "path": "performance.listener_reaction", "severity": "critical"},
    ],
    "observation_refs": ["video_receipt://shot-001/readback"],
    "actual_observation": {
        "performance": {"hand_action": "raise_hand", "listener_reaction": "none"}
    },
    "resource_budget": {"max_retries": 1},
}
```

规则：

- 所有观测都匹配 → `KEEP`；
- 有偏差但没有关键观测失败 → `RETRY`；
- 标记 `severity=critical` 或 `rollback_required=true` 的偏差 → `ROLLBACK`；
- 缺真实观测或预期值 → `UNKNOWN`。

`observation_refs` 是真实回读、测试产物或审核收据的可追踪引用。没有它，
即使传入的字段碰巧匹配，也只能是 `UNKNOWN`，不能让指标闭环晋升。

当 `ClosedLoopEngine` 收到 `prediction` 时，`RETRY`/`UNKNOWN` 会阻断能力晋升，
`ROLLBACK` 会转成既有的 `ROLLBACK_REQUIRED`。因此一次指标改善不能掩盖现实
表现失败。

## 边界

预测收据是事实/证据边界内的观测记录，不是意识证明，不是模型永久身份，
也不是把“情绪”或“预测”写成事实。无法观测的部分必须保留 `UNKNOWN`，等待
下一次有界验证。
