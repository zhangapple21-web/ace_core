# ACE 收盘复盘与次日观察池 — 2026-08-27

- 复盘时点：2026-08-27 15:20:36 +08:00
- 正式班次：`06_RUNTIME/ace/data/daily_shift_latest.json`
- 运行身份：PID `30428`，run `8b85e3f942a243be9fee8f570eb430ee`，唯一生产 daemon
- 研究状态：`RESEARCH_ONLY_DATA_DEGRADED`
- 交付边界：Advisor `BLOCKED`；Risk `NOT_READY`；Owner TG `OFF`
- 结论：本日没有达到 ACE 准入门的个股推荐，也没有可诚实计算的个股假设命中率。次日仅保留数据准入与证据验证观察池。

## 当日假设、观察与实际证据

| 当日假设/观察 | 实际证据 | 判定 |
| --- | --- | --- |
| 当前金融观察只能形成有边界的市场状态与数据质量结论，不能形成推荐。 | 收盘窗口仍为 `RESEARCH_ONLY`，Finance 为 `DEGRADED`，Advisor 为 `BLOCKED`，Risk 为 `NOT_READY`。 | 成立。生产门与交付门保持关闭。 |
| 需要在后续窗口比较既有来源证据，确认哪些字段仍阻断实时验证。 | 09:33–09:35 的受控增量刷新对 pytdx/Sina 的 quote、1m、index 共刷新 30 个 probe；但只跑了 1 轮，且未在收盘窗口刷新。 | 部分完成。得到早盘证据，不足以代表收盘状态。 |
| 公开讨论只能作为待交叉验证上下文，不能成为行情或荐股权威。 | 收盘抓取了雪球、东方财富股吧、新浪财经页面，但三者均无可观测的上游条目时间戳；独立可用内容源计数为 0。 | 成立。状态为 `NO_OBSERVABLE_SENTIMENT_SOURCE`。 |
| Phase 2 需要五项核心操作的质量门和独立交叉验证全部通过。 | 能力矩阵仍为 `NOT_ADMITTED`。quote、1m 出现双组早盘证据；daily/5m 的 freshness 与 consistency 仍不足；index 未形成合格的第二独立组。北交所样本 `430047` 同时出现 TDX host pool exhausted 与 Sina stale-date。 | 未通过。不得改变准入状态。 |

## 赢在哪里

1. **风控判断正确。** 系统没有把部分成功 probe 等同于生产准入，没有创建金融任务、没有生成推荐、没有发送 TG。
2. **“完全不可用”被更精确地修正。** pytdx/Sina 在固定池的 quote、1m、index 上恢复了部分早盘证据，说明问题是“能力不完整且质量门未齐”，不是所有数据源都不可用。
3. **证据链可追溯。** 能力矩阵、benchmark、公开页面快照、Finance 窗口和 OBS-20260827-1215 均留下时间戳与引用。
4. **运行工作有可核对结果。** 当日归档 108 个任务，生产模型调用 4 次尝试/4 次成功；TaskPool 当日生命周期为 claim/research/validation 各 352，approved/archived 各 108。

## 错在哪里或没有做到

1. **没有收盘行情刷新。** `close_review` 的 `data_refresh` 为 null；因此不能把 09:35 的 probe 当作 15:00 收盘行情，也不能做个股涨跌复盘。
2. **没有可回测的个股假设。** 当日正式记录只有数据准入研究问题，没有股票、触发价、失效价或仓位假设；因此“选股赢/错”均应报告为不可评估，而不是事后补写。
3. **公开情绪来源未形成有效内容证据。** 页面可访问不等于可用；缺少上游条目时间戳，独立内容源仍为 0。
4. **Phase 2 仍有结构性缺口。** daily_kline、minute_kline_5m 的 freshness/consistency 未达标，index 的合格独立交叉验证不足，`430047` 暴露覆盖和陈旧数据问题。
5. **模型成本证据不完整。** NIM 两次调用成本未知；不能把未知成本记作 0。Shenwen 两次调用记录成本合计 USD 0.01000076。

