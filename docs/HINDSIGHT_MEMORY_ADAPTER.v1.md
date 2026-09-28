# Hindsight-style memory adapter v1

## Positioning

ACE borrows Hindsight's multi-path retrieval, evidence-backed observation,
and read-only knowledge projection ideas without adding a second memory source
of truth. `core/hindsight_memory_adapter.py` is a local, read-only, zero-
dependency adapter. Default ACE retrieval is unchanged; the adapter is
explicitly opt-in.

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

This adapter can become a default retrieval path only after a real fixture or
shadow benchmark demonstrates measurable improvement, no regression, zero
boundary leakage, and a complete painful review. The current synthetic PASS is
only a candidate evidence receipt and is deliberately not promoted. Run
`ops/record_hindsight_memory_promotion_gate.py` to record the decision. The
current synthetic comparison deliberately keeps the adapter opt-in because its
recall improves while its naive in-process latency is higher; the closed-loop
receipt therefore records `ROLLBACK_REQUIRED` for default promotion.
