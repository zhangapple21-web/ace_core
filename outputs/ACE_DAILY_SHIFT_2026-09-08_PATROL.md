# ACE DAILY SHIFT — 2026-09-08 patrol

## 09:45 ACE 金融能力日报

`RESEARCH_ONLY / RESEARCH_ONLY_DATA_DEGRADED`

- **观察边界（FACT）**：本次只读取现有 ACE daemon、当天窗口账本、股票数据 benchmark/能力矩阵、Daily Shift，以及 mine-seed 历史 Advisor 对照；不运行旧 Advisor，不创建候选，不改变 Data/Admission/Validator/Risk 门槛，不推荐交易，不发送 Telegram。
- **窗口（FACT）**：`finance_work_windows_latest.json` 的 `open_validation` 记录为 `2026-09-08T09:44:41.417787+08:00`；`window_status=RESEARCH_ONLY`、`finance_status=RESEARCH_ONLY`、`recommendation_allowed=false`、`task_created=false`、`model_call=false`。受控刷新于 `2026-09-08T09:37:03.699932+08:00` 完成，来源 `pytdx`、`sina`，操作 `quote`、`minute_kline_1m`、`index`，30 个 refreshed probes。
- **唯一 daemon（FACT）**：仅有 PID `23320` 的 `pythonw.exe ... C:\tmp\ace_core\ace.py daemon --serve`；`.daemon.lock`、`daemon_state.json`、`heartbeat.json` 均绑定 run `b72c849daa6a42aa97a1c2460287ec47`。进程存活，`run_status=alive`，heartbeat=`alive`，`consecutive_misses=0`，最近周期 `completed`。未启动第二 daemon、Scheduler、TaskPool、Router 或 Worker。

### quote / 1m / index 证据

benchmark `generated_at=2026-09-08T01:37:03.722360+00:00`（本地约 09:37），能力矩阵 `generated_at=2026-09-08T01:37:03.726032+00:00`，`phase_two_admission=NOT_ADMITTED`。下表为 benchmark 的来源级质量观测；数值为 0–1，不能把“有观测”解释成生产准入。

| operation | 独立性 / 准入 | freshness | coverage | field completeness | consistency | 结论 |
|---|---|---:|---:|---:|---:|---|
| `quote` | 刷新观测组为 `tdx_tcp_protocol`（pytdx）与 `sina_public_http`（sina）；矩阵 `production_sources=[]`、无独立交叉验证 | pytdx 0.00；sina 0.80 | pytdx 0.00；sina 0.80 | pytdx 0.00；sina 0.80 | pytdx 0.00；sina 0.25 | **BLOCKED**：`no_qualified_production_source`、`independent_cross_validation_missing` |
| `minute_kline_1m` | 刷新观测组为 pytdx + sina；矩阵 `production_sources=[]`、无独立交叉验证 | pytdx 0.00；sina 0.60 | pytdx 0.00；sina 0.60 | pytdx 0.00；sina 0.60 | 两源均 0.00 | **BLOCKED**：无合格生产源、独立交叉验证缺失 |
| `index` | 刷新观测组为 pytdx + sina；矩阵 `production_sources=[]`、无独立交叉验证 | pytdx 0.00；sina 1.00 | pytdx 0.00；sina 1.00 | pytdx 0.00；sina 1.00 | pytdx 0.00；sina 0.00 | **BLOCKED**：无合格生产源、独立交叉验证缺失 |

能力矩阵五项核心操作均未完成总门槛：`quote`、`minute_kline_1m`、`index` 没有合格生产源；`daily_kline` 和 `minute_kline_5m` 仅保留 `baostock` 单一生产观测；五项共同缺 `independent_cross_validation`。`finshare` 上游血缘不可观测，只能研究用途；其余 source-level 可用性不改变总准入。刷新覆盖部分实时观测，不等于完成 Phase 2。

### freshness / coverage / completeness / consistency 总结

