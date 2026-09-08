# ACE DAILY SHIFT — 2026-09-06 patrol

## 09:45 ACE 金融能力日报

`RESEARCH_ONLY / RESEARCH_ONLY_DATA_DEGRADED`

- **观察边界（FACT）**：2026-09-06 是周日。`finance_work_windows_latest.json` 最近记录为 `open_validation`，`observed_at=2026-09-06T09:54:22.916165+08:00`；窗口为 `RESEARCH_ONLY`、`finance_status=DEGRADED`、`market_state=RESEARCH_ONLY_DATA_DEGRADED`，`recommendation_allowed=false`、`task_created=false`、`model_call=false`、`data_refresh=null`。今天只观察到 `morning_observation` 与 `open_validation`，`midday_review/close_review/next_day_watchlist` 缺失；不把周末或历史快照写成盘中实时行情。
- **唯一 daemon（FACT）**：当前仅发现一个 `ace.py daemon --serve` 进程，PID `43004`。`memory/daemon_state.json`、`memory/heartbeat.json` 与 `.daemon.lock` 均绑定 run `54ac1e2004444aa28f45dedd897d0d46`；heartbeat=`alive`、`consecutive_misses=0`，本次 cycle=`completed`。未启动第二 daemon、Scheduler、TaskPool、Router 或 Worker。

### quote / 1m / index 证据

下表是当前可用的最新 benchmark（生成于 `2026-09-02T09:36:27.977480+08:00`）的源级质量字段；今天没有新的 `data_refresh`，所以它们不是 2026-09-06 的实时快照。

| operation | 独立性/准入 | freshness | coverage | field completeness | consistency | 结论 |
|---|---|---:|---:|---:|---:|---|
| `quote` | benchmark 观测到 `pytdx/tdx_tcp_protocol` 与 `sina/sina_public_http`，但能力矩阵 `production_sources=[]`、独立交叉验证=`false`；`finshare` 血缘不可观测 | pytdx 0.8；sina 0.8 | pytdx 0.8；sina 0.8 | pytdx 0.8；sina 0.8 | pytdx 0.5；sina 0.5 | **BLOCKED**：`NO_QUALIFIED_PRODUCTION_SOURCE`、`INDEPENDENT_CROSS_VALIDATION_MISSING` |
| `minute_kline_1m` | `pytdx/tdx_tcp_protocol` + `sina/sina_public_http`，矩阵标为 READY 且有独立交叉验证；但 Phase 2 总体仍未准入 | pytdx 0.8；sina 0.8 | pytdx 0.8；sina 0.8 | pytdx 0.8；sina 0.8 | pytdx 1.0；sina 1.0 | 仅为历史 benchmark 级部分能力 |
| `index` | `pytdx/tdx_tcp_protocol` + `sina/sina_public_http`，矩阵标为 READY 且有独立交叉验证；但 Phase 2 总体仍未准入 | pytdx 0.8；sina 1.0 | pytdx 1.0；sina 1.0 | pytdx 0.8；sina 1.0 | pytdx 1.0；sina 1.0 | 仅为历史 benchmark 级部分能力 |

能力矩阵当前 `phase_two_admission=NOT_ADMITTED`；`daily_kline`、`minute_kline_1m`、`minute_kline_5m`、`index` 虽有部分双组观测，不能绕过 `quote` 阻塞。`public_sentiment` 的三个页面快照均无法观察上游条目时间戳，`independent_content_source_count=0`、`admission_ready=false`、`status=NO_OBSERVABLE_SENTIMENT_SOURCE`。

### Advisor / Risk / TG / AUTO_PUSH

- **Advisor**：Daily Shift=`BLOCKED`；审计交叉检查将 mine-seed 外部证据标为 `NOT_READY`，原因是历史 runner 证据陈旧。未运行旧 Advisor。
- **Risk**：`NOT_READY`。历史对照路径所指 `C:\tmp\mine-seed\05_TOOLS\mine_output\advisor\risk_status.json` 不存在；审计原因为 `risk_evidence_missing_or_malformed`。
- **TG**：Daily Shift `owner_tg=OFF`、`publication_authority=false`；审计域仍标记 `NOT_READY`，因为当前自动化/Telegram 状态不可用。未发送 Telegram。
- **AUTO_PUSH**：当前没有可验证的运行时开关或发送记录；审计明确记录 `automation_or_telegram_state_unavailable`，故保持 `UNKNOWN/UNAVAILABLE`，不推断为已关闭或已执行。

### 历史 Advisor 与纸面评测合同

