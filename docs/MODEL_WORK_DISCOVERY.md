# Model Work Discovery

## Boundary

`ModelWorkDiscovery` is a bounded coordinator over the existing discovery and
admission path. It is not a scheduler, worker, router, or model caller.

```text
existing observation/discovery sources
  -> DiscoveryCandidate
  -> DiscoveryMode observation
  -> ObservationToTaskConverter
  -> ModelTaskAdmission
  -> existing TaskPool / Researcher / MinerPool lifecycle
```

Once per local calendar day it permits candidate inspection independently of
LOCAL backlog. Zero candidates is a valid result and is persisted as
`NO_VALID_MODEL_WORK`. At most one candidate observation is created per run;
fingerprint and incident state continue to prevent duplicate open work.

Candidate observations may start with incomplete evidence so unresolved but
worthwhile questions remain observable. They do not enter TaskPool on that
basis. Every admitted candidate must have a research question, expected result,
verification method, bounded risk/scope, and at least two distinct evidence
references. A health probe is evidence at most; it is never a production model
call by itself.

## Existing source inventory

| Domain | Existing artifact or producer | Current candidate wiring | Status / minimum gap |
|---|---|---|---|
| External Learning | `WebScout` external items and canonical URLs | Creates legacy external tasks directly | PARTIAL: require a real cross-source question and two independent canonical URLs before using the shared admission path |
| Daily Summary / System Review | Daily summary and daemon state artifacts | No model candidate rule | PARTIAL: emit only for a material unexplained delta/anomaly, not every summary |
| Semantic Slice | Local slice clustering and memory output | Local producer only | LOCAL: candidate only for unresolved cross-cluster synthesis supported by independent slice artifacts |
| Knowledge Reconciliation | Curator / triple-cross-validation structures | Curator conflict detector returns no conflicts | BLOCKED: implement evidence-producing conflict detection before candidate wiring |
| Model Self-Evaluation | Model verification and execution traces | No admitted production candidate source | PARTIAL: only measured regression/disagreement may become work; probes remain probes |
| Runtime / Provider Health Analysis | Runtime state, provider health and traces | Health checks only | PARTIAL: unexplained anomaly across independent runtime/provider artifacts may become work |
| A-share Data Quality Research | StockDataBenchmark evidence and source lineage | `StockDiscoverySources.data_health_candidates` | READY: degraded independent sources produce an admission-ready reasoning candidate |
| Advisor Improvement Research | Advisor runner status and delivery ledger | Conditional stock discovery source | CONDITIONAL: only explicit AUTO_RUN plus recorded failure; never enables sending |
| Financial Research | Work Allocation category and stock artifacts | No general producer | BLOCKED by Data Health and a missing evidence-backed research-question producer |

## Invariants

- LOCAL work consumption and MODEL work discovery are independent.
- Existing TaskPool backlog does not globally suppress model-work inspection.
- Discovery does not increase Researcher throughput.
- No daily minimum task or model-call quota exists.
- Candidate sources may return nothing without being treated as failure.
- `ModelTaskAdmission` remains the hard eligibility boundary.
- Strategic/execution roles are never renamed to reasoning to influence routing.
- Advisor, Risk, Data Health, Telegram, and auto-push boundaries are unchanged.

## Work-value and admission audit

The production funnel must be measured as three separate gates:

```text
source inspected -> candidate formed -> admission decision -> service opportunity
```

On 2026-08-25 the first natural daily run produced one candidate, admitted one,
and rejected zero.  The candidate then sat behind more than one hundred older
high-priority tasks.  This is evidence of a service-visibility defect, not an
over-strict admission rule.  The selector defect was fixed without adding
Researcher capacity: the existing untouched-work fairness scan now considers
the complete bounded pool instead of its first 100 records.

Do not weaken admission until production reports show a material population of
well-formed candidates rejected for a particular reason.  If that evidence
appears, use explicit value levels rather than a daily-call quota:

| Level | Meaning | Model path |
|---|---|---|
| L0 LOCAL | Deterministic collection, parsing, indexing, or archaeology | No model |
| L1 SYNTHESIS | Falsifiable question supported by at least two independent evidence refs | Reasoning profile after admission |
| L2 STRATEGIC | L1 plus material cross-system impact and alternatives/counter-evidence | Strategic profile; never inferred from priority alone |
| L3 EXECUTION | Approved bounded action with rollback, authorization, and verification contract | Execution profile behind all existing hard gates |

Priority answers when work should be serviced.  Value level answers what kind
of cognition or authority the work requires.  They must not be conflated, and
neither field may be used to rename work to force a particular model.

## Cognitive Work Supply

The existing `DailyGrowthLedger` publishes a non-quota
`cognitive_work_supply` view from persisted observations, the daily model-work
Admission funnel, TaskPool lifecycle records, and production execution traces.

It records:

```text
observations
candidate_work
accepted_work
accepted_model_work
admitted_candidate_work
local_work
reasoning_work
strategic_work
execution_work
deferred_work
rejected_work
eligible_but_unserved
model_calls
archived_work
```

Derived observations are:

```text
discovery_yield
admission_rejection_rate
service_latency_seconds (median / p95)
model_work_service_rate
```

These are diagnostic measurements, not activity targets.  Both
`activity_quota_enforced` and `model_call_quota_enforced` remain false.

Zero model calls must have a causal status, including:

```text
OBSERVATION_PIPELINE_SILENT
NO_CANDIDATE_DISCOVERED
CANDIDATE_FOUND_BUT_REJECTED
CANDIDATE_DEFERRED
ELIGIBLE_WORK_NOT_SERVICED
ELIGIBLE_WORK_SERVICE_INCOMPLETE
```

Three consecutive completed daily discovery windows with zero Candidates set
`discovery_health=INVESTIGATE_DISCOVERY_CHAIN`.  The signal does not create a
Task or call a model by itself.

Coverage is deliberately explicit.  Observation counts come from the retained
RuntimeObserver window, accepted Work comes from TaskPool creation records, and
Candidate/Admission counts currently cover Model Work Discovery only.  Daily
Learning, local Observer, FileScanner, and MineSeedScanner do not yet expose a
common Candidate funnel, so the report declares `coverage.complete=false`
instead of presenting a partial count as civilization-wide truth.

### Isolated historical verification

Using the persisted 2026-08-25 TaskPool, observation ledger, and model-work
discovery report as read-only inputs produced:

```text
observations = 118
candidate_work = 1
accepted_work = 24
accepted_model_work = 1
local_work = 23
reasoning_work = 1
strategic_work = 0
execution_work = 0
eligible_but_unserved = 0
model_calls = 4
archived_work = 29
service_latency_seconds.median = 886.371
model_work_service_rate = 1.0
window_status = MODEL_WORK_SERVICED
```

The observation count is limited to the RuntimeObserver retained window, and
the Candidate count covers Model Work Discovery only.  The calculation wrote
to a temporary report, not the production ledger.  Production evidence for the
new schema requires a normal safe daemon reload and a natural lifecycle cycle;
neither should be forced merely to populate the metric.