- **Freshness**：只有 sina quote/1m/index 的部分 endpoint freshness 观测达到 0.60–1.00；pytdx 本次三项均为 0.00，不能形成双源实时一致证据。
- **Coverage**：sina quote/1m/index 分别为 0.80/0.60/1.00；pytdx 三项均为 0.00。其余核心操作仍非本窗口完整刷新。
- **Field completeness**：与 coverage 同步受限；pytdx 三项为 0.00，sina 为 0.80/0.60/1.00。
- **Consistency**：quote 为 pytdx 0.00、sina 0.25；1m 两源 0.00；index 为 pytdx 0.00、sina 0.00。不能据此宣称跨源一致。

### 舆情与市场状态

- `public_sentiment.status=NO_OBSERVABLE_SENTIMENT_SOURCE`、`independent_content_source_count=0`、`admission_ready=false`。雪球与新浪财经页面有快照，但上游条目时间戳不可观察；东方财富股吧在 open-validation 为 `unavailable (URLError)`，不构成独立、可审计的情绪准入证据。
- 当前市场状态保持 `RESEARCH_ONLY_DATA_DEGRADED`。只有 `quote`、`daily_kline`、`minute_kline_1m`、`minute_kline_5m`、`index` 五项都具备生产来源、独立交叉验证，并同时满足 freshness、coverage、字段完整性和跨源一致性，才可改变该状态；任一证据过期、血缘不可观测、覆盖/字段不足或冲突，当前结论继续有效。

### Advisor / Risk / TG / AUTO_PUSH

- **Advisor**：`BLOCKED`。历史 mine-seed `runner_status.json` 的 `last_run_time=2026-07-14T09:38:35.314490`、`last_run_success=false`、`health_score=45.0`、`recommendations=[]`；仅作历史对照，未运行旧 Advisor。
- **Risk**：`NOT_READY`。`C:\tmp\mine-seed\05_TOOLS\mine_output\advisor\risk_status.json` 不存在；当天 blocking ledger 原因是 `risk_evidence_missing_or_malformed`。
- **TG**：`owner_tg=OFF`、`publication_authority=false`。当天 blocking ledger 记录 `automation_or_telegram_state_unavailable`；本次未发送 Telegram。
- **AUTO_PUSH**：`UNKNOWN/UNAVAILABLE`。`ACE_STOCK_ADVISOR_AUTO_PUSH` 的运行时状态不可验证，不能把不可用推断成已执行或已关闭；本次无外发。

### 历史 Advisor 与纸面评测合同

