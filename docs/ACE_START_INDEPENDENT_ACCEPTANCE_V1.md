# ACE start / independent acceptance v1

## Scope

`ace_start.py` is the single narrow task-start shim. It delegates the actual
claim to the existing `TaskPool.claim_task`, which remains the runtime
authority. The shim does not create a scheduler, queue, lease store, or second
state source. A start requires the already persisted execution envelope and
the existing owner/lease/claim/fencing path; malformed or missing envelopes
fail closed.

## Independent evidence chain

`ops/independent_acceptance.py` is a separate-process, read-only checker. It
reads the persisted task JSON and a protocol receipt, computes SHA-256 before
and after, verifies that an active task has an owner, claim, and fencing
token, binds the receipt to the same task ID and protocol versions, rejects
receipts carrying errors, and independently checks the minimum
execution-discipline envelope shape (complexity, pipeline, and events). It
never calls a lifecycle mutation API and never repairs a record.

The bounded replay is:

1. Create a temporary task through explicit Admission.
2. Start it through `core.ace_start.ace_start`.
3. Capture the protocol receipt and pre-start facts.
4. Run `python -m ops.independent_acceptance` in a separate process.
5. Require `verdict=PASS`, stable task identity, and no checker mutation.

This proves only the exercised temporary TaskPool/start/receipt path. It does
not prove that every legacy script, window tool, automation, heartbeat, or
old scheduler import uses the shim.

## Current result

- `ops/test_execution_discipline.py`
- `ops/test_runtime_authority_audit.py`
- `ops/test_independent_acceptance.py`
- `ops/test_legacy_cli_fail_closed.py`

Current focused result: **24 passed** for the start/discipline/authority set;
legacy CLI/owner/admission regression adds **20 passed**. The temporary
cross-process runner returns `verdict=PASS`.

## Boundary

`valid=true` in a protocol receipt means the recorded envelope is internally
consistent. It is not production approval, independent quality proof, or proof
that the whole checkout has one reachable lifecycle. The old
`core/scheduler.py` and `core/task_queue.py` remain present; all window-tool
guard coverage and heartbeat thread attribution remain unproven. The 3000
gateway also remains a separate health boundary from 3002 and must not be
declared healthy from the 3002 result.
