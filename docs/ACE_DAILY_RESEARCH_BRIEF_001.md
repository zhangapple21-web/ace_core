# ACE Daily Research Brief 001

## Product boundary

ACE produces a **daily research brief for teacher review**.  It is not an
automatic recommendation engine, outbound messaging system, or order system.

```text
admitted evidence -> candidate cards -> teacher decision -> manual transfer
```

The only outbound-capable step is deliberately outside this module.  A teacher
may decide to have Xiao Yan manually relay approved material, but the system
does not compose, call Telegram, or mark a delivery as performed.

## Gate

Candidate cards are shown only when both of these conditions hold:

1. Runtime data quality reports `READY` and `recommendation_eligibility=eligible`.
2. The A-share Phase 2 matrix has strictly admitted all five core operations:
   quote, daily kline, 1 minute kline, 5 minute kline, and index; each needs
   two independent groups and explicit cross-source validation.

Any missing, stale, incomplete, untraceable, or conflicting evidence produces
a `RESEARCH_ONLY` brief with an empty candidate list and named blockers.

## Candidate card

Every card must contain point-in-time observation time, a rule-card identity,
trigger reasons, invalidating conditions, source references, snapshot hash,
and a research/backtest summary.  It cannot contain an order instruction,
target price, automatic send request, or performance guarantee.

## Human decision record

An `APPROVED` decision creates only an auditable `forward_eligible` flag.  It
still has `manual_transfer_required=true`; neither Telegram nor any trading
integration is imported or invoked.

## Continuous scholar loop

Open-source projects are held in a governed backlog and fed one at a time into
the existing DailyLearningLoop. A miner must conduct a bounded archaeology
before a project can be classified; a catalogue entry cannot install software,
change production routing, or become adopted knowledge by itself. The
Repository Curator remains the daily record keeper for resulting artifacts.