- 历史 `advisor_20260710/11/13/14_lineage.json` 均为 `mvp-v1`，快照在 2026-07，来源为单一 `tencent` 或 `eastmoney`；只含 signal 组合和价格字段，缺少 R2 所需研究 hypothesis、失效条件、两个独立 evidence refs 和风险审计，不能复用为今天的评测候选，也不当作今天结果。
- 代码级 `C:\tmp\ace_core\core\paper_evaluation_journal.py` 定义了隔离的 `EVALUATION_ONLY` 契约（数据快照 hash、`source_refs`、hypothesis、invalidating conditions、冻结 horizon 等），但运行时 `C:\tmp\ace_core\06_RUNTIME\ace\data\paper_evaluations\` 目录及 `journal.json` 均不存在。Daily Shift 为 `recorded_count=0`、`outcome_receipt_count=0`、`postmortem_status=NO_ELIGIBLE_PRIOR_RECORD`；代码存在不等于已有可追溯 R2 合同。

### 今日候选判定

**结论：0 条 `EVALUATION_ONLY / NOT_FOR_LIVE_TRADING`（目标 2 只是上限，不是配额）。**

Exact blockers：

1. 当前不存在可追溯的 R2 纸面评测提交源或运行时 journal。
2. Phase 2=`NOT_ADMITTED`；quote/1m/index 无合格生产源和独立交叉验证，daily/5m 也只有单组生产观测。
3. 无法为任何候选同时提供今天的实时数据快照、研究假设、失效条件、两个独立 evidence refs 和风险审计。
4. Advisor 历史运行失败且陈旧，Risk 证据缺失，TG/AUTO_PUSH 状态不可验证；不能用历史结果、页面快照或缺失字段补齐候选。

下一验证：沿用唯一现有 daemon，在下一交易观察窗口复跑同一固定股票池与五项核心操作，重新核对来源血缘、时间戳、freshness、coverage、field completeness、consistency；在完整 R2 合同和逐候选证据出现前保持 `0` 条。

本次仅写入日报；未运行旧 Advisor、未制造候选、未改变 Data/Admission/Validator/Risk 门槛、未推荐交易、未发送 Telegram，未创建第二套 Scheduler/TaskPool/Router/Worker。

## 12:31 ACE 午盘复核验收

`RESEARCH_ONLY / RESEARCH_ONLY_DATA_DEGRADED`

- **唯一生产 daemon 身份（FACT）**：`memory/daemon_state.json`、`memory/heartbeat.json` 与 `.daemon.lock` 均绑定 PID `23320`、run `b72c849daa6a42aa97a1c2460287ec47`；进程存活、`run_status=alive`、heartbeat=`alive`、`consecutive_misses=0`，本次未启动第二 daemon、Scheduler、Router 或 Worker。
- **窗口账本已写入（FACT）**：`finance_work_windows_latest.json` 的 `midday_review.observed_at=2026-09-08T12:31:31.555016+08:00`，`window_status=RESEARCH_ONLY`、`finance_status=RESEARCH_ONLY`、`data_refresh_attempted=false`、`data_refresh=null`、`observation_recorded=true`（`observation_id=OBS-20260908-3972`）。早盘 `09:37:03` 的 pytdx/sina 受控刷新只覆盖部分 `quote`、`minute_kline_1m`、`index` 观测，不等同于午盘完整实时准入证据。
- **市场状态（FACT）**：`RESEARCH_ONLY_DATA_DEGRADED`；Phase 2=`NOT_ADMITTED`。`quote`、`minute_kline_1m`、`index` 没有合格生产源和独立交叉验证，`daily_kline`、`minute_kline_5m` 仅保留单组 baostock 生产观测，五项共同缺少独立交叉验证；finshare 上游血缘不可观测，不能作为独立交叉验证。部分来源恢复不改变总门槛。
- **舆情证据（FACT）**：`public_sentiment.status=NO_OBSERVABLE_SENTIMENT_SOURCE`、`independent_content_source_count=0`、`admission_ready=false`；雪球、东方财富股吧与新浪财经快照缺少可观察上游条目时间戳，不能构成独立、可审计的市场方向或候选准入证据。
- **反证**：① 早盘刷新仅覆盖三项操作，午盘未新增刷新；② 五项核心操作仍缺生产/独立交叉验证，baostock 单源与 finshare 血缘缺口不能补齐；③ 舆情页面无可审计条目时间戳，不能把页面快照当作独立情绪信号。
- **失效条件**：只有 `quote`、`daily_kline`、`minute_kline_1m`、`minute_kline_5m`、`index` 五项均具备生产来源并完成独立交叉验证，同时满足 freshness、coverage、字段完整性和跨源一致性门槛，才可改变 `DEGRADED`；任一证据过期、覆盖率/字段完整性不足、血缘不可观测或跨源不一致，当前结论继续有效。
- **下一验证**：下一交易观察窗口沿用同一固定股票池复跑五项核心操作，重新核对来源血缘、时间戳、freshness、coverage、field completeness、consistency；在完整证据出现前保持 `NOT_ADMITTED` 与 `record_observation_and_wait_for_independent_evidence`。
- **Admission / outbound guard（FACT）**：本窗口 `evaluation_pick_count=0/2`、`publication_authority=false`、`task_created=false`、`model_call=false`、`recommendation_allowed=false`；Advisor=`BLOCKED`、Risk=`NOT_READY`、Owner TG=`OFF`、`no_synthetic_work=true`。本次午盘复核未制造候选、TaskPool 项、模型调用、荐股或 TG 发送。
- **TaskPool 边界（FACT）**：Daily Shift 快照为 `blocked=139`、`archived=579`、`graveyard=17`，今日生命周期计数为 `claim/research/validation/approved/archived=1/1/1/1/1`；这些是现有一般生命周期/维护记录，不是本午盘复核创建，也不是金融推荐候选，`production_integration=false`。本窗口没有候选进入 TaskPool。
- **验收证据**：针对性 `pytest`（finance windows、daily shift、finance-shift contract、runtime identity、data admission recovery、model/task admission、task admission）`44 passed in 1.66s`；未编辑生产源码。
