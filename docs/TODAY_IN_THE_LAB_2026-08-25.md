# TODAY IN THE LAB — 2026-08-25

> Snapshot: 2026-08-25 13:17 Asia/Shanghai
> Purpose: explain what ACE actually observed, executed, learned, retained, and
> failed to retain. This is a convergence report, not a new runtime component.

## Executive Answer

ACE is no longer merely accumulating unclaimed tasks.  It is claiming,
researching, validating, approving, and archiving work across high and medium
priority sources.  One naturally discovered model task reached a real provider
and archived.

However, archived work is not yet equivalent to durable, trustworthy growth:

1. evidence quality is weak for most archaeology work and one model task has
   confirmed cross-domain contamination;
2. 35 archived tasks produced only 20 uniquely attributable Experience
   records because second-resolution Experience IDs collide and overwrite;
3. the A-share data, Risk, Advisor, and Telegram gates remain not ready;
4. DailyLearning was suppressed by a priority backlog and did not complete a
   governed learning target;
5. RepositoryCurator still reports full-repository scan volume rather than a
   current-run handoff.

The correct description of today is therefore:

```text
REAL EXECUTION AND PARTIAL CLOSURE
+
PROVISIONAL LEARNING
+
KNOWLEDGE RETENTION DEFECT
```

## What ACE Observed

- The daemon remained alive through the snapshot; the latest heartbeat was
  `2026-08-25T13:17:17.552075`, in the Curator stage.
- A-share source benchmarks showed material degradation and incomplete
  coverage across AKShare, FinShare, Tencent, BaoStock, PyTDX, Sina, and the
  legacy market source.
- Model Work Discovery formed one evidence-backed Candidate:
  `核查A股数据源退化与字段冲突` (`OBS-20260825-0475`).
- The Candidate passed existing ModelTaskAdmission and became
  `RQ-20260825-021`.
- TaskPool observations showed continued service for both high and medium
  work, including FileScanner and ObservationToTask sources.
- The evidence relevance shadow audit observed widespread duplicate evidence,
  generic archaeology questions, missing explicit lineage, and one specific
  contamination case.

## What ACE Completed

Production lifecycle counts through the snapshot:

```text
claim             116
unique claimed     81
research          116
validation        116
rework             81
approved           35
archived           35
```

Current pool:

```text
pending    325
active       0
review       0
approved     0
archived    35
blocked      5
graveyard   17
```

This is real net convergence, not an idle consumer.  Pending fell while
archived rose, and medium work received sustained service.

## Which Work Used a Model

Exactly one archived task was model work:

```text
task_id         RQ-20260825-021
task_type       reasoning
provider        nim
selected_model  nvidia/nemotron-3-ultra-550b-a55b
production calls 4
API successes     4
```

Health probes were excluded from the production count.  Shenwen 5.6 and 5.4
still have no verified production-task call in this snapshot.

The four calls were repeated service of one Work item, not four independently
discovered cognitive tasks.

## What the Model Actually Produced

The final persisted model analysis identified, provisionally:

- AKShare as severely degraded;
- the legacy market source as unavailable;
- FinShare as incomplete and lineage-unobservable;
- BaoStock as a limited fallback with consistency/coverage gaps;
- PyTDX as the strongest measured source in this benchmark;
- single-source risk for several operations;
- historical freshness as not yet validated against the market calendar.

This is a reasoning artifact, not model training and not proof that ACE's model
weights changed.  “Learning” here can only mean that a validated result was
retained and can affect a later decision.

The conclusion remains provisional because the task evidence also contains two
copies of an unrelated `电销规则.txt` record.  Five final evidence records do
trace to the original stock-data Admission; the two unrelated records do not.

## What Was Distilled

The runtime generated, by the snapshot:

```text
19 pattern Experience files
 1 constraint Experience file
 2 generated skill records
 1 skill manifest
 1 knowledge index
```

The generated skills describe recurring `碎片考古` and
`启动碎片考古` work.  They prove pattern extraction ran, but not that the
underlying archaeological conclusions are high quality.  The evidence audit
found those research questions too generic for deterministic relevance
assessment.

The stock-data constraint Experience contains the same unrelated telephone
sales evidence as its source task.  It must therefore be treated as
contaminated/provisional and must not be promoted into a production data or
Advisor rule.

