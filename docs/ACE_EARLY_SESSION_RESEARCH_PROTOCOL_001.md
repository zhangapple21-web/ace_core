# ACE Early-Session Research Protocol 001

## Purpose

Turn the teacher's early-market checklist into an auditable, replayable
research protocol.  This is not an automated stock-picking or delivery path.
Until Phase 2 A-share data admission is strict for `quote`, `minute_kline_1m`,
and `index`, every output remains `RESEARCH_ONLY`.

## Fixed timetable (Asia/Shanghai)

| Phase | Window | Required retained fields |
| --- | --- | --- |
| `premarket` | 09:00-09:15 | announcement scan, overnight context, sector hypotheses |
| `auction` | 09:15-09:25 | auction quote, auction volume, index auction |
| `first_minute` | 09:30-09:31 | quote, 1m kline, index |
| `open_validation` | 09:30-09:45 | quote, 1m kline, index, sector breadth, volume-price state |

At each phase, a record must name non-empty `source_refs`.  By open
validation, all prior phases are required; a complete final-phase record
cannot conceal a missing auction or pre-market snapshot.

## Hard gate

For the live operations `quote`, `minute_kline_1m`, and `index`, ACE requires
all of: independently cross-validated sources, observable lineage, freshness,
complete coverage, complete fields, and cross-source consistency.  If any one
is absent, the record fails closed with
`live_quote_1m_index_not_strictly_admitted`.

## Context and historical validation

Forum, sector-news, public institutional commentary, and short-term flow
material enter only as a `CROSS_VALIDATE_WITH_HARD_DATA` question.  They never
satisfy a hard-data field and never provide selection authority.

Numeric signal thresholds are intentionally omitted until a frozen rule profile
has a named `historical_validation_ref`.  The next evidence step is to replay
10-20 point-in-time historical cases and preserve sources, rule version,
outcomes, invalidations, and out-of-sample split.  Only then can a separately
governed rule profile be considered for the existing human-review brief.

## Boundaries

- no network fetch, model call, candidate creation, Advisor/Risk integration,
  Telegram delivery, order, or auto-push;
- no change to data lineage, freshness, coverage, field completeness, or
  cross-source consistency standards;
- teacher review remains required even if a later validated profile is added.
