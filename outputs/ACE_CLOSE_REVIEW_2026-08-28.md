# ACE 收盘复盘与次日观察池 — 2026-08-28

- 复盘证据时点：2026-08-28 15:30:08 +08:00
- 正式班次：`06_RUNTIME/ace/data/daily_shift_latest.json`
- 运行身份：PID `30112`，run `fc6d453908074b8a8cc25610f3ab7a41`；process、lock、heartbeat 与 DAILY SHIFT 一致
- 研究状态：`RESEARCH_ONLY_DATA_DEGRADED`
- 交付边界：Advisor `BLOCKED`；Risk `NOT_READY`；Owner TG `OFF`
- 总结论：本日没有合格的个股评测记录或推荐。Phase 2 仍为 `NOT_ADMITTED`，次一交易日只保留数据准入、证据时窗与研究结论复核观察池。

## 当日假设、观察与实际证据

| 当日假设/观察 | 实际证据 | 判定 |
| --- | --- | --- |
| 多源市场状态值得交叉验证，但任何 freshness、coverage 或跨源不一致都应推翻“已就绪”。 | 09:36 的受控刷新只覆盖 pytdx/Sina 的 quote、1m、index，共 30 个 probe；daily/5m 仍是保留的历史证据。正式能力矩阵仍为 `NOT_ADMITTED`。 | 风控假设成立；“市场已就绪”不成立。 |
| quote、1m、index 的早盘实时证据可能恢复。 | 1m 与 index 形成 pytdx/Sina 两个可观察独立组；但 quote 两源 consistency 都是 `0.75 < 0.80`，正式矩阵因此不给 quote 生产源。 | 部分成立。恢复的是可观测性，不是完整准入。 |
| daily_kline 与 minute_kline_5m 可由 Baostock/pytdx 交叉验证。 | 矩阵列出两个独立组，但这些 probe 没有在当日增量刷新；Baostock 两项 freshness `0.0`、consistency `0.5`，pytdx 两项 freshness `0.0`，且 5m consistency `0.5`。 | 不能作为当日收盘事实；仅是历史/研究证据。 |
| 固定池中的 BSE 样本 `430047` 会暴露覆盖边界。 | 当日 quote/1m：pytdx 为 `pytdx_host_pool_exhausted`；Sina 分别返回 `2026-06-25`、`2025-09-30` 的陈旧日期。 | 成立。BSE 覆盖仍是明确缺口。 |
| 公开讨论只能作为上下文，不能成为行情或推荐权威。 | 收盘窗口雪球和新浪为 `URLError`，东方财富股吧虽可访问但没有上游条目时间戳；独立可用内容源计数为 0。 | 成立，保持 `NO_OBSERVABLE_SENTIMENT_SOURCE`。 |
| 当日研究模型可形成可沉积的资料，但不能自动改变生产角色。 | 六个任务完成并归档，沉积 4 个 Pattern、2 个 Constraint；其中模型输出出现“pytdx 是 quote/1m/index 唯一来源”等与正式矩阵不一致的表述。 | 只能作为待复核 Experience；不得覆盖能力矩阵或路由。 |
| 可以形成当日纸面评测与事后复盘。 | DAILY SHIFT 为 `NO_VALID_EVALUATION_PICK`、pick count 0；postmortem 为 `NO_ELIGIBLE_PRIOR_RECORD`。当前虽有隔离 journal 的工作树验收，但运行 daemon 未声明已加载，且无合格上游 D0 record。 | 不成立。不得事后补写股票、价格、收益或胜率。 |

## 赢在哪里

1. **准入门保持正确。** 部分 quote/1m/index probe 成功没有被等同于 Phase 2；Finance 继续 `DEGRADED`，Advisor/Risk/TG 保持关闭。
2. **相较昨日，实时证据边界更清楚。** 当日 09:36 真实刷新了 pytdx/Sina 的三项 live operation，并区分了 refreshed 30 条与 retained 88 条，避免把全部 benchmark 误称为当日证据。
3. **quote 的阻断被精确定位。** 两个直接源虽各有 4/5 样本可用，但 consistency 为 `0.75`，低于 `0.80`；不能因 availability 恰好达门而宣称通过。
4. **BSE 与 index 合同被分开。** `430047` 的失败属于个股 quote/1m 覆盖；index 是独立的上证指数合同，不能伪写成“BSE index 失败”。
5. **工作量与模型证据可回放。** 当日 6 个任务依次完成 claim/research/validation/approved/archived；正式 DAILY SHIFT 记录 6 次生产模型调用，6/6 成功。

## 错在哪里或没有做到

1. **收盘仍没有 live refresh。** `close_review.data_refresh=null`；因此 09:36 数据不能代表 15:00 收盘，无法诚实产出个股涨跌、触发/失效或收益复盘。
2. **没有可评测的 D0 个股假设。** 当日 Finance 记录没有完整的 symbol、reference price、point-in-time snapshot、研究假设、失效条件、双独立证据和风险审计；pick 与 postmortem 都只能为 0。
3. **模型研究结论存在过度概括。** RQ-20260828-005 的输出把 pytdx称为若干操作的唯一/主来源，并提出路由性动作；这与正式矩阵中的 Sina 双组证据、quote 无生产源、全局 `NOT_ADMITTED` 冲突。该结论未通过生产接受，不执行其路由建议。
4. **验证反证仍偏弱。** RQ-20260828-003/005 的 Validator 都记录“未主动寻找反例，存在确认偏误风险”；归档或 Guardian `experience/constraint` 不等于事实已独立验证。
5. **当日 benchmark 混合时间域。** quote consistency 仍会与保留的旧 peer 比较；daily/5m 也未当日刷新。它适合暴露缺口，不足以声明当前市场段能力。
6. **公开内容源仍无有效条目级时间戳。** 页面标题、导航与抓取时间不能替代上游 item timestamp；收盘还有两源网络失败。