## What Failed to Become Durable Knowledge

Thirty-five tasks archived, but only twenty Experience records currently have
unique `source_task_id` values.

Root cause:

```python
exp_id = f"EXP-{datetime.now().strftime('%Y%m%d%H%M%S')}"
```

Two tasks frequently archive in the same second.  They therefore receive the
same Experience ID, file path, and index key; the later deposition overwrites
the earlier one.

Observed consequence:

```text
archived tasks                 35
uniquely attributable records 20
retention gap                  15
```

This means `archived_task_count=35` is a valid lifecycle count, but it is not a
valid durable-growth count.  The current `MEASURABLE_GROWTH` label is therefore
directionally true but quantitatively overstated.

## Experience Retention Repair

A minimal code repair is now ready locally.  Experience identity is no longer
derived from wall-clock seconds.  It is stable per:

```text
(source_task_id, experience_type)
```

The repair also:

- restores persisted `reference_count` and `last_used_at` during loading;
- reuses current and legacy records for the same identity;
- permits different Experience types for the same source task;
- opens new Experience files exclusively, so an existing file cannot be
  overwritten silently;
- treats an unexpected deterministic-path collision as an explicit error.
- counts post-archive deposition failures in the lifecycle result and records
  the failing task ID in daemon error state instead of swallowing the error.

Verification completed at approximately 13:30 Asia/Shanghai:

```text
focused Experience tests                         7 passed
combined Experience/runtime/learning/shadow tests 83 passed
compileall                                       passed
diff whitespace check                            passed
```

The failure-observability repair does not retry deposition and does not move an
archived task.  It exposes the integrity failure without introducing a second
lifecycle.  A future recovery decision must remain evidence-governed.

This is `CODE_READY`, not yet `PRODUCTION_ACTIVE`.  The live daemon process
started at `2026-08-25 11:55:46`, before the module changed at approximately
`13:26:42`, so it still has the old implementation loaded.  No restart was
performed.  Status is therefore:

```text
EXPERIENCE_RETENTION_CODE_READY       YES
EXPERIENCE_RETENTION_PRODUCTION_ACTIVE NO
PRODUCTION_RELOAD_PENDING             YES
```

### Historical Recovery Assessment

A later read-only snapshot found that production had advanced to 37 archived
tasks and 21 uniquely attributable Experience records, leaving 16 missing
source task IDs.  All 16 are generic `碎片考古` or `启动碎片考古` tasks.  Their
questions assert only that a file or backlog *may* contain useful material;
the shadow audit also found generic relevance, repeated evidence, and known
cross-path duplicate content in this population.

```text
RQ-20260823-096  RQ-20260823-102  RQ-20260823-104  RQ-20260823-108
RQ-20260823-110  RQ-20260823-112  RQ-20260823-115  RQ-20260823-118
RQ-20260823-124  RQ-20260823-127  RQ-20260823-130  RQ-20260823-133
RQ-20260823-136  RQ-20260823-139  RQ-20260823-142  RQ-20260823-145
```

Classification: `0 safe automatic backfills`, `16 quality-review required`.
`RQ-20260823-096` additionally belongs to the known cross-source duplicate
content group and is explicitly unsafe to reconstruct without provenance
review.

Consequently none of the 16 is admitted for automatic backfill.  Existing
Guardian approval alone is not enough to reconstruct durable knowledge from
work whose relevance and provenance have not been calibrated.  Historical
backfill is deferred pending a task-by-task quality review; no Experience file,
task, or index entry was changed by this assessment.  The contaminated
`RQ-20260825-021` constraint is likewise not re-promoted or rewritten.

## Evidence Quality Findings

The frozen 33-task shadow audit (ending 13:05) found:

```text
evidence records                         323
exact duplicate records                  153
tasks with exact duplicates            33/33
tasks with >=5 exact duplicates        22/33
cross-source duplicate-content groups      3
generic archaeology questions          32/33
specific contamination warnings         1/33
```

Exact duplicates do not inflate Validator's canonical `(source, content)`
count, but they demonstrate repeated Researcher accumulation.  Identical
content under different source paths can inflate apparent source diversity.

The shadow evaluator remains diagnostic only and must not become a production
Validator gate without a labeled calibration set.

## What Changed in the System Today

Confirmed behavioral changes, regardless of the still-dirty worktree:

