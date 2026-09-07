# ACE start closure v1 — evidence-bound

## FACT

- `ace.py` and the new `ace_start.py task ...` delegate task starts to
  `core.ace_start.ace_start`; the actual lifecycle mutation remains
  `TaskPool.claim_task`.
- `TaskPool` start/claim/active transitions now require an existing execution
  envelope and a passing gate. Missing envelopes fail closed; they are not
  repaired on a runtime start path.
- The read-only protocol audit no longer backfills a missing envelope. It
  returns `valid=false` with `missing_execution_discipline_envelope`.
- `ops/independent_acceptance.py` reads persisted JSON directly in a separate
  process, hashes before/after records, and checks owner/claim/fencing without
  writing runtime state.
- `ops/run_ace_start_acceptance.py` produced a temporary end-to-end receipt:
  `verdict=PASS`, `authority=ACE_TASKPOOL`,
  `runtime_mutation_by_checker=false`.
- The two discovered executable legacy constructors are now fail-closed:
  importing `core.scheduler` raises before loading its dependencies, and
  constructing `core.task_queue.TaskQueue` raises before creating directories.
  The source files remain for archaeology; this is not filesystem ACL proof.
- Focused regression: 28 passed; compile and diff checks passed for the new
  entrypoint, gate, verifier, and tests.

## NOT CLAIMED

This closes only the exercised start/acceptance boundary and the two discovered
legacy Python construction entries. It does not prove that the checkout has
one and only one reachable lifecycle: the legacy source files remain, direct
filesystem writes are not ACL-blocked, and full coverage of every Codex-window
tool, automation, heartbeat, direct script import, and terminal ownership
guard is not established. The 3000 gateway currently returns 500 for
`/v1/models` while 3002 `/v1/models` and `/healthz` return 200; those are
separate boundaries, not one healthy chain. Heartbeat thread attribution also
remains UNKNOWN where no local target evidence exists.

## INFERENCE

The covered start boundary is stricter: a derived record or a malformed task
cannot become a claim merely by being present, and an independent reader can
replay the resulting evidence without trusting the mutating process.

## NEXT EXPERIMENT

Build the write-entry matrix for legacy scheduler/task_queue, automation
runners, heartbeat runners, and all discovered window writers. Mark each
`OBSERVED_GUARD`, `DIRECT_WRITE`, `NO_GUARD_EVIDENCE`, or `UNREACHABLE`; keep
unmaterialized paths INCONCLUSIVE. Do not delete legacy files or create a
second runtime to obtain this evidence.
