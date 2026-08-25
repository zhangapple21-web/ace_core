# AUM-MISSION-AUTOMATION-OBSERVABILITY-013 Design

## Objective

Build an external, read-only ACE production audit toolchain. It shall collect persisted runtime evidence, produce a daily health report, classify operational readiness, detect trends, and recommend one next action without altering business runtime behavior.

## Scope

The command is:

```text
python ops/run_autonomous_audit.py
```

The command may read:

- heartbeat and daemon state files
- daemon lock metadata
- TaskPool task records
- persisted model task admission and execution traces
- Data Health benchmark and incident records
- persisted Advisor and Risk state records
- existing Telegram, AUTO_RUN, and AUTO_PUSH configuration values

The command writes only audit report files under `06_RUNTIME/ace/data/audits/` and its own history directory.

## Non-Goals and Safety Constraints

The audit tool shall not:

- import or instantiate `AceDaemon`
- call a Provider, Router, `MinerPool`, or model API
- create, claim, update, archive, or delete TaskPool tasks
- start, stop, lock, unlock, or otherwise control the daemon
- send Telegram messages
- alter AUTO_RUN, AUTO_PUSH, or Telegram configuration
- modify production files owned by current 012 work
- scan backups as evidence of current runtime state

A missing, malformed, or unavailable source is reported as an evidence limitation. It must not be inferred as a healthy state.

## Data Sources

The audit collector directly parses persisted JSON and JSONL files. It treats TaskPool files in active runtime locations as current state and ignores backup directories. It does not use task mutation APIs.

Each source is recorded with its path, observed timestamp where available, parse outcome, and freshness evaluation. The collector isolates failures per source so one malformed file cannot prevent the rest of the report.

## Output Layout

The audit directory is `06_RUNTIME/ace/data/audits/`:

```text
daily_health.json
daily_health.md
blocking_reasons.json
trend_report.json
history/YYYY-MM-DD/daily_health.json
history/YYYY-MM-DD/blocking_reasons.json
history/YYYY-MM-DD/trend_report.json
```

The four fixed files represent the most recent successful audit. The history directory stores immutable daily JSON snapshots. Records older than 90 calendar days are deleted only from `history/`; no runtime data is deleted.

## Readiness Model

Every audit domain has one of these states:

- `READY`: required current evidence is available and no blocking condition applies.
- `NOT_READY`: evidence is missing, malformed, stale, incomplete, or cannot support the required conclusion.
- `BLOCKED`: a known persisted condition prevents work from progressing.

Every non-ready result includes stable reason codes, evidence paths, and one recommended action. The overall state is the most severe domain state: `BLOCKED`, then `NOT_READY`, then `READY`.

## Domain Reports

### Runtime

Read heartbeat, daemon state, and daemon lock data. Report source freshness, cycle stage, PID/lock consistency, and whether a completed cycle exists. A stale or mismatched state is `NOT_READY`; a persisted failed cycle or lock conflict is `BLOCKED`.

### Task Lifecycle and Backlog

Read current TaskPool records and aggregate count, priority, age, and lifecycle activity across pending, active, blocked, review, approved, and archive. Capture claim, research, validation, rework, approved, and archive evidence from the persisted record fields and outputs when present.

### Fairness and Starvation

Flag high-priority pending tasks that exceed the configured waiting threshold, active tasks that exceed expected lifecycle age, and priority cohorts with disproportionate wait time. A starvation finding is `BLOCKED` only when a task is persistently eligible yet unserved; otherwise it is `NOT_READY` when timing evidence is insufficient.

### Model Calls

Execution traces are classified strictly as one of:

- `HEALTH_PROBE`: provider health, readiness, watchdog, or key-health evidence.
- `CONTROLLED_PROBE`: explicitly controlled test or verification evidence.
- `PRODUCTION_TASK_CALL`: an execution trace attached to a current task whose persisted `model_task_admission` is eligible reasoning and whose tags contain `task_type:reasoning`.

Only `PRODUCTION_TASK_CALL` contributes to production model totals, provider totals, selected-model totals, API call counts, fallback counts, and trace completeness. The report aggregates actual selected models matching Shenwen 5.6 and 5.4 strings without imposing a routing expectation.

### Data Health

Read the latest current Data Health benchmark and incident records. Report source metrics for availability, completeness, coverage, and consistency, and identify degraded or missing evidence. No market or financial query is executed.

### Advisor, Risk, and Telegram

Read persisted Advisor and Risk state where available, and report their observed state and freshness. Read Telegram, AUTO_RUN, and AUTO_PUSH configuration values without changing them. Missing sources are explicitly `NOT_READY`; the audit never treats absence as disabled or enabled.

### Trends and Recommended Action

Trend computation reads only previous audit snapshots within the 90-day retention window. It compares current and prior values for TaskPool backlog, blocked tasks, starvation findings, lifecycle transitions, Data Health, and production calls. It emits anomalies for sustained degradation, rising backlog, repeated blockage, or declining evidence freshness.

The report selects exactly one recommended action using severity and evidence order:

1. repair a runtime or lock blocker;
2. resolve a persisted TaskPool blocker or starvation finding;
3. repair missing or stale observation evidence;
4. resolve Data Health degradation;
5. investigate sustained adverse trend;
6. continue normal observation.

The recommendation is advisory only and cannot trigger an action.

## Automation

After manual command validation and tests pass, create one daily automation at 09:00 local time. It runs the existing audit command and persists reports silently. The schedule itself neither starts the daemon nor sends notifications.

## Verification

Tests use isolated temporary directories and synthetic persisted files. They verify:

- no mutation of TaskPool, runtime config, daemon state, or notification state;
- health probes and controlled probes are not counted as production calls;
- valid admitted reasoning traces are counted as production calls;
- model aggregation reflects actual selected-model values;
- lifecycle, rework, fairness, and starvation summaries are deterministic;
- missing and malformed sources produce non-ready evidence rather than exceptions;
- all fixed reports, daily history snapshots, and 90-day retention work correctly;
- trend findings and recommended action are derived only from persisted audit history.
