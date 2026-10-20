# ACE 本体 1.0 落地里程碑

- **里程碑**：ACE Ontology 1.0 / Civilization Map Kernel
- **基准日**：2026-10-02
- **状态**：LANDED
- **性质**：治理里程碑与可审计引用，不是新的运行时、任务池、记忆库或 Authority。

## 本体边界

ACE 本体保留跨世界连续性所需的最小语义：

1. **Canonical Identity**：`core/civilization_map_reference.py::canonical_object_id`；由 `namespace + local_identity` 派生稳定 ID，路径只能作为 locator。
2. **Topology / Relation**：`MapObjectRef`、`MapRelation`；记录 belongs/derived/depends/verified/projects/copies/mounted 等关系。
3. **Chronology / State**：对象携带 `current/candidate/experiment/frozen/archived/unknown` 状态；Authority 与 Projection/Index/Cache/Recovery Copy 分开。
4. **Semantic Coordinates**：沿用既有 L0-L6，不重新编号；本里程碑不改变宪法层级。
5. **Capability Addressing**：对象引用携带 `capability_addresses`，能力与挂载世界可替换，地址不随 Runtime 改变。

## 生产落点

- `core/civilization_map_reference.py`：无状态引用与校验工具，不拥有任何数据写入权。
- `core/task.py`：TaskPool admission 写入 canonical identity、payload hash、operation intent、idempotency token、generation。
- `ops/test_civilization_map_reference.py`：身份、关系、Authority 回指和 admission 语义回归。

## 已验证不变量

- 路径变化不改变同一逻辑对象的 canonical identity。
- Projection/Index/Cache/Recovery Copy 必须回指 Authority。
- 同一对象的不同 operation intent 或不同 payload 不再被 source-only 逻辑静默吞并。
- 历史 legacy admission 继续按既有契约去重。
- Memory、Knowledge、TaskPool、Runtime、Video Kingdom 等 Authority 未被合并或替换。

## 后续阶段

P1 从本里程碑的身份工具出发，审计既有 Memory/Knowledge/State Authority 的关系、投影、写入路径和未闭环边界。P1 只产生可追溯审计结论和修复任务，不自动晋升候选、不重构 Authority。

## 验收收据

- 定向回归：16 passed。
- 语法编译：`civilization_map_reference.py`、`task.py`、对应测试通过。
- 具体 P1 census：见 `08_GOVERNANCE/ACE_P1_AUTHORITY_RELATION_AUDIT.v1.md`。
