# ACE Capability Ownership Validation — 2026-08-25

> Scope: validate the owner and current evidence strength of the 17 capabilities
> marked `PRODUCTION_ACTIVE`, then inspect import consumers for four exact
> duplicate groups.  This is read-only ownership archaeology.  It does not
> activate, merge, move, delete or repair a capability.

## Executive Answer

All 17 production-active capability families have current daemon wiring and at
least current-day evidence.  Their evidence strength differs:

```text
DIRECT_CURRENT_CYCLE        current cycle artifact or state
DIRECT_CURRENT_DAY          real trace from today's current production lineage
WIRED_IDLE_CURRENT_CYCLE    current daemon wiring, but no new output this cycle
```

No capability was upgraded merely from file presence or a health probe.

The four exact duplicate groups have no established current production import
consumer.  In each ACE pair, the `04_PROTOCOLS` file has repository history and
the byte-identical `core` file is a staged addition with no committed history.
This proves an incomplete copy/migration, not a completed canonical-owner
transition.

## Runtime Anchor

At the validation snapshot:

```text
pid                 26788
run_id              5c68d12cb7b849c28fc584be91a47d9b
process_started     2026-08-25T11:55:46+08:00
last_cycle_started  2026-08-25T14:06:01+08:00
last_completed      through runtime_observations; Curator in progress
pending             319
active                0
review                0
approved              0
archived              41
blocked                5
graveyard             17
```

The process still predates the Experience identity repair and therefore does
not validate the new Experience semantics.

## Active Capability Evidence Table

| ID | Evidence strength | Current evidence | Owner verdict |
|---|---|---|---|
| OBS-RUNTIME-HEALTH | DIRECT_CURRENT_CYCLE | heartbeat at 14:07; stage pulses and current run_id | confirmed `ace_daemon` / Heartbeat |
| OBS-FILESYSTEM | WIRED_IDLE_CURRENT_CYCLE | FileScanner and LocalArchaeologist wired; current cycle created no new task | confirmed current producers, idle this cycle |
| OBS-OBSERVATION | DIRECT_CURRENT_CYCLE | runtime_observations stage completed at 14:06:05 | confirmed RuntimeObserver boundary |
| OBS-GIT-MINE-SEED | WIRED_IDLE_CURRENT_CYCLE | scanner wired; producer count zero this cycle | confirmed narrow mine-seed owner, not civilization-wide |
| WORK-DISCOVERY | DIRECT_CURRENT_DAY | one evidence-backed Candidate and one admitted reasoning task today | confirmed Discovery / ModelWorkDiscovery |
| WORK-ALLOCATION | DIRECT_CURRENT_CYCLE | 319 existing Work classified: 316 Local, 1 Reasoning, 2 Exploration | confirmed AutonomousWorkAllocation |
| WORK-ADMISSION | DIRECT_CURRENT_DAY | Candidate funnel 1 observed, 1 eligible, 1 task created | confirmed Admission modules |
| TASKPOOL-LIFECYCLE | DIRECT_CURRENT_CYCLE | pool state and task_lifecycle stage current; 41 archived today | confirmed TaskPool |
| TASKPOOL-FAIRNESS | DIRECT_CURRENT_DAY | high/medium and multiple sources received service earlier today | confirmed TaskPool/task-role selection; multi-day proof absent |
| RESEARCH-LOCAL | DIRECT_CURRENT_DAY | real claim/research transitions persisted in archived tasks | confirmed Researcher |
| EXECUTION-MODEL-POOL | DIRECT_CURRENT_DAY | one admitted reasoning Work, four successful production-task calls | confirmed MinerPool; probes excluded |
| EXECUTION-PROVIDER-HEALTH | DIRECT_CURRENT_CYCLE | model_health stage current; provider watchdog state exists | confirmed watchdog; health is not production work |
| VALIDATION-TASK | DIRECT_CURRENT_DAY | real validation/rework/approval history | confirmed Validator |
| GOVERNANCE-GUARDIAN | DIRECT_CURRENT_DAY | Guardian decisions persisted on naturally archived tasks | confirmed Guardian |
| KNOWLEDGE-ARCHIVE | DIRECT_CURRENT_DAY | 41 approved-to-archived task IDs in DailyGrowth ledger | confirmed Archivist |
| KNOWLEDGE-MEMORY-INDEX | DIRECT_CURRENT_CYCLE | daemon memory state and daily summary updated in current cycle | confirmed local runtime MemoryIndex |
| KNOWLEDGE-DAILY-GROWTH | DIRECT_CURRENT_CYCLE | ledger recorded at 14:06 with 41 archived tasks and four production calls | confirmed DailyGrowthLedger |

## Important Evidence Qualifications

### Active does not mean productive every cycle

FileScanner and MineSeedScanner produced zero new tasks in the current cycle.
That is compatible with active observation and Work Conservation.  Their status
comes from current wiring plus current-day/task-history evidence, not a quota.

### Current-day does not mean current-cycle

The four production model calls occurred earlier today for one Work.  The
current cycle re-reports the persisted trace; it did not make four new calls.
The ownership is validated, but new production volume is zero in this cycle.

