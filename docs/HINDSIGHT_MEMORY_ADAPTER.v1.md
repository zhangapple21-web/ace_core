# Hindsight-style memory adapter v1

## Positioning

ACE borrows Hindsight's multi-path retrieval as an implementation strategy, not
as a memory store. `core/hindsight_memory_adapter.py` is local, read-only, and
zero-dependency. Its canonical host is `MemoryKernel.query()`; the direct
`MemoryIndex` adapter entry was removed because it duplicated the route. The
daemon's current default remains the legacy `MemoryIndex` until the replacement
gate in `ACE_MEMORY_KERNEL.v1.md` passes.

## Landed capabilities

- Semantic proxy, keyword, concept/event graph, and temporal-window retrieval,
  fused with reciprocal rank fusion (RRF).
- ACE data-boundary validation for every candidate; unclassified records are
  rejected before retrieval.
- Evidence consolidation that retains evidence hashes, source-reference hashes,
  source record IDs, and duplicate counts. Conflicts remain UNKNOWN_CONFLICT.
- Knowledge pages are READ_ONLY_PROJECTION values with no governance or
  execution authority.
- `ops/run_hindsight_memory_benchmark.py` runs a synthetic, offline A/B test
  with no network, model, secret, or production call.

## ACE invariants that remain unchanged

`retain` is not a fact, `reflect` is not execution authorization, and an
observation is not capability growth. Any conclusion that changes future
behavior must still pass ACE evidence, painful review, rollback, and promotion
gates. A Hindsight bank cannot replace ACE identity, the L0-L6 hierarchy, or
the data-classification boundary.

## Acceptance gate

The current synthetic PASS is candidate evidence only: its baseline recall is
zero, adapter precision@3 is 1/3, and measured in-process latency is higher.
The `ROLLBACK_REQUIRED` receipt means "do not promote this candidate to the
default path"; no production rollback is needed because it was never integrated.
Do not use this synthetic result as a replacement decision. Any later promotion
must satisfy the single replacement gate in `ACE_MEMORY_KERNEL.v1.md`.