## 数据缺口

- 缺少 15:00 后对固定池 `600000`、`000001`、`300750`、`688001`、`430047` 的 quote、daily、1m、5m、index 同窗证据。
- quote 的 pytdx/Sina consistency 均为 `0.75 < 0.80`；正式矩阵 production source 为空。
- daily/5m 没有 2026-08-28 增量刷新；Baostock freshness `0.0`、consistency `0.5`，pytdx historical freshness 也为 `0.0`。
- `430047` 的 pytdx host pool exhausted 与 Sina stale-date 尚未恢复。
- 当前 incremental benchmark 仍混合 2026-08-28 refreshed 与历史 retained probes；不能把 round 编号当成同一采样时窗。
- 公开情绪独立内容源为 0；缺条目级上游时间戳，且收盘两源 `URLError`。
- NIM 4 次模型调用成本未知；未知不得记为 0。Shenwen 2 次已知成本合计 USD `0.00965228`。
- 隔离 Paper Evaluation Journal 没有合格生产上游 D0 record；运行 daemon 是否加载当前工作树补丁未被证明。

## 学习候选与 Experience 沉积

- Daily Learning 候选为“考古 Qlib 分钟因子研究边界”，状态 `queued_research`，原因 `requires_independent_miner_review`。本地目录与官方仓库构成两个目录级来源，但 cross-validation 仍为 low/unresolved；它不是已接入能力。
- 当日归档 6 个任务，`completed_work.experience_deposition=true`。知识目录新增 4 个 Pattern、2 个 Constraint；另更新 2 个 skill artifact 与 manifest。沉积数量只证明写入发生，不证明结论已获生产接受。
- 本日应保留的 Finance 经验：
  - live 增量刷新必须与 retained 历史 probe 分窗解释；
  - 单一模型报告、Guardian 归档或 Experience 类型不能覆盖能力矩阵；
  - fixed sample 是观察标签，不是整个市场段 admission；
  - 无合格 D0 record 时，评测、收益和 postmortem 必须保持零结果。

## 次一交易日观察池（2026-08-31，RESEARCH_ONLY）

1. **固定池五项操作同窗复跑**
   - 对象：`600000`、`000001`、`300750`、`688001`、`430047`。
   - 操作：quote、daily_kline、minute_kline_1m、minute_kline_5m、index。
   - 通过条件：每项 availability、coverage、field completeness、freshness、consistency 均 `>=0.8`，具备可观察血缘，并至少有两个独立合格组。
   - 失效条件：任一指标低于 0.8、证据跨时窗、时间戳过期、血缘不可观测或跨源不一致。

2. **quote consistency 专项**
   - 只在同一采样窗口比较独立来源，不把保留的旧 Tencent peer 当成当日对照。
   - pytdx/Sina 任一 consistency 仍低于 `0.80` 时，quote 保持无生产源，Phase 2 不变。

3. **daily/5m 当日性专项**
   - 必须取得当日 market-calendar-aware freshness 证据；历史 probe 只能标记 retained。
   - Baostock/pytdx 的 freshness 或 consistency 任一不达标时，不得以“双组已列出”代替质量通过。

4. **`430047` 覆盖专项**
   - 检查 TDX host pool 是否恢复，Sina quote/1m 日期是否等于有效交易日期。
   - 任一 exhausted/stale 继续出现时，固定池 coverage 不得宣称全通过。

5. **收盘窗口完整性**
   - 保存 15:00 后的收盘证据。若 `close_review.data_refresh` 仍为 null，只能做数据质量复盘，不做个股表现或胜率结论。

6. **研究结论主 Agent 接受**
   - 对“主源/唯一源/生产角色”的模型表述逐项与 matrix、raw probe、时窗和独立组核对。
   - 冲突结论保留为 rejected/watch evidence，不改变路由、不降低阈值。

7. **纸面评测零记录边界**
   - 仅当既有生产上游提交完整 D0 `EVALUATION_ONLY` record 时记录；不得从 research task、历史 brief 或观察池反向合成。
   - 没有完整 snapshot/hash/source refs/hypothesis/invalidation/horizon policy 时继续保持 pick 0、postmortem 0。

## ACE DAILY SHIFT 汇总

- TaskPool 当前快照：blocked 132、archived 557、graveyard 17；无 pending。今日生命周期 claim/research/validation/approved/archived 各 6。
- 模型：正式日累计 6 次生产调用，6/6 成功；NIM reasoning 4 次，Shenwen strategic 2 次；shadow-only，不改变路由或准入。
- 归档/Experience：今日归档 6；Experience 4 Pattern + 2 Constraint；学习候选仍待独立 miner 复核。
- Finance：`DEGRADED`；morning/open/midday/close 均为 `RESEARCH_ONLY`。
- Data：Phase 2 `NOT_ADMITTED`；1m/index 有双组证据，quote consistency 未过，daily/5m 非当日刷新。
- Advisor：`BLOCKED`。
- Risk：`NOT_READY`。
- TG：`OFF`。
- Finance evaluation：0 pick，`NO_VALID_EVALUATION_PICK`；postmortem 0，`NO_ELIGIBLE_PRIOR_RECORD`。
- 下一动作：`record_observation_and_wait_for_independent_evidence`。
- 合成工作：`NO`。

仅供研究与运行治理复盘，不构成投资建议。
