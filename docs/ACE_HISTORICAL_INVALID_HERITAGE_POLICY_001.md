# ACE 历史无效证据隔离政策 001

更新时间：2026-08-31  
适用对象：`07_SANDBOX/free_research` 的历史实验、蒸馏、工厂收据和懒猫挑战记录。

## 决策

法院发现哈希不一致时，原始记录必须继续保持 `INVALID`。可以建立独立的
`ARCHIVED_INVALID_HERITAGE` 登记，将文件路径、原始哈希、重算哈希、观察时间和原因固定下来，但登记本身不能让法院跳过校验。

```text
原始记录（append-only） ──哈希失败──> Court: INVALID（持续可见）
                                      │
                                      └──> Historical Registry:
                                           ARCHIVED_INVALID_HERITAGE
                                           report_only / no promotion
```

## 为什么不允许“跳过校验”

“已知异常”与“已验证有效”是两个不同状态。若法院读取一份声明后跳过哈希检查，后续报告可能把被篡改的历史材料误认为完整证据，破坏 lineage 和复盘可信度。隔离登记的作用是分类、追溯和统计，不是抹平异常。

## 本次登记

`08_GOVERNANCE/evidence/historical_integrity/EXP-SHIFT-92A480C775DB32BD.json`
记录了 `EXP-SHIFT-92A480C775DB32BD` 的蒸馏哈希差异，固定了：

- `stored_hash` 与 `recomputed_hash`；
- 原始蒸馏文件路径和来源记录哈希；
- `skip_court_validation=false`；
- `promotion_eligible=false`、`production_integration=false`；
- 本次自由区回合和哈希重算的证据引用。

## 后续真实历史回放

获得具备 Point-in-Time 属性且来源合法的 A 股历史 Tick/逐笔快照后，可在自由区新建独立回放会话。新会话必须使用新的数据快照哈希、规则版本和成本模型，不能覆盖或“修复”旧记录；旧记录只作为历史异常样本保留。