## 数据缺口

- 收盘窗口没有 live refresh，缺少同一固定股票池的 15:00 后 quote、daily、1m、5m、index 对照。
- 当前 benchmark 仅 1 轮；不满足连续、多轮、固定间隔稳定性验证。
- Baostock 的 daily/5m freshness 为 0、consistency 为 0.5。
- pytdx 在 `430047` 上出现 `pytdx_host_pool_exhausted`；Sina 对同一标的返回 2026-06-25/2025-09-30 的陈旧日期。
- 公开情绪页面缺少可观测的上游条目时间戳，不能进入独立内容证据计数。
- NIM 调用账单未知，成本汇总仍不完整。

## 学习候选与 Experience 沉积

- Daily Learning 选择内部候选“考古 Alphalens 风格因子验真方法”，状态 `queued_research`，原因 `requires_independent_miner_review`；外部发现为 `NOT_NEEDED_INTERNAL_CANDIDATE`。它尚不是已验证经验或生产能力。
- 当日任务归档 108 个，`completed_work.experience_deposition=true`；知识目录当日新增/更新 Pattern 60、Constraint 48，另有 Skills 3 与索引 1。这里记录的是沉积数量，不推断每条都已独立验证。
- 本日最值得沉积的 Finance 经验：单轮/单操作成功不构成 Phase 2 准入；陈旧日期和不可观测血缘必须 fail closed；收盘复盘必须区分早盘 probe 与收盘事实。

## 次日观察池（2026-08-28，RESEARCH_ONLY）

1. **固定池五项操作复跑**
   - 对象：`600000`、`000001`、`300750`、`688001`、`430047`。
   - 操作：quote、daily_kline、minute_kline_1m、minute_kline_5m、index。
   - 通过条件：availability、coverage、field completeness、freshness、consistency 各项均 `>= 0.8`，且每项至少两个可观察血缘的独立组。
   - 失效条件：任一项低于 0.8、时间戳过期、血缘不可观测或跨源不一致。

2. **`430047` 覆盖专项**
   - 验证 TDX host pool 是否恢复，并核对 Sina 返回日期是否为当日交易日期。
   - 若任一来源继续 exhausted/stale，不得把全固定池 coverage 记为通过。

3. **收盘窗口完整性**
   - 必须保存 15:00 后的收盘证据；若 `close_review.data_refresh` 仍为 null，只能继续产出数据质量复盘，不能产出个股表现结论。

4. **公开内容证据**
   - 仅统计带上游条目时间戳、可追溯来源与独立 upstream identity 的内容。
   - 论坛/社区页若只有页面标题或导航文本，继续保留为 `UNVERIFIED_CONTEXT`。

5. **学习候选独立复核**
   - 只通过现有 Daily Learning、Admission 与 TaskPool 路径验证 Alphalens 候选。
   - 没有独立 miner 证据时保持 `queued_research`，不得为活跃度制造模型调用或新任务。

## ACE DAILY SHIFT 汇总

- TaskPool：blocked 124、archived 448、pending 18、graveyard 17；当日归档 108。
- 模型：生产调用 4/4 成功；NIM reasoning 2 次，Shenwen strategic 2 次；报告为 shadow-only，不改变路由与准入。
- 归档/Experience：归档 108；Experience deposition 已发生，但学习候选仍待独立复核。
- Finance：`DEGRADED`，close window `RESEARCH_ONLY`。
- Data：Phase 2 `NOT_ADMITTED`；早盘部分恢复，收盘未刷新。
- Advisor：`BLOCKED`。
- Risk：`NOT_READY`。
- TG：`OFF`。
- 下一动作：`record_observation_and_wait_for_independent_evidence`。
- 合成工作：`NO`。

仅供研究与运行治理复盘，不构成投资建议。
