# P1：记忆 / 知识 / 状态权威关系审计

- **审计版本**：`ace.p1.authority-relation-audit.v1`
- **基准日**：2026-10-02
- **状态**：BASELINE_ESTABLISHED
- **审计原则**：识别、编号、回指、标注；不合并 Authority，不把索引/缓存/快照升级为 Authority。
- **证据基线**：`SOURCE_OF_TRUTH.md`、`core/memory_gateway.py`、`core/memory_index.py`、`core/memory_kernel.py`、`00_ROOT/ROOT_STATE.md`、`08_GOVERNANCE/evidence/memory_kernel_migration_assessment_20260929.json`。

## 1. Canonical census

| canonical ID | 语义对象 | role | state | 当前 Authority / locator | 关系结论 |
|---|---|---|---|---|---|
| `ace:ace:9aa60e2c19530c29db3dd808` | ACE civilization map kernel | authority | current | `core/civilization_map_reference.py` + L0-L6 根文档 | ACE 本体引用层，不拥有下挂世界数据 |
| `ace:root:3a2d29bda949988667c2ec47` | ROOT_STATE / 根连续性 | authority | current | `00_ROOT/ROOT_STATE.md` | 启动最小根状态；属于本体连续性基线 |
| `ace:memory:3da839763a46ef5436180e05` | MemoryGateway → MemoryIndex | authority | current | `06_RUNTIME/ace/data/memory/memory_index.json` | 当前唯一生产记忆读写链；gateway 是受控 facade |
| `ace:memory:1d9a430e6b0e48fbaab704e9` | MemoryKernel | authority candidate | candidate | `core/memory_kernel.py`、events/snapshot 设计 | staged migration candidate；不得默认读写或形成第二索引 |
| `ace:knowledge:8e22a97322e4fcdb803ef9cb` | canonical Knowledge | authority | current | `09_KNOWLEDGE/` | 受治理 Knowledge 目录权威 |
| `ace:taskpool:8b5334168400b1f2c941b428` | TaskPool task state | authority | current | `task_pool/` | 任务生命周期权威；不与 shared queue 合并 |
| `ace:runtime:111dc53eb6ef0b4a304099aa` | daemon runtime state | authority evidence | current | `06_RUNTIME/ace/data/memory/daemon_state.json` + heartbeat | 快照与心跳共同构成运行证据；快照单独不能证明 liveness |
| `ace:evidence:08d54593767be5246b951c45` | governance evidence registry | evidence ledger | current | `08_GOVERNANCE/evidence/evidence_registry.jsonl` | 证据收据，不直接授予生产权威 |
| `ace:experience:02d3fb71abb909a8affcf5ff` | ExperienceDeposition | authority | current | 受治理 Knowledge / ExperienceDeposition 路径 | 经验沉积权威；不能由 summary/index 单独替代 |
| `ace:capability:dd2ec07eb6f2689d25149d04` | capability cards | candidate projection | candidate | `09_KNOWLEDGE/capability_cards/` | `RESEARCH_READY_NOT_PROMOTED`；不是生产能力或 provider route |
| `ace:daily-learning:f2b5a9297d60847590d0e3d9` | DailyLearningLoop local knowledge | secondary write candidate | candidate | `06_RUNTIME/ace/data/memory/daily_learning/knowledge/` | 潜在第二知识写入路径；未证明近期双写，必须持续隔离审计 |

> ID 的生成使用 `canonical_object_id(namespace, local_identity)`；上述路径只作为 locator，不是身份来源。

## 2. 权威关系图（文字版）

```text
ACE map kernel
├── owns identity/relations/coordinates/addressing
├── references ROOT_STATE continuity baseline
├── mounts MemoryGateway → MemoryIndex [CURRENT AUTHORITY]
├── mounts canonical Knowledge [CURRENT AUTHORITY]
├── mounts TaskPool [CURRENT AUTHORITY]
├── observes Runtime snapshot + heartbeat [STATE EVIDENCE]
├── indexes Governance evidence registry [EVIDENCE LEDGER]
├── observes MemoryKernel [CANDIDATE / STAGED MIGRATION]
├── observes capability cards [CANDIDATE PROJECTION]
└── flags DailyLearningLoop local Knowledge [POTENTIAL SECOND WRITER]
```

