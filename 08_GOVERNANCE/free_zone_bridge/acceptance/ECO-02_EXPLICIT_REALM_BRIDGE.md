# ECO-02 explicit realm bridge acceptance

Date: 2026-08-29 (Asia/Shanghai)

## Decision

**Accepted for ACE reality research only.**

The Free Zone learning identified by
`EXP-20260827052410721753-FREEZONE-EC3912CEC380` is now represented in ACE
reality by the immutable receipt
`BRIDGE-0AC26C3DA5102F3C689240C4`.

This is not TaskPool admission, production integration, recommendation
authority, Experience adoption, or permission for automatic scanning.  The
existing ACE Admission or Experience review remains the only next gate.

## Mapped learning

Free Zone exploration may remain unconstrained inside its own realm.  A result
crosses into ACE only when one artifact is explicitly named, bound by its
experiment and distillation hashes, translated into an ACE reality question,
supported by independent reality evidence, and freshly accepted by the main
steward.  The source outcome is evidence input, never a production fact.

## RED and minimal implementation

- RED: `python -m pytest -q -p no:cacheprovider ops/test_free_zone_reality_bridge.py`
  failed during collection because `core.free_zone_reality_bridge` did not
  exist.
- Single-writer implementation:
  - `core/free_zone_reality_bridge.py`
  - `ops/build_free_zone_reality_bridge.py`
  - `ops/test_free_zone_reality_bridge.py`
  - `08_GOVERNANCE/free_zone_bridge/mappings/ECO-02_EXPLICIT_REALM_BRIDGE.json`
  - this acceptance record and the generated receipt
- No daemon, TaskPool, provider, model route, Finance, Risk, Advisor, Telegram,
  World Atlas, or legacy Free Zone writer was modified.

## GREEN and integrity evidence

- Bridge contract: `5 passed`.
- Focused adjacent regression: `36 passed` across the bridge, Free Research
  Sandbox, realm boundary, counterexample preservation, DailyShift, runtime
  identity, task-quality governance, and coordination ledger tests.
- Syntax compile: passed.
- `git diff --check`: passed for the touched scope.
- Unmerged-path scan: empty.
- Real command executed twice with the same inputs and returned the same bridge
  ID; exactly one receipt exists.

## Real runtime non-interference

Immediately before and after the real bridge run:

- sole daemon PID: `30704`
- ACE local run ID: `3929e80267a14ed4bb983cd422a5aa3a`
- lock/state/heartbeat identity: matched
- executable TaskPool counts: `pending=0`, `active=0`, `review=0`, `approved=0`
- source artifact SHA-256:
  `f05bff2d52a4b72fac4424d0851ea6b09d987e36fd0eb7402a515097f8a660db`

All values were unchanged.  The receipt reports `task_created=false`,
`model_call=false`, `production_runtime_mutation=false`,
`admission_bypassed=false`, and `recommendation_authority=false`.

## Independent reality evidence

The accepted receipt binds three distinct evidence groups:

1. independent boundary audit;
2. deterministic boundary regression contract;
3. sole-daemon natural runtime output.

## Next gate

Future Free Zone results may reuse this bridge implementation only through a
new explicit mapping and fresh evidence snapshot.  No directory scan, batch
promotion, automatic bridge run, or daemon consumer is accepted.  If a mapped
learning later proposes concrete ACE work or Experience adoption, it must pass
the existing corresponding review from zero.
