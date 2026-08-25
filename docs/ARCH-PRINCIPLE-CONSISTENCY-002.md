# ARCH-PRINCIPLE-CONSISTENCY-002

## Scope

Principle -> code -> production-evidence consistency audit for the frozen ACE
work boundary.  This report does not add a principle, scheduler, task pool,
router, worker, workload quota, or model-call target.

Audit time: `2026-08-25T12:14:43+08:00`

## Verdict

`CONDITIONALLY_CONSISTENT`

The production lifecycle already demonstrates discovered model Work reaching
Admission, TaskPool, MinerPool, Validator, Guardian, Archivist, and archived
state.  Two implementation/reporting ambiguities were found and repaired in
isolation:

1. Candidate Work with incomplete evidence was rejected by contract parsing
   before ModelTaskAdmission could record the real rejection reason.
2. `no_synthetic_work=true` was an unscoped constant in the allocation report
   and could be mistaken for proof about all upstream producers.

The repaired code is test-verified but has not been loaded into the production
daemon during this audit.

## Principle-Code-Evidence Matrix

| Frozen boundary | Code evidence | Production evidence | Status |
|---|---|---|---|
| Work is discovered, assessed, and accepted; it is not manufactured to satisfy activity quotas | `core/model_work_discovery.py` runs one backlog-independent bounded observation window; `candidate_observation_cap=1` is a cap, not a minimum; candidate sources may return zero | `model_work_discovery_latest.json` recorded one natural candidate and one admitted reasoning task. Daily growth explicitly records `no_growth_quota=true` | PASS, production reload pending for renamed cap |
| Candidate Work may be incomplete; Accepted Work must meet Admission | `core/observation_to_task.py` now accepts an empty candidate evidence list; `core/model_task_admission.py` still rejects fewer than two independent refs before Task creation | Existing one-evidence rejection path was already observed in isolated tests; zero-evidence path now records `independent_evidence_required` and creates no Task | PASS for Candidate/Admission separation; production reload pending |
| Idle / Watch is legal and observation continues | `ModelWorkDiscovery` persists `NO_VALID_MODEL_WORK`; `AutonomousWorkAllocation` can return `NO_VALID_AUTONOMOUS_WORK`; `DailyGrowthLedger` permits `NO_MEASURABLE_GROWTH` | Current cycle had `WORK_AVAILABLE`, so a natural Idle / Watch cycle was not observed in this snapshot | CODE READY; NATURAL IDLE UNOBSERVED |
| Workload does not define Capability | `AutonomousWorkAllocation` classifies existing Work as LOCAL/LEARNING/REASONING/STRATEGIC/EXECUTION/EXPLORATION/FINANCIAL_RESEARCH without creating or dispatching it | Current cycle classified 330 LOCAL, 1 REASONING, 2 EXPLORATION, 0 STRATEGIC, 0 EXECUTION, and 0 FINANCIAL_RESEARCH | PASS |
| MinerPool / models are Execution Fabric | `Researcher` calls `_record_model_execution` only for admitted model-enabled task profiles; health probes are counted separately by `ops/autonomous_audit.py` | Natural task `RQ-20260825-021` made four successful NIM production calls, then reached approved and archived. Shenwen 5.6/5.4 had health calls only and remain production-unverified | PASS for generic ModelPool; SHENWEN PRODUCTION UNVERIFIED |
| Application cannot redefine ACE Core or bypass gates | Stock work enters through `StockDiscoverySources` -> Discovery -> ModelTaskAdmission; Advisor delivery requires Publication, AUTO_PUSH, TG, Data, Risk, and Owner gates | Current health audit reports Data BLOCKED, Advisor BLOCKED, Risk NOT_READY, and no controlled owner delivery readiness | PARTIAL: gates hold, but finance-specific discovery adapters still live under `core/` |
| Repository is source of truth; Git is transport and traceability | Root architecture and civilization maps now define Git as versioned transport/diff/lineage, not an ACE capability or automatic publication grant | Both repository maps preserve `mine-seed` as broad civilization workspace and `ace_core` as distilled production core; no commit or push occurred | PASS at repository-policy layer |
| Work has one governed lifecycle | Existing `TaskPool` states and transition audit remain the only production state machine | `RQ-20260825-021`: pending -> active (`lease_claimed`) -> review -> pending (`validator_rework_pending`) -> active -> review -> approved -> archived; seven evidence records; final Validator outcome approved | PASS |
| Scheduler may trigger observation, but time is not evidence | `ace_daemon.py` invokes daily model discovery inside the existing lifecycle; discovery sources and Admission determine whether Work exists | The daily window observed a real data-health discrepancy, while later cycles recorded `already_discovered_today` without creating another task | PASS |