禁止的关系推断：

- MemoryKernel 不因拥有事件账本设计就自动成为生产 Memory Authority。
- `09_KNOWLEDGE/index.json` 不因索引了 daily-learning 路径就成为 Knowledge Authority。
- `daemon_state.json` 不因写入 `alive` 就单独证明进程存活。
- capability card 不因存在于 Knowledge 目录就自动成为生产 Skill。
- evidence registry 不因记录结果就替代原始 Authority。

## 3. P1 审计结论

### P1-A：Memory

**结论：GREEN / 单生产入口已确认。**

- `MemoryGateway.backend_name == "MemoryIndex"`。
- daemon 生产构造为 `MemoryGateway(MemoryIndex(...))`。
- Gateway 不暴露 MemoryKernel 的 `import_records` 或 governed migration API。
- MemoryKernel 当前应标记为 candidate/staged migration，不得并行写入生产记忆。
- 已有 migration assessment 明确 `production_cutover_status=NOT_RUN`、`execution_authorized=false`、`production_integration=false`。

### P1-B：Knowledge

**结论：AMBER / canonical 目录明确，但存在潜在第二写入路径。**

- canonical Knowledge 为 `09_KNOWLEDGE/`。
- daemon 默认经验沉积指向 `09_KNOWLEDGE/`。
- DailyLearningLoop 构造 `06_RUNTIME/.../daily_learning/knowledge/` 下的本地 ExperienceDeposition。
- 近期 34 个每日结果为 `NO_VALID_LEARNING_TARGET`，尚未证明近期双写；但不能据此宣称已完成单一写入闭环。
- `09_KNOWLEDGE/index.json` 对 daily-learning 的历史引用是 lineage/index evidence，不改变 canonical Knowledge authority。

### P1-C：State / Runtime

**结论：AMBER / 快照、心跳和恢复证据必须分层。**

- `daemon_state.json` 是持久化运行快照。
- heartbeat/进程证据用于证明实时 liveness。
- recovery copy、audit receipt、PI/MCP 输出均是 projection/evidence，不拥有 ACE runtime state。
- 任何“运行中”结论必须至少关联 snapshot + heartbeat/进程证据，不能只读 JSON 快照。

### P1-D：Task / Evidence / Capability

**结论：各自 Authority 已保持分离。**

- TaskPool 负责任务生命周期；shared queue 不被吸收。
- evidence registry 负责治理收据；不替换原始记忆/Knowledge/Task Authority。
- capability cards 是 candidate projection；当前生产晋升仍为 false。

## 4. 本轮不做的事

- 不合并 MemoryIndex 与 MemoryKernel。
- 不合并 canonical Knowledge 与 daily-learning Knowledge。
- 不把 identity census 变成写入仲裁器。
- 不清理历史重复任务、不删除旧索引、不迁移历史 Memory。
- 不修改 daemon、runtime heartbeat、PID/restart 或隔壁生命周期写面。

## 5. P1 下一步闸门

1. **Knowledge write-path census**：逐个调用点标注 `read / candidate write / canonical write / projection`，确认 DailyLearningLoop 是否存在真实双写。
2. **State liveness join**：定义 snapshot、heartbeat、process receipt 的最小关联键和时间窗口，不新建 state store。
3. **Memory lineage sample**：对 MemoryIndex、MemoryKernel events、Hindsight adapter 做小样本 canonical identity/来源覆盖率审计，不执行 cutover。
4. **Projection back-reference check**：对 `09_KNOWLEDGE/index.json`、capability registry、PI/MCP 输出验证 authority 回指。
5. **Change gate**：每个 authority 关系变化必须遵守 `baseline → change → test → evaluation → compare`，并留下 receipt。

## 6. P1 验收标准

- 每个被审计对象都有 canonical ID、role、state、authority locator、lineage/关系结论。
- 任何 projection/index/cache/recovery copy 都能回指其 Authority，或明确标记为缺口。
- 任何“唯一写入路径”声明都有调用点和测试证据。
- 未经 migration gate，不改变生产 Memory backend。
- 审计报告不授予任何新生产权限。
