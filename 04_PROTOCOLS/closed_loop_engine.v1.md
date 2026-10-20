# ACE 闭环引擎 v1

ACE 的能力增长不是“每天改一点代码”，而是一次有证据的闭环：

```text
观察 → 拆解 → 记录基线 → 单变量改动 → 结果评估 → 痛苦复盘
     → 晋升 / 拒绝 / 回滚 → 生成下一次观察
```

## 强制收口

- 没有基线或结果不可比较：`BLOCKED_MISSING_EVALUATION`。
- 缺少代价、反事实后果、复发风险、可复用教训任一项：`REJECTED_MISSING_PAINFUL_REVIEW`。
- 指标退化：`ROLLBACK_REQUIRED`，不得把失败当成能力。
- 没有可测量改善：`REJECTED_NO_MEASURABLE_GAIN`，只进入失败复盘账本。
- 只有“有改善 + 完整痛苦复盘 + 明确 `retain: true`”才进入 `capability_growth.jsonl`。

## 分工边界

执行节点负责实验和提供结果；ACE 负责比较证据和作出收口判定。模型、插件、进程和项目都是可替换执行资源，不是永久能力。引擎只写追加式收据、失败复盘和能力增长记录，不直接改生产配置。

实现：`core/closed_loop_engine.py`。每次闭环的完整收据在 `09_KNOWLEDGE/closed_loop/cycle_receipts.jsonl`，下一次触发状态在 `06_RUNTIME/ace/data/closed_loop/state.json`。

后台桥：`core/closed_loop_background.py`。它最多调用三个多样化 MinerPool 模型提出拆解和指标方案；通过本地契约校验后才进入既有 TaskPool，模型没有直接写回权限。计划收据在 `09_KNOWLEDGE/closed_loop/plans.jsonl`，重复指纹不会重复派单。
