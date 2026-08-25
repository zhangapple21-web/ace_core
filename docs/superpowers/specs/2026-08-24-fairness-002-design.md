# Fairness-002 Design

## Goal

Prevent ordinary pending high-priority tasks from indefinitely suppressing eligible pending medium-priority tasks while preserving the base priority order:

```text
critical > high > medium > low
```

The mechanism applies only to Researcher claim selection. It does not change Validator policy, task state transitions, leases, fencing, task admission, or the daemon's two Researcher claim slots per lifecycle round.

## Scope

Fairness-002 governs a pending, claim-eligible medium task that repeatedly loses a real Researcher claim opportunity to a pending, claim-eligible ordinary high task. A medium task is eligible only when it is not terminal non-convergent and its `retry_after` is absent or expired.

This is independent of the existing rework fairness policy. Rework fairness prevents a repeatedly reworked task from displacing untouched work. Fairness-002 measures only ordinary high-versus-medium competition.

## Scheduling Contract

`Researcher.pick_up_task(priority="any")` remains priority-first by default.

1. If an eligible pending critical task exists, Researcher claims critical work. Aged medium work never overrides critical work.
2. Otherwise, when an eligible pending high task is claimed while an eligible pending medium candidate exists, the medium candidate records one high competition by incrementing `starvation_age` and appending a `selection_trace` event with reason `aging_competition`.
3. After a medium candidate reaches `FAIRNESS_MEDIUM_AGE_LIMIT = 3`, the next high claim opportunity claims that medium task instead. The deferred high task records `aging_yield`; the claimed medium records `aging_reset` and resets `starvation_age` to zero.
4. A successful medium yield consumes exactly one existing claim opportunity. It does not add a third slot or otherwise alter the daemon's `for _ in range(2)` lifecycle loop.
5. A medium task that is ineligible, terminal non-convergent, delayed by `retry_after`, or absent cannot accumulate an eligible competition and cannot be yielded.
6. The policy is per medium task. Multiple medium tasks age independently, and only the first eligible medium candidate selected by normal TaskPool ordering receives the next bounded yield.

## Persistence And Observability

`Task.starvation_age` is JSON-persisted with default zero for historical task files. The selection trace is the production-observation surface:

```text
aging_competition
aging_yield
aging_reset
```

The mechanism must continue to use `TaskPool.claim_task()` for the actual claim, so lease ownership, `claim_id`, and `fencing_token` retain their existing semantics.

## Isolation And Production Boundary

All implementation verification uses temporary TaskPool directories. Before isolated tests pass, the production `C:\tmp\ace_core\task_pool` is not modified and the daemon is not restarted. After isolated verification, production evidence is gathered separately through five read-only daemon cycles.

## Acceptance Criteria

- Three successful ordinary high claims competing with an eligible medium cause one subsequent bounded medium claim.
- An eligible critical task is selected before an aged medium.
- High remains the majority over sustained high backlog; the mechanism provides bounded opportunities rather than priority inversion.
- Five simulated two-slot cycles retain exactly two claim attempts per cycle and produce bounded medium access under continuous high backlog.
- Ineligible or terminal medium tasks are not selected or aged through an invalid claim path.
- Rework fairness remains independent and lease/fencing behavior continues to pass its existing regression tests.
