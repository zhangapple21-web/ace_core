# PROTOCOL-010 — ACE Execution Discipline v1.1

开工协议的完整阶段与证据账本见 [`ACE_START_PROTOCOL_V2.md`](ACE_START_PROTOCOL_V2.md)。

## Decision

The `OMX-INSPIRED-FZ-20260905` pilot is `INCONCLUSIVE` for comparative benefit.
ACE therefore adopts only the narrow, boundary-safe part that the pilot and
existing ACE governance support: every admitted task receives one persisted
execution-discipline envelope, and structured work records clarification,
minimal planning, verification, and an explicit stop condition before the
existing lifecycle proceeds.

This is a protocol envelope, not a new runtime. It does not install OMX, create
`.omx` state, add a scheduler/router/worker queue, or grant any production or
external authority.

## Scope by complexity

| Complexity | Default behavior |
| --- | --- |
| `simple` | Light branch: execute through the existing lifecycle, keep verification and stop fields, do not force paperwork. |
| `medium` | Structured envelope: record goal/non-goals/facts/unknowns/boundary, then a minimal three-step plan. |
| `complex` | Same structured envelope, with an explicit refusal rule for shared/dependent parallelism and a note that independent review/recovery are not proven by the pilot. |

Complexity may be supplied explicitly through `create_task(..., complexity=...)`
or `complexity:<value>` tags. Otherwise ACE uses a deterministic, conservative
heuristic and records its basis in the task itself.

## Required envelope

`core.execution_discipline.build_execution_discipline` persists the following
under `task.outputs.execution_discipline`:

- clarification: goal, non-goals, known facts, unknowns, and boundary;
- minimal plan: required only for `medium` and `complex` work;
- verification: the existing Validator/Guardian path and source recheck;
- constraints: no default parallelism for shared/dependent state, existing
  continue-gate recovery only, and no external side effects;
- stop: evidence complete or gap recorded, no blind retry, and no remaining
  in-scope action;
- bounded lifecycle events for preparation, start, review, transitions, and
  stop.

The envelope preserves `UNKNOWN`, `FAILED`, and proposal-only outcomes. It is
not evidence that clarification was performed by a human, that a reviewer was
independent, or that recovery/parallelism succeeded.

## What is deliberately not adopted

- mandatory full planning for simple work;
- real parallel execution or a second coordination runtime;
- same-worker “challenge” passes as independent review;
- synthetic owner continuity as crash-recovery proof;
- automatic ACE promotion of the Free Zone pilot;
- provider/model/token cost claims when no trace exists.

## Acceptance and rollback

The implementation is additive and backward compatible. Legacy task files are
backfilled in memory by `ensure_execution_discipline`; no task status or
authority is changed by backfill. The persisted envelope is written through the
existing atomic `TaskPool` writer and follows the existing single-daemon,
single-source-of-truth model.

Focused regression: `ops/test_execution_discipline.py`.
