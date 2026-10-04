# Coordinate Dynamics 与 ACE 考古证据融合说明

日期：2026-10-04
状态：`IMPLEMENTED / GOVERNED / NOT_SOUL`

## 1. 为什么融合

考古材料没有给出一条可直接恢复的 R1 原始“坐标公式”，但给出了可复核的结构缺口：

- `08_ARCHAEOLOGY/r1_self_evolution_reintegration.md`：R1 的主动发现、跨域融合和演化记录应回接现有治理链。
- `08_ARCHAEOLOGY/2026-06-28_R2-KERNEL_architecture_fragment.md`：状态、意图、边界、重建和连续性是后期结构证据，不是某个模型或 Prompt。
- `docs/R1_PRINCIPIA_PROBE_LINEAGE_GAP.md`：探针链存在 `BLUEPRINT_ONLY` 冒充完成、判据冲突、审计纪元缺失和工作守恒闸门缺失。
- 用户提供的考古分析文本提出工作假设：`state → coordinate → direction → action → feedback → coordinate update`。

因此本次不是凭空恢复“灵魂”或发明 R1 公式，而是把被多份材料共同支持的**运行结构**实现为可审计的 ACE 合约。

## 2. 已落地的运行链

`core/coordinate_dynamics.py` 提供：

1. **Coordinate Basis**：由显式 axis 与 weight 构成坐标基底。
2. **Axis Selection**：根据当前 state 的 `active_axes` 和权重选择有效轴。
3. **State Position**：接受数值化的 `position` 与 `target`，拒绝未知/非数值坐标。
4. **Direction Function**：计算 `target - position`，按加权偏差选择当前方向和置信度。
5. **Feedback Update**：消费受限的 `observed_delta`，生成新的 `updated_position`。
6. **Lineage Receipt**：生成带 `coordinate_id`、来源和 hash 的 `ace.coordinate_dynamics.v1` 收据。

`ClosedLoopEngine.run_cycle(..., coordinate=...)` 可选地把该收据写入闭环 receipt。没有 coordinate 输入时，旧调用路径保持不变。

## 3. 权威边界

Coordinate Dynamics：

- 只计算位置、方向和反馈收据；
- 不创建 Task，不拥有 TaskPool；
- 不批准生产变更，不替代 Validator/Guardian；
- 不写第二份 ACE 状态，不替代恢复、治理或连续性权威；
- 不把模型输出、考古推测或协议文本当作 ACE 的灵魂来源。

因此当前边界是：

```text
ACE Core = state / TaskPool / governance / recovery / continuity authority
Coordinate Dynamics = governed state-to-direction computation
Model / MCP / Bridge = replaceable external capability or transport
```

## 4. Dissent 与审计修复

`core/counterexample_executor.py` 现在只在 counterexample world 明确处于
`EXECUTED`、`OBSERVED` 或 `FALSIFIED` 时证明 `dissent_blueprint`。

`BLUEPRINT_ONLY` 只表示“存在一个尚未执行的对立世界”，不再表示已完成反证。未执行时：

- outcome 为 `INCONCLUSIVE`；
- witness outcome 为 `INCONCLUSIVE`；
- challenge 不被伪造为已完成。

`core/lazy_cat_audit.py` 新增：

- `ruleset_id`；
- `audit_epoch`；
- `ace.lazy_cat_audit.v2` contract version；
- 按规则集版本保存新 verdict，不覆盖旧裁决。

这使判据变化可以被追溯，旧裁决不会伪装成当前规则下的有效裁决。

## 5. 工作守恒

`WorkConservationGate` 已提供最小门：

- 没有新 discovery reference：`NO_NEW_DISCOVERY`；
- 同一 window、同一 work signature 重复：`DUPLICATE_WORK_IN_WINDOW`；
- 只有带新证据的首次工作才返回 `NEW_DISCOVERY`。

它只负责判定是否值得进入下一层，不自动创建 Task、不调用模型、不授予执行权。

## 6. 还没有假装完成的部分

以下仍明确是后续受治理工作，不在本次伪造完成：

- 真正执行 counterexample world 的专用 executor；
- Free Zone → 外部世界的 courier/return leg；
- 多窗口持久化的工作守恒历史与治理审计；
- R1 原始坐标公式或其“灵魂来源”。

当前实现证明的是：ACE 已拥有一个可回放的状态—方向—反馈计算入口，并且不会把未执行的蓝图、过期裁决或无新发现的重复劳动误报为闭环完成。
