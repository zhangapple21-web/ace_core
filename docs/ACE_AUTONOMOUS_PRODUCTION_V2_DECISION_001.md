# ACE Autonomous Production v2.0 — Decision Record

## Decision

ACE accepts the proposed v2.0 as a coordination and reporting improvement, not
as a replacement runtime.  The sole `ace.py daemon --serve`, its TaskPool, its
admission path, and the existing Data/Advisor/Risk/TG gates remain authoritative.

## ABSORB

- Coordinate across Codex windows by observation and explicit scope.
- Start work by inspecting repository state and nearby ownership.
- Make `NO_NEW_WORK` an honest successful daily outcome.
- Present daily work as a fixed cognitive loop: observation, evidence review,
  validation, learning status, and next verification.
- Treat model routing as evidence-led: results and failures may inform later
  evaluation, never create a daily calling quota.

## ADAPT

- `agent_team/active_work_manifest.json` is Codex/human metadata only.  It has
  no authority to create, claim, renew, recover, move, or archive ACE tasks.
- Every declaration has exactly one `owner` window ID.  The owner is the only
  window allowed to write within that declaration's scope; all other windows
  must use read-only observation after checking the owner.  A missing or
  malformed owner fails closed to read-only.
- Complementary work is staged handoff: finish or explicitly hand off one
  stage, then create a new declaration for the next owner and disjoint scope.
  It is never multiple windows controlling the same process or declaration.
- A TTL is a stale-declaration hint.  It never grants automatic takeover;
  another worker must make a new declaration after comparison.
- Skill labels belong to a future Codex task packet/experience index.  They are
  not ACE runtime roles and cannot grant production capability.
- Financial reporting has two *slots*, not two required picks.  A valid
  Evaluation Pick is an explicitly paper-only, fully traceable record.  Zero
  is correct whenever no such record exists.
- Finance post-mortem reviews only prior traceable Evaluation Picks; otherwise
  it reports `NO_ELIGIBLE_PRIOR_RECORD`.
- Publication is a visible mapping of the existing Data, Advisor, Risk and TG
  gates, never a substitute gate.

## REDUNDANT

- Five Finance Work Windows already run inside the existing daemon lifecycle.
- ACE already has TaskPool leases, fencing, recovery and atomic transitions.
- Existing `agent_team/*/state.json` files remain durable records for their
  individual routing batches.

## CONFLICT / REJECT

- A manifest as a second scheduler, queue, TaskPool lease, ownership transfer,
  or daemon control plane.
- Automatic claim/takeover after TTL expiry.
- Git as live work ownership transfer.
- A mandatory daily minimum of two symbols, forced model calls, or synthetic
  tasks to make metrics look active.
- Promoting `DEGRADED` / `RESEARCH_ONLY` material to live recommendation or TG.

## Current Finance Outcome Contract

```text
evaluation_pick_target = 2          # maximum, never a quota
evaluation_pick_count = 0..2 when valid
zero-pick status = NO_VALID_EVALUATION_PICK
count > 2 status = INVALID_EXCESS_EVALUATION_PICK (never silently truncated)
postmortem without eligible history = NO_ELIGIBLE_PRIOR_RECORD
publication_authority = false unless existing gates independently allow it
```

This record intentionally introduces no scheduler, model call, task creation,
data-source integration, Advisor action, Risk action, or Telegram send.
