# P1 Knowledge / Runtime Audit

> 审计基准：2026-10-02。只读审计；不改变任务、知识、能力卡或生产 gate 状态。

## 结论

- 唯一 canonical runtime 仍为 `C:\tmp\ace_core`；未发现第二运行入口获得生产权限。
- `09_KNOWLEDGE/` 是 canonical Knowledge 路径。daemon 的默认 `ExperienceDeposition` 指向该路径。
- 唯一 canonical runtime 仍为 `C:\tmp\ace_core`；未发现第二运行入口获得生产权限。
- `09_KNOWLEDGE/` 是 canonical Knowledge 路径。daemon 的默认 `ExperienceDeposition` 指向该路径。
- `DailyLearningLoop` 的 daemon 运行时已显式注入 `09_KNOWLEDGE/`；原 daily-learning knowledge 目录仅保留历史材料和隔离测试语义，不再是 daemon 默认生产写入路径。
- 当前文件规模不等于学习或生产能力：canonical Knowledge 有 920 个 JSON（其中 761 个 `EXP-*` 经验文件）；daily-learning 分支有 2 个 JSON（其中 1 个 `EXP-*`）。
- 最近已核对的 34 份每日结果为：`NO_VALID_LEARNING_TARGET=20`、`queued_research=12`、`adopt=1`、`observe=1`。
- 能力卡共 138 张，状态均为 `RESEARCH_READY_NOT_PROMOTED`，`production_integration=true` 为 0；本审计不执行晋升。

## Knowledge 读写矩阵

| 组件 | 读取/写入对象 | 当前判定 |
|---|---|---|
| `ace_daemon.py` | `09_KNOWLEDGE/`；构造默认 `ExperienceDeposition` | canonical 生产路径 |
| `core/daily_learning.py` | `daily_learning/knowledge/`；构造独立 `ExperienceDeposition` | 潜在第二写入路径，需治理收敛 |
| `core/governance/civilization_status.py` | `data_dir/09_KNOWLEDGE/` | 需按调用方 `data_dir` 语义继续核对；不得据此新增权威 |
| `core/learning_return_bridge.py` | `09_KNOWLEDGE/capability_cards/` | 受 gate 约束的候选能力卡写入 |
| `core/self_evolution.py` | `09_KNOWLEDGE/self_evolution/proposals.jsonl` | 治理提案记录，不是生产能力授权 |
| `core/closed_loop_engine.py` | `09_KNOWLEDGE/closed_loop/` | 受治理闭环收据/失败重放/候选成长记录 |
| `repository_curator.py`、治理报告/监控 | 读取 `09_KNOWLEDGE/experiences.json` 等 | 读取/报告投影，不改变权威关系 |
| PI/MCP bridge | 受限只读查询 | 不拥有 Knowledge 写权限 |

## 摄取到能力 lineage

`source -> evidence/admission -> TaskPool -> Researcher -> Validator -> Guardian -> Experience/Archivist -> capability card -> external verification -> production gate`

已核实的最新五天任务均为 `archived`，Validator 为 `approved`，Guardian 为 `experience`，Learning Return 为 `MATERIALIZED`；但 outcome receipt 为 `PENDING_EXTERNAL_VERIFICATION`，且独立来源不足。因此只能判定为研究/经验候选，不能判定为生产能力。

历史 `ace_codex_guard/state.json` 相关重复任务（至少 `RQ-20261002-127` 至 `RQ-20261002-143`）保留 lineage，交 Guardian/Archivist 按生命周期处理；本审计不删除。

## Runtime / liveness

- 最新持久化 heartbeat 的 PID `27332` 不存在，`last_beat=2026-10-02T13:11:19.887358`，因此 `status=alive` 是陈旧快照，不能证明 daemon 常驻。
- `daemon_state.json` 记录过一次完整周期，且该周期 `new_errors=[]`；历史 `status_l` 错误属于修复前记录，不作为当前周期失败。
- 当前三处运行锁均不存在：`.workspace.write.lock`、`.daemon.lock`、`task_pool/.lifecycle.lock`。
- 常驻 daemon 的退出根因仍未被充分证实；不能把单周期完成或宿主状态推断为持续运行。

## 验证记录

- `py -3 -m pytest ops/test_task_admission.py ops/test_file_scanner_workspace_boundary.py ops/test_local_archaeologist_governance.py ops/test_experience_deposition.py ops/test_learning_return_bridge.py ops/test_memory_gateway.py ops/test_self_evolution.py -q` → **36 passed**。
- `py -3 -m compileall -q ace.py ace_daemon.py core ops` → **通过**。
- Memory Gateway、continuity、admission、archaeology governance 既有审计结论保持有效。

## 未闭环与边界

1. DailyLearningLoop 与 canonical Knowledge 的写入权威尚未治理收敛；不自动合并、迁移或删除材料。
2. daemon 常驻 liveness 未验证；不盲目重启或宣称在线。
3. 重复历史任务等待 Guardian/Archivist 生命周期处理；保留全部证据与 lineage。
4. 能力卡维持未晋升；外部验证、独立证据和 production gate 未满足。
5. Node.js 不可用时不执行 PI-Desktop Node 插件测试；Python 回归与编译验证已完成。
