# AUM-MISSION-EVIDENCE-RELEVANCE-SHADOW-AUDIT-003

## Boundary

This audit is offline and shadow-only.  It does not change TaskPool state,
Validator outcomes, Admission, Researcher throughput, daemon state, model
routing, data-health gates, or Telegram behavior.

Frozen production window:

```text
2026-08-25T00:00:00 through 2026-08-25T13:05:00 Asia/Shanghai
```

The window contains the 33 tasks that naturally reached `archived` before the
audit was frozen.  Later daemon archives are deliberately outside this
snapshot.

## Method

The deterministic evaluator reports observations, not verdicts:

- exact duplicate `(source, content)` records;
- identical content attributed to different sources;
- whether persisted evidence traces to the original Admission evidence;
- explicit upstream and `independence_group` lineage only;
- conservative lexical alignment for specific research questions;
- `unassessed` for generic archaeology questions rather than guessing semantic
  relevance.

No model or embedding service is used.  Consequently,
`possible_semantic_contamination` is a review signal, not proof that Validator
should reject a task.

## Frozen Results

```text
tasks                                      33
evidence records                          323
exact duplicate records                   153
tasks with exact duplicates                33
tasks with >=5 exact duplicates             22
cross-source duplicate-content groups       3
generic questions                          32
generic evidence records unassessed       316
Admission-traced evidence records            5
low-alignment evidence records               2
tasks with possible semantic contamination  1
tasks with explicit observable lineage       0
tasks with >=2 explicit independence groups  0
```

The duplication result does not mean all 153 duplicate records inflated the
Validator count.  Validator canonicalizes exact `(source, content)` pairs.
They do prove repeated evidence accumulation and wasted research/review work.
Identical content stored under different sources is more serious because the
current canonical pair treats it as distinct evidence.

## Representative Findings

### RQ-20260825-021

The task `核查A股数据源退化与字段冲突` contains seven persisted evidence
records:

- five trace to the original stock-data Admission evidence;
- two identical records come from `电销规则.txt` and do not trace to Admission;
- those two records have no strong lexical alignment with the specific stock
  data research context;
- one of the two is an exact duplicate;
- the Admission records contain upstream labels, but do not persist both an
  explicit `lineage_observable=true` fact and a verified
  `independence_group`, so the shadow audit does not claim source
  independence.

This establishes a real provenance-contamination defect.  It does not prove
that the five stock benchmark records are semantically invalid.

### RQ-20260823-096 / 100 / 101

These tasks contain the same content under two separate drawer paths
(`内部版说明.txt` and `内部版说明 (2).txt`).  The shadow evaluator reports
`cross_source_content_duplicate`; file-path count is not source independence.

### Generic archaeology tasks

Thirty-two tasks use broad questions such as `碎片考古` or
`启动碎片考古`.  Their 316 evidence records are marked `unassessed`, not
contaminated.  The current task question is too generic for a deterministic
lexical evaluator to prove relevance or irrelevance.  A future repair should
improve the research question or preserve a target artifact fingerprint; it
should not promote a heuristic warning into a hard Validator gate.

## Root Cause Boundaries

Confirmed in current code:

1. `Researcher.research_task()` appends evidence on every research pass.
2. `Task.add_evidence()` does not deduplicate before appending.
3. Validator canonicalizes `(source, content)` but does not test whether an
   evidence record traces to Admission or supports the task question.
4. The same content under different source strings is counted as distinct.
5. Persisted task evidence loses Admission lineage metadata because
   `Task.add_evidence()` stores only `source`, `content`, and `added_at`.

The shadow layer intentionally does not repair any of these production paths.

## Implementation

- `core/evidence_relevance_shadow.py`: pure in-memory diagnostics.
- `ops/evidence_relevance_shadow_audit.py`: read-only JSON loader and stdout
  report.
- `ops/test_evidence_relevance_shadow.py`: isolated non-mutation, relevance,
  duplicate, lineage, and time-window tests.

The module has no imports from TaskPool, Validator, daemon, MinerPool, model
clients, or Telegram components.

## Disposition

```text
SHADOW_ONLY = TRUE
PRODUCTION_ENFORCEMENT = FALSE
VALIDATOR_OUTCOME_CHANGED = FALSE
TASK_STATE_CHANGED = FALSE
MODEL_CALLED = FALSE
```

Do not make this evaluator a hard gate until a labeled review set establishes
false-positive and false-negative rates for archaeology, learning, runtime,
and model work separately.
