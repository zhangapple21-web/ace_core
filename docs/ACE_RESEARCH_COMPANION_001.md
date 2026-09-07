# ACE Research Companion v1

## Purpose

`core/research_companion.py` provides a small, report-only context layer for
the Free Zone and human research briefs. It turns an open question into a
hash-bound card and keeps later evidence, counterevidence, hypothesis changes,
and invalidations in an append-only thread. The design absorbs the useful
parts of the reviewed research practice: question-first decomposition,
explicit falsification, and continuity of reasoning.

## Contract

- `ResearchQuestionCard` is created with a falsifiable hypothesis, scope,
  expected evidence, unknowns, and a next verification step.
- Support and counterevidence are separate, timestamped references with an
  independence group. A card without a counterevidence pass is forced to
  `UNKNOWN`; the module never invents a contrary fact.
- `ResearchThread` starts with `question_created`. Every later event is
  appended and linked to the prior event hash. Old judgments remain intact;
  a changed hypothesis or invalidation is an event, not an overwrite.
- All artifacts have SHA-256 integrity hashes and fixed
  `production_integration: false`.

## Boundary

This module does not import or call TaskPool, Scheduler, Worker, Runtime,
Data Health, Admission, Advisor, Risk, broker, Telegram, or any model/provider.
It does not create candidates, orders, recommendations, or outbound messages.
It is suitable for Free Zone shadow records and as optional context attached
to a human-review research brief. Crossing into ACE reality remains an
explicit `FreeZoneRealityBridge` receipt followed by the existing ACE gates.

## Status semantics

`FACT`, `INFERENCE`, `HYPOTHESIS`, `UNKNOWN`, and `INVALIDATED` describe the
epistemic state of the card, not a trading signal. Thread states (`OPEN`,
`VERIFICATION_PENDING`, `INVALIDATED`, `CLOSED`) describe research progress,
not production readiness.

## Verification

`ops/test_research_companion.py` covers hash round trips, missing
counterevidence, forbidden production fields, event append/history,
tamper detection, invalidation retention, and forbidden event payloads.