### Archive count does not equal durable learning count

The ledger now reports 41 archived tasks.  The live process still uses the old
second-based Experience identity, so the archive count cannot be treated as 41
durably retained Experience records.

### Trace completeness is still imperfect

The current model-pipeline aggregate reports `trace_complete = 0` even though
task-level records contain provider, model, call result, latency and response
hash fields.  This is an observability discrepancy, not a reason to revoke the
verified production call.

## Exact Duplicate Consumer Audit

### Roundtable

```text
04_PROTOCOLS/roundtable.py  committed provenance: 6942bd7
core/roundtable.py          staged addition, no committed history
SHA-256                     identical
```

Consumers found:

```text
04_PROTOCOLS/awareness_loop.py → from roundtable import roundtable
core/awareness_loop.py         → from roundtable import roundtable
```

Neither Awareness Loop is called by the current daemon.  The `core` import is
also not package-qualified; when imported as `core.awareness_loop` from the
repository root it has no proven resolution to `core.roundtable`.

Owner verdict:

```text
historical provenance owner   04_PROTOCOLS/roundtable.py
current production owner      none
core migration complete       no
safe to delete                no
```

### Awareness Loop

```text
04_PROTOCOLS/awareness_loop.py committed provenance: 6942bd7
core/awareness_loop.py         staged addition, no committed history
SHA-256                        identical
current import consumers       none found
current daemon call            none
```

Owner verdict: historical protocol only; the staged `core` copy is not proven
as a production migration.

### Governor helper

```text
04_PROTOCOLS/governor.py committed provenance: 6942bd7
core/governor.py         staged addition, no committed history
SHA-256                  identical
current import consumers none found
```

This helper must not be confused with the current
`core.governance.knowledge_governor.Governor`, which the daemon actually uses.

Owner verdict: duplicate historical helper; no current production owner.

### Recovery Protocol

```text
ace_core/04_PROTOCOLS/recovery_protocol.py committed provenance: 6942bd7
ace_core/core/recovery_protocol.py         staged addition, no committed history
mine-seed/04_PROTOCOLS/recovery_protocol.py committed historical copy
SHA-256                                    identical across all three
current import consumers                   none found
```

Owner verdict: shared historical protocol with no proven current consumer.
Backup and runtime recovery capabilities elsewhere must not be conflated with
this orphaned exact-copy implementation.

## Canonical Ownership Decisions That Are Safe Now

The following ownership statements are evidence-backed and do not require file
mutation:

```text
current scheduler/lifecycle owner   ace_daemon.py
current task owner                  TaskPool
current Work discovery owner        Discovery / ModelWorkDiscovery
current model execution owner       MinerPool
current validation owners           Validator + Guardian
current task archive owner          Archivist
current runtime memory owner        MemoryIndex
current growth ledger owner         DailyGrowthLedger
current Roundtable owner            none
current Daily Lab handoff owner     none
current cross-repository owner      none
```

## Ownership Decisions That Are Not Yet Safe

Do not yet choose a canonical file for:

- Roundtable;
- Awareness Loop;
- the historical Governor helper;
- Recovery Protocol.

Reasons:

1. no current production consumer needs any of them;
2. the staged copies are user work and may represent an incomplete migration;
3. same-name concepts have different semantics elsewhere in mine-seed;
4. choosing an owner before defining the desired contract would preserve the
   wrong implementation merely because it is in `core` or has older history.

## Capability Catalog Corrections From This Validation

No status change is required for the 17 active entries.  Their evidence has
been qualified more precisely:

- seven are directly observable in the current cycle;
- eight have direct current-day lifecycle or execution evidence;
- two are currently wired and idle rather than producing new Work.

The duplicate family remains `SUPERSEDED_OR_DUPLICATE`, with canonical owner
pending.  Roundtable remains `HISTORICAL_RUNTIME`, not production active.

## Next Read-only Work

The next safe ownership pass is repository identity rather than capability
implementation:

```text
repository_id
local_path
remote_identity
visibility_confidence
trust_class
content_scan_allowed
model_context_allowed
publication_allowed
capability_evidence_roles
last_observed_commit
```

That catalog must remain metadata-only for sensitive repositories.  It should
not copy source content and should not activate scanning.

## Final Verdict

```text
ACTIVE_CAPABILITIES_REVIEWED             17
ACTIVE_CAPABILITIES_REVOKED               0
CURRENT_CYCLE_DIRECT_EVIDENCE              7
CURRENT_DAY_DIRECT_EVIDENCE                8
CURRENTLY_WIRED_AND_IDLE                    2
EXACT_DUPLICATE_GROUPS_AUDITED             4
CURRENT_PRODUCTION_CONSUMERS_FOUND         0
SAFE_CANONICAL_FILE_DECISIONS              0
PRODUCTION_CHANGE                          0
```

ACE now has a more accurate answer than “the module exists”: it knows which
capabilities are alive, which merely produced evidence earlier today, which are
currently idle, and which duplicated implementations have no current owner.