- Task selection now services high and medium work across more than one source.
- The lifecycle now produces natural approved and archived outcomes.
- Backlog-independent Model Work Discovery produced one real admitted Work.
- MinerPool executed that Work through a real provider.
- Daily growth and autonomous audit artifacts now distinguish production calls
  from probes.
- An offline, non-enforcing evidence relevance audit can now expose duplicate,
  provenance, lineage, and possible contamination warnings.

What did not change:

- no Experiment runtime was implemented;
- no second Scheduler, TaskPool, Router, or Worker was created;
- no Validator or Admission threshold was lowered;
- no Telegram or auto-push path was enabled.

## What Did Not Work

- DailyLearning returned `NO_VALID_LEARNING_TARGET` because
  `RQ-20260823-001` globally blocked the learning window.
- Knowledge deposition lost records through Experience ID collision.
- The stock constraint retained contaminated evidence.
- RepositoryCurator continued to report approximately 1000 artifacts as newly
  scanned every cycle with `status=unknown`.
- A-share Data Health remained blocked despite candidate independent-source
  capability in the operation matrix.
- Risk evidence is missing.
- Advisor's persisted last run is a failed 2026-07-14 snapshot.
- Owner TG controlled readiness and auto-push readiness are unverified and off.

## What Is Worth Watching Next

Only one repair deserves immediate priority:

```text
Experience deposition identity and idempotency
```

Acceptance should prove:

1. two tasks archived in the same second create two distinct Experience IDs;
2. replay of the same source task does not create duplicate Experience;
3. every successful archive has exactly one attributable deposition outcome;
4. collision recovery is observable;
5. no existing Experience is overwritten;
6. no model, Advisor, Data Health, Telegram, or TaskPool policy is changed.

Evidence provenance preservation remains important, but it is second.  An
archive-to-knowledge data-loss defect is more fundamental than adding richer
metadata to records that may be overwritten.

Experiment implementation remains paused.

## Deferred Read-only Mission Candidate

`AUM-MISSION-DAILY-ROUNDTABLE-ARCHAEOLOGY-001` is registered only as a
possible later archaeology mission.  It is not an implementation decision and
does not authorize a Council, Roundtable, Agent, Worker, task, model call, or
production integration.

It may start only after the Experience retention repair has been loaded and
verified through a natural production archive.  If started, its first phase is
strictly read-only and must classify every historical claim as one of:

```text
DESIGN_EVIDENCE
PRODUCTION_CODE
RUNTIME_ARTIFACT
```

Historical blueprints, persona descriptions, generated documents, and naming
similarity are not production evidence.  The archaeology question is limited
to whether R1 or mine-seed actually contained a multi-perspective daily-review
semantic that helped decide, from already-existing Observation, Evidence,
Candidate, and Work:

```text
what happened in the lab today;
which Work matters most;
which Work should Execute, Learn, Watch, Block, or Defer.
```

Any recovered semantic must be mapped against the current Work Discovery,
Work Allocation, Validator, Guardian, Archivist, Curator, and DailyLearning
boundaries.  It must not manufacture Work, restore CouncilOfThree personas,
create a second decision runtime, or produce tasks merely to exercise the
MinerPool.  No new Principle is authorized by this registration.

## Daily Verdict

```text
RUNTIME_ALIVE                         YES
TASKPOOL_CONSUMING                    YES
TASKPOOL_NET_CONVERGENCE              YES, current-day evidence
MODEL_WORK_DISCOVERY                  YES
MODEL_POOL_PRODUCTION                 YES, one Work / four NIM calls
MODEL_OUTPUT_DURABLY_TRUSTWORTHY      PARTIAL
KNOWLEDGE_DEPOSITION_COMPLETE         NO
DAILY_LEARNING_COMPLETED              NO
A_SHARE_DATA_READY                    NO
ADVISOR_READY                         NO
OWNER_TG_CONTROLLED_READY             NO
AUTO_PUSH_READY                       NO

ACE_IS_EXECUTING                      YES
ACE_IS_DURABLY_GROWING                PARTIAL / NOT YET RELIABLE
```

The honest summary is:

> ACE did real work today and closed real lifecycle paths.  It also exposed
> that lifecycle completion currently outruns knowledge quality and knowledge
> retention.  The next improvement should make completed work survive exactly
> once, not add another conceptual layer.