- `runner_status.json`（最后运行 `2026-07-14T09:38:35.314490`）显示 `last_run_success=false`、`health_score=45.0`、`recommendations=[]`；它是外部历史对照，不是今天的运行结果。
- 2026-07 的四份 lineage 均为 `mvp-v1`，每条只有单一 `tencent` 或 `eastmoney` source、signal 组合和价格字段；缺少 R2 所需的研究 hypothesis、失效条件、两个独立 evidence refs 与风险审计，因此**不可复用为今天候选**。
- 代码级 `core/paper_evaluation_journal.py` 确实定义了隔离的 `EVALUATION_ONLY` 记录契约（快照 hash、source refs、hypothesis、失效条件、冻结 horizon 等），但运行时 `06_RUNTIME\ace\data\paper_evaluations\` 目录及 `journal.json` 均不存在，Daily Shift 也记录 `recorded_count=0`、`outcome_receipt_count=0`、`postmortem_status=NO_ELIGIBLE_PRIOR_RECORD`。因此不能把“有代码契约”升级成“已有可追溯记录”。

### 今日候选判定

**结论：0 条 `EVALUATION_ONLY / NOT_FOR_LIVE_TRADING`（目标 2 只是上限，不是配额）。**

Exact blockers：

1. 没有今天可追溯的 R2 纸面评测记录/提交源；`paper_evaluations` journal 缺失。
2. `quote` 无合格生产源且无独立交叉验证，故 Phase 2=`NOT_ADMITTED`；今天也没有实时数据 refresh。
3. 不能为任一候选同时提供今天的实时快照、研究假设、失效条件、两个独立 evidence refs 和风险审计。
4. Advisor 历史失败且陈旧、Risk 证据缺失、TG/AUTO_PUSH 状态不可验证；不得以旧结果或缺口字段补齐候选。

下一验证：沿用现有 daemon，在下一交易观察窗口复跑同一固定股票池与五项核心操作，重新核对来源血缘、时间戳、coverage、field completeness、consistency，并在出现完整 R2 合同与逐候选证据前保持 `0` 条。

本次仅写入日报；未运行旧 Advisor、未创建候选、未改变 Data/Admission/Validator/Risk 门槛、未发送 Telegram，未创建第二套 Scheduler/TaskPool/Router/Worker。

## 12:32 ACE 午盘复核验收

`RESEARCH_ONLY / RESEARCH_ONLY_DATA_DEGRADED`

- **唯一生产 daemon 身份（FACT）**：`memory/daemon_state.json`、`memory/heartbeat.json` 与 `.daemon.lock` 仍绑定 PID `43004`、run `54ac1e2004444aa28f45dedd897d0d46`；进程存活、heartbeat=`alive`、`consecutive_misses=0`，本次未启动第二 daemon、Scheduler、Router 或 Worker。
- **窗口账本已写入（FACT）**：`finance_work_windows_latest.json` 的 `midday_review.observed_at=2026-09-06T12:32:47.887690+08:00`，`window_status=RESEARCH_ONLY`、`finance_status=DEGRADED`、`data_refresh_attempted=false`、`data_refresh=null`。今天是周日，非交易日；不把历史 benchmark 或周末页面快照当作盘中实时行情。
- **市场状态（FACT）**：`RESEARCH_ONLY_DATA_DEGRADED`。能力矩阵最后生成于 `2026-09-02T09:36:27.977480+08:00`，Phase 2=`NOT_ADMITTED`；`quote` 仍无生产来源且 `has_independent_cross_validation=false`，未覆盖完整五项核心操作。`daily_kline`、`minute_kline_1m`、`minute_kline_5m`、`index` 的部分双组记录不能绕过 `quote` 阻塞；`baostock` 一致性缺口与 `finshare` 血缘不可观测仍保留。
- **舆情证据（FACT）**：`public_sentiment` 仅有页面快照，上游条目时间戳不可观察；`independent_content_source_count=0`、`status=NO_OBSERVABLE_SENTIMENT_SOURCE`、`admission_ready=false`，不构成市场方向或候选准入证据。
- **反证**：① 既有 pytdx/sina 受控观测只覆盖部分 `quote/1m/index`，且本窗口没有新的行情 refresh；② 日线/5m 的一致性与 `finshare` 血缘缺口仍未消除；③ 周日无 A 股交易，不能从旧快照推断午盘盘面。
- **失效条件**：只有当 `quote`、`daily_kline`、`minute_kline_1m`、`minute_kline_5m`、`index` 五项均具备生产来源并完成独立交叉验证，同时满足 freshness、coverage、字段完整性和跨源一致性门槛，才可改变 `DEGRADED`；任一证据过期、血缘不可观测或跨源不一致，当前结论继续有效/保持失效。
- **下一验证**：下一交易观察窗口复跑同一固定股票池与五项核心操作，重新核对来源血缘、时间戳、覆盖率、字段完整性和一致性；在此之前保持 `NOT_ADMITTED` 与 `record_observation_and_wait_for_independent_evidence`。
- **Admission / outbound guard（FACT）**：`evaluation_pick_count=0/2`、`publication_authority=false`、`task_created=false`、`model_call=false`、`recommendation_allowed=false`；Advisor=`BLOCKED`、Risk=`NOT_READY`、Owner TG=`OFF`、`no_synthetic_work=true`。本次午盘复核未制造候选、TaskPool 项、模型调用、荐股或 TG 发送。
- **TaskPool 边界（FACT）**：Daily Shift 当前快照为 `blocked=139`、`archived=576`、`graveyard=17`，今日 `claim/research/validation/approved/archived=0`；仅允许满足现有 Admission 的候选进入 TaskPool，本窗口没有候选进入。
- **验收证据**：针对性 `pytest`（finance windows、daily shift、finance-shift contract、runtime identity、data admission recovery、model/task admission）`38 passed in 1.64s`；未编辑生产源码。
