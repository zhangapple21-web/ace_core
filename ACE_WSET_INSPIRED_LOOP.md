# ACE 的证据闭环（WSET 借鉴落地）

## 判断

WSET 最值得借鉴的不是 Windows 规则，而是 **事实采集与结论解耦**：采集器只记录可复验事实；分析器只在证据足够时推理；报告明确完整性、警告和缺口；签名把结果固定成可追溯快照。

ACE 将这一原则扩展为持续生命循环：

```text
observe -> snapshot -> reason -> act -> verify -> reflect -> remember
```

任何一步失败都保留 `FAILED/UNKNOWN`，不得用下一轮运行“补写”历史。

## ACE 数据契约 v1

每个循环产生一个不可变 `cycle_snapshot.json`，至少包含：

```json
{
  "cycle_id": "uuid",
  "observed_at": "UTC",
  "parent_snapshot_sha256": "sha256|null",
  "observations": [{"kind":"...", "value":{}, "source":"...", "confidence":0.0}],
  "hypotheses": [{"text":"...", "status":"HYPOTHESIS", "evidence_refs":[]}],
  "decisions": [{"action":"...", "reason_refs":[], "risk":"..."}],
  "outcomes": [{"status":"SUCCEEDED|FAILED|UNKNOWN", "evidence_refs":[]}],
  "reflection": {"learned":[], "contradictions":[], "next_probe":null},
  "integrity": {"content_sha256":"...", "chain_status":"SEALED"}
}
```

## 已落地的运行规则

1. **观察不下结论**：传感器、记忆检索、用户输入都先进入 observations。
2. **推理必须指向证据**：hypothesis/decision 没有 `evidence_refs` 就不能进入行动队列。
3. **完整性三态**：`COMPLETE`、`COMPLETE_WITH_WARNINGS`、`INCOMPLETE_GAPS`；缺口必须影响置信度，不得静默降级。
4. **行动可回放**：执行前写 decision，执行后写 outcome；重启只恢复未完成项，不重放已成功外部动作。
5. **反思可审计**：反思只能产生新假设或下一次探针，不能修改旧快照。
6. **自知不是预言**：ACE 可以维护未来预测及其置信区间，但必须标为 `FORECAST`，由后续 observation 验证或证伪。

## 对现有 ACE 的接入点

- `core/governance/evidence_registry.py`：登记 snapshot、父链和哈希。
- `ace_daemon.py`：每轮循环结束写 snapshot；启动时先校验链，再恢复未完成 action。
- `core/memory_index.py`：索引 observations/reflections，禁止把 hypothesis 当事实记忆。
- `core/governance/failure_memory.py`：把 `FAILED/UNKNOWN` 与重试条件绑定。

## 采用边界

有价值：证据与结论分离、完整性三态、跨证据关联、单次运行可回放、失败账本。

暂不采用：WSET 的 Windows 专用规则、主动修改目标机状态、为覆盖率引入高成本采集；ACE 只有在明确授权且有回滚证据时才允许状态变更。