## Repair Evidence

### Candidate versus Accepted Work

RED:

```text
candidate_count = 0
```

for a zero-evidence Candidate, because candidate-contract parsing rejected it
before Admission.

GREEN:

```text
candidate_count = 1
eligible_count = 0
tasks_created = 0
rejection_reasons = {independent_evidence_required: 1}
```

The evidence threshold was not lowered.  The change only preserves the
Candidate and moves the decision to the existing Admission boundary.

### Synthetic-work assertion scope

Removed the global-looking constant:

```text
no_synthetic_work = true
```

Replaced it with an assertion that matches what this component can actually
prove:

```text
allocation_mode = read_only_existing_work
allocator_created_task_count = 0
no_synthetic_work_by_allocator = true
```

This does not certify every upstream producer.  Source-specific provenance and
Admission remain responsible for that evidence.

## Validation

```text
RED: 2 expected failures
GREEN targeted: 2 passed
Relevant regression: 43 passed
Full ace_core regression: 201 passed
```

`git diff --check` is the final repository-format gate.  No daemon restart,
model call, production Task creation, production task movement, Telegram send,
commit, or push is part of this audit.

## Production Evidence Caveats

1. The archived natural task's four traces predate the currently edited trace
   writer and do not contain persisted `trace_complete=true`; the audit report
   therefore counts four production calls but zero complete traces.  Do not
   rewrite historical traces.
2. The daemon lock points to live Python PID `26788`, while top-level
   `daemon_state.json` still carries stale PID `37644` and an older run ID.
   Runtime was frozen for this audit, so this identity inconsistency was not
   repaired here.  Cycle-level evidence was still completing, but top-level
   process identity must not be used as current-run proof until a separate
   Runtime closure audit resolves the mismatch.
3. The code changes in this audit are not production evidence until a safe,
   separately authorized daemon reload and a natural cycle demonstrate them.

## Remaining Boundary Debt

### Application isolation

`core/stock_discovery_sources.py` and `core/stock_data_reliability.py` are
finance-specific adapters under the Core namespace.  They currently preserve
Admission, Data Health, Risk, Advisor, and Telegram gates, so this is not a
gate-bypass defect.  It is a packaging-boundary debt.

Do not create a second application framework to fix it.  A future minimal
repair should first define the existing adapter seam and then move only the
finance-specific source wiring behind it without changing TaskPool, Router,
Scheduler, or worker semantics.

## Freeze Decision

- Do not add Principle #023 or expand the capability list.
- Keep Principle #022 as a recovered and consolidated Principle, not a new L0
  foundational axiom.
- Do not lower ModelTaskAdmission evidence thresholds.
- Do not manufacture a live Idle cycle or model task for validation.
- Do not claim global `no_synthetic_work` from a component-local constant.
- Do not claim Shenwen production activity from daily health probes.
- Do not enter Advisor or Telegram while Data/Risk remain unready.

Next minimal production validation, when a normal reload is independently
authorized, is one natural cycle proving the scoped allocation fields and one
naturally incomplete Candidate proving Admission rejection without Task side
effects.  Neither event should be manufactured solely for this audit.
