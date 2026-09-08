# ACE 收盘复盘增量与下一交易日观察池 — 2026-08-29

- 复核证据时点：2026-08-29 15:36 +08:00
- 市场日历语境：周六，A 股非交易日；本附件是对 2026-08-28 收盘报告的增量复核，不伪装成新的交易日收益复盘
- 历史基准：`outputs/ACE_CLOSE_REVIEW_2026-08-28.md`
- 正式班次：`06_RUNTIME/ace/data/daily_shift_latest.json`，仍由唯一生产 daemon 管理
- 运行身份：PID `12828`，run `2c54d74a864a4c469d320d42edd0f9dc`；process、`.daemon.lock`、`heartbeat.json` 与 DAILY SHIFT 一致
- 研究状态：`RESEARCH_ONLY_DATA_DEGRADED`
- 交付边界：Finance `DEGRADED`；Advisor `BLOCKED`；Risk `NOT_READY`；Owner TG `OFF`
- 总结论：周末没有新的交易行情、完整 D0 纸面记录或可复盘 outcome receipt。8 月 28 日的零荐股、零评测、零 postmortem 结论不变；8 月 31 日继续执行数据准入观察池，不扩成股票推荐池。

## 事实、推断、未知

- **FACT**：截至 15:34 的 DAILY SHIFT 已记录 morning、open、midday、close 四个窗口，均为 `RESEARCH_ONLY`；`next_day_watchlist` 仍缺失。
- **FACT**：本日 `finance_live_refresh` 为空，能力矩阵与 benchmark 的最后修改时间均为 2026-08-28 09:36:47；没有 8 月 29 日的新交易数据。
- **FACT**：评测 pick 为 0，Paper Evaluation Journal 的 record 与 outcome receipt 均为 0，postmortem eligible prior record 为 0。
- **FACT**：当前 TaskPool 是 blocked 138、archived 561、graveyard 17；今日迁移为 claim/research/validation 各 14、approved/archived 各 4。
- **FACT**：今日有 2 次已准入生产模型调用且 2 次成功，均为 NIM `nvidia/nemotron-3-ultra-550b-a55b`；2 次成本均未知，账面 `total=0` 不能解释为零成本。
- **FACT**：知识目录新增 4 个 Pattern；没有新增 Constraint。四个源任务均已归档。
- **INFERENCE**：周末窗口复用了 8 月 28 日的数据能力证据和市场反证，适合维持门禁，不足以更新任何个股行情或验证周五收益。
- **UNKNOWN**：`next_day_watchlist` 未在本次复核时点落盘；其缺失必须保留，不能人工补记为已完成。

## 既有假设、观察与实际证据

| 假设/观察 | 新增或复核证据 | 判定 |
| --- | --- | --- |
| 非交易日不应强制 live refresh，也不应把旧 benchmark 写成今日行情。 | 四个 Finance 窗口的 `data_refresh=null`；matrix 与 benchmark 均停留在 8 月 28 日 09:36。 | 成立。周末只能复核门禁与运行沉积。 |
| 8 月 28 日的 Phase 2 阻断在出现新同窗证据前应保持。 | DAILY SHIFT 仍为 Finance `DEGRADED`、market review `RESEARCH_ONLY_DATA_DEGRADED`；下一动作仍是等待独立证据。 | 成立。没有新证据改变准入。 |
| 周末公开页面可提供市场上下文。 | 雪球、股吧、新浪页面可抓取，但没有可观察的上游条目时间戳；独立内容源计数为 0。 | 只能保留为未核验上下文，不能成为行情、情绪或推荐证据。 |
| 今日学习可产生可复用 Experience。 | 4 个任务归档并沉积 4 个 Pattern；但源任务 `result.counter_count=0`，部分沉积又引用旧摘要中的“反例数 2”。 | 写入事实成立，独立验真不足；不能视为已接纳能力。 |
| 今日可以补做股票评测或 postmortem。 | pick 0、journal record 0、outcome receipt 0、eligible prior 0。 | 不成立。不得补股票、价格、收益、胜率或目标位。 |

## 赢在哪里

1. **交易日边界保持诚实。** 周六没有被包装成新的 A 股收盘日，也没有强制刷新或复用旧价生成 K 线结论。
2. **唯一生产路径保持连续。** 进程、锁、心跳与 DAILY SHIFT 指向同一 PID/run；没有启动第二个 Scheduler、TaskPool、Router 或 Worker。
3. **交付门保持关闭。** 部分页面抓取、任务归档和模型成功都没有改变 Finance、Advisor、Risk 或 TG 状态。
4. **统计口径可区分。** TaskPool 当前存量与今日生命周期迁移分开记录；模型成本未知没有被洗成零成本。
5. **零结果被保留。** evaluation、journal 与 postmortem 没有因自动化需要报告而制造记录。

## 错在哪里或没有做到

