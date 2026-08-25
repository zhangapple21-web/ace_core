# Model Task Admission-003 Design

## Goal

Prove, using only an isolated TaskPool, that an Observation with independently verifiable non-local research evidence can create an explicitly typed `reasoning` task, while archaeology and other local-only evidence can never be promoted to a model task.

## Scope

This phase adds an isolated ModelTaskAdmission decision boundary and RED/GREEN coverage. It does not wire the boundary into `ObservationToTaskConverter`, `DiscoveryMode`, `ace_daemon.py`, or the production TaskPool. It does not modify MinerPool, ModelRouter, providers, scheduling, or task profiles. It never creates `strategic` or `execution` tasks.

## Input Contract

A decision receives an observation-shaped mapping with:

- `source_type`: source class used for local-only protection.
- `source_ref`: immutable source identifier.
- `evidence`: evidence records, each with a non-empty `source_ref`.
- `research_question`: the unresolved cognitive question.
- `expected_result`: the expected reasoning output.
- `verification_method`: the result verification method.

The isolated test helper builds this mapping directly. Existing production Observation and Discovery formats are not changed in this phase.

## Decision Contract

`ModelTaskAdmission.evaluate(candidate)` returns a JSON-safe decision mapping:

```text
{
  eligible: bool,
  classification: "local_evidence_only" | "reasoning",
  reasons: list[str],
  evidence_refs: list[str],
  admission_basis: dict
}
```

The decision is deterministic and contains no model, router, provider, task-pool, or filesystem dependency.

## Classification Rules

1. Local-only protection runs first. `source_type == "archaeology"`, `local_evidence_only == true`, `route_mode == "local_evidence_only"`, or a local archaeology tag produces `eligible=false`, `classification="local_evidence_only"`, and reason `local_evidence_only`.
2. A non-local candidate must contain at least two evidence records with two distinct non-empty `source_ref` values.
3. A non-local candidate must have non-empty `research_question`, `expected_result`, and `verification_method` strings.
4. A candidate that satisfies rules 2 and 3 produces `eligible=true`, `classification="reasoning"`.
5. All other candidates produce `eligible=false`, `classification="local_evidence_only"` and stable missing-condition reasons.
6. `strategic` and `execution` are outside this phase. The evaluator does not emit either classification.

## Isolated Task Persistence

A separate isolated helper may persist only an eligible decision into a temporary TaskPool. The persisted task must:

- use an explicit `task_type:reasoning` tag;
- store `outputs.discovery.task_type == "reasoning"`;
- include `outputs.model_task_admission` equal to the evaluator decision;
- preserve the source reference and both evidence references in Task admission;
- use `source_type="external_research"` in the test fixture.

Ineligible decisions do not create a task.

## Test Boundaries

All tests use `TemporaryDirectory()` TaskPools and do not load daemon configuration or initialize MinerPool.

Required RED/GREEN cases:

- two independent evidence references plus all three research fields create one traceable reasoning task;
- one evidence reference does not create a task;
- missing verification method does not create a task;
- archaeology/local-only input with otherwise valid double evidence does not create a task and cannot classify as reasoning;
- a candidate claiming `strategic` or `execution` still cannot produce either type in this phase.

## Acceptance Criteria

- The evaluator has no production runtime side effects.
- Only evidence-qualified, non-local inputs can become isolated reasoning tasks.
- Local archaeology cannot cross the model task boundary.
- No strategic or execution task is generated.
- Existing test suite and new isolated test file pass.
