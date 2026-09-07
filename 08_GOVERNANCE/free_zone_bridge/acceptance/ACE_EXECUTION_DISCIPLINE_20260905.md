# ACE execution-discipline acceptance — 2026-09-05

## Decision

**Accepted narrowly for ACE protocol implementation.**

The source OMX-inspired pilot remains `INCONCLUSIVE`; it did not prove a
workflow speedup, quality gain, independent review, parallel execution, or
crash recovery. The accepted change is only the boundary-safe discipline that
the evidence supports.

## What was implemented

- `core/execution_discipline.py` builds one deterministic envelope per task.
- `TaskPool.create_task` persists the envelope atomically under
  `task.outputs.execution_discipline`.
- Legacy task files are backfilled without changing status or authority.
- Existing lifecycle transitions append bounded protocol events.
- Medium/complex research enters a fail-closed minimum gate for goal, minimal
  plan, and verification method; simple work stays on a light branch.
- The protocol records refusal of shared-state parallelism and defers
  independent review/recovery claims to future evidence.

## Evidence

- Source synthesis hash:
  `7e267563b01225766b1ecd636e76f038204040bc3dbff418457499c64efa0d0`
- Adversarial review hash:
  `4c162c9d5fac8397646a727e33597cc1d734644d05f66074057cc63039fd4de8`
- Combined focused protocol + TaskPool/admission/non-convergence regression:
  `35 passed`.
- Mainline/authority/continuity regression: `95 passed`.
- Daily/model/task-pool regression: `48 passed`.
- `py_compile` and `git diff --check`: passed for the touched implementation.

## Boundaries preserved

No OMX installation, `.omx` directory, tmux/psmux, second scheduler/router,
provider call, external send, deployment, ACE admission bypass, or automatic
Free Zone promotion was performed. The bridge receipt is
`BRIDGE-OMX-EXECUTION-DISCIPLINE-20260905.json` and retains the source
`INCONCLUSIVE` verdict.

## Follow-up evidence required

Before considering stronger claims, run a separately instrumented Free Zone
experiment with symmetric timing, repeated fixtures, a genuinely independent
reviewer, real interruption/recovery, and real independent parallel lanes.