1. **`next_day_watchlist` 缺失。** 本次等待到 15:36，daemon 仍只记录四窗；观察池只能由独立复盘附件保留，不能宣称正式窗口已完成。
2. **周末窗口语义仍像交易日。** morning/open/midday/close 四个名称继续出现，但没有 market-calendar 状态字段直接说明“非交易日”；下游必须靠日期与 `data_refresh=null` 解释，存在误读风险。
3. **市场上下文没有新鲜条目证据。** 抓取成功只证明页面可达，标题、导航与抓取时间不能替代上游 item timestamp。
4. **Experience 反证口径不一致。** 四个今日归档任务的 `result.counter_count=0`；沉积材料中出现的“反例数 2”来自旧归档摘要，不能算本任务主动反证。
5. **部分碎片任务价值判断过于泛化。** `DxDiag (2).txt` 与 `unrestricted_ai.py.txt` 仍以“可能包含有价值碎片”作为结论，缺少针对内容、用途和反例的直接验真。
6. **模型成本覆盖不完整。** 两次调用均为 unknown cost；`total=0` 只是已知成本求和，不是实际成本事实。

## 数据与治理缺口

- 没有 2026-08-29 交易数据；8 月 28 日 09:36 的 matrix/benchmark 不能代表周五收盘，也不能代表周一。
- 8 月 28 日 `close_review.data_refresh=null` 的缺口未被补齐，因此仍不能评价固定池个股的收盘触发、失效或收益。
- quote 的跨源 consistency、daily/5m 的当日 freshness、`430047` 的 TDX host exhaustion/Sina stale date 均没有新证据证明恢复。
- 公开情绪独立内容源计数为 0；market context 中两条 cross-validation question 仍是 `UNVERIFIED_CONTEXT`。
- 缺完整 D0 point-in-time snapshot、hypothesis、invalidation、双独立 evidence refs、Risk audit 与 outcome receipt。
- 缺本日两次 NIM 调用的可核对成本记录。

## 学习候选与 Experience 沉积

- Daily Learning 候选：“考古 vn.py Alpha 离线研究工作流”；状态 `queued_research`，原因 `requires_independent_miner_review`。范围明确禁止接 Gateway、券商或订单接口；任务归档不等于能力接入。
- 今日归档任务：`RQ-20260829-001` 至 `RQ-20260829-004`；知识目录新增 4 个 Pattern、0 个 Constraint。
- 可保留的候选经验：离线特征、实验与回测的组织方式可以继续做有边界的考古；必须保持与行情接入、券商接口、订单执行、推荐交付隔离。
- 不予提升的沉积：仅凭 generic hypothesis、历史归档互引或 Guardian/Archivist 写入，不能获得生产角色、Finance 准入或推荐权限。
- 下一次 Experience 验收条件：本任务必须有直接内容证据、至少一个主动反例、明确适用边界、去重后的独立来源，并由主 Agent 对冲突做接受或拒绝记录。

## 下一交易日观察池（2026-08-31，RESEARCH_ONLY）

1. **固定覆盖样本**：`600000`、`000001`、`300750`、`688001`、`430047`。这些是数据覆盖探针，不是推荐名单。
2. **五项核心操作**：quote、daily_kline、minute_kline_1m、minute_kline_5m、index 必须在交易日同窗复跑。
3. **数据全局门**：每项 availability、coverage、field completeness、freshness、consistency 均 `>=0.8`，血缘可观察，且至少两个独立合格组。任一项失败即维持 Phase 2 `NOT_ADMITTED`。
4. **专项复核**：quote 只比较同窗独立源；daily/5m 必须有 8 月 31 日 market-calendar-aware freshness；`430047` 必须确认 TDX host pool 和 Sina 日期均恢复。
5. **窗口完整性**：保存盘前/开盘/午间/15:00 后收盘证据；若 close refresh 仍为空，只做数据质量复盘。
6. **候选合同门**：只有生产上游提交完整 D0 snapshot/hash/source refs/hypothesis/invalidation/horizon policy/Risk audit 后，才允许产生最多两张 `EVALUATION_ONLY` 记录；否则 pick 与 postmortem 继续为 0。
7. **交付门**：Data/Admission/Validator/Risk 任一未通过，Advisor 保持 `BLOCKED`、Risk `NOT_READY`、TG/AUTO_PUSH `OFF`，不得使用“推荐、目标、胜率、上车”等措辞。

## ACE DAILY SHIFT 增量汇总

- TaskPool：当前 blocked 138、archived 561、graveyard 17；今日 claim/research/validation 各 14，approved/archived 各 4。
- 模型：2 次尝试、2 次成功；NIM Nemotron reasoning；shadow-only、routing effect false；2 次成本未知。
- 归档/Experience：今日归档 4；新增 4 Pattern、0 Constraint；学习候选仍待独立 miner 复核。
- Finance：`DEGRADED`；四个已观察窗口均 `RESEARCH_ONLY`；`next_day_watchlist` 缺失。
- Data：没有本日 live refresh；Phase 2 没有新证据改变 `NOT_ADMITTED`。
- Advisor：`BLOCKED`。
- Risk：`NOT_READY`。
- TG：`OFF`。
- Finance evaluation：0 pick，`NO_VALID_EVALUATION_PICK`；paper journal 0 record/0 receipt；postmortem 0 eligible。
- Public sentiment：`NO_OBSERVABLE_SENTIMENT_SOURCE`，独立内容源 0。
- 下一动作：`record_observation_and_wait_for_independent_evidence`。
- 合成工作：`NO`。

仅供研究与运行治理复盘，不构成投资建议。
