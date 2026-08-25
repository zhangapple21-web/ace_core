# ACE Capability Census — 2026-08-25

> Question: What does ACE already own?  This census does not add, repair,
> merge, activate, or delete a capability.  It separates capability semantics,
> implementations, tests, historical execution, and current production state.

Machine-readable snapshot:
`docs/ACE_CAPABILITY_CATALOG_2026-08-25.json`

## Executive Answer

ACE does not primarily suffer from a lack of capability.  It suffers from a
lack of one evidence-backed memory of its capabilities.

The local drawer already contains:

```text
47 capability families or governance-relevant capability states
17 current production-active capabilities
 3 current but degraded capabilities
 1 tested repair waiting for production reload
 2 tested diagnostic/operator capabilities not wired into production
 9 implemented but not currently verified capabilities
 5 historical runtime capabilities
 3 blocked capabilities
 3 deliberately disabled side-effect capabilities
 2 design-only capability contracts
 1 exact-duplicate family
 1 sensitive excluded repository capability
```

These numbers are not a score.  They prevent four dangerous conflations:

```text
file exists        != capability is usable
test passes        != production is active
historical run     != current run
status says ACTIVE != runtime evidence exists
```

## Why Previous Capability Memory Was Lost

ACE has several old inventories, each answering a different question:

1. `CAPABILITY_FINAL.md` compresses all cognition into the primitives
   `Observe / Transform / Act`.
2. R1 Capability Archaeology defines seven Reality-interface semantics:
   Read, Write, Observe, Verify, Replay, Search, and Capture.
3. `03_DATA/MISSIONS/capability_registry.json` records old mission readiness
   declarations and AUTO worker mappings.
4. Worker registries list potential executors and declared capabilities.
5. Runtime topology documents map historical entry, router, gate, storage and
   exit nodes.
6. Current source code contains additional capabilities not reflected in those
   registries.
7. Current runtime artifacts prove only a subset of those implementations are
   actually alive today.

None of these inventories is individually wrong.  The failure is that they
were treated as interchangeable and were not continuously reconciled.

Examples:

- the old registry marks LawDiscoveryEngineReady as ACTIVE, but current
  `ace_daemon.py` does not call the mine-seed Law Discovery runtime;
- old mappings call Memory MCP and GitHub MCP current implementations, but no
  current ACE daemon trace establishes them as its production interfaces;
- mine-seed labels RoundTable Running, while its self-evolution code explicitly
  skips Roundtable audit pending integration;
- `core/roundtable.py` exists, but the current daemon does not call it;
- Experience deposition exists and has production history, but its repaired
  identity semantics are not active until the daemon reloads.

The missing capability is therefore not another execution engine.  It is:

```text
evidence-backed capability self-knowledge
```

## Census Model

Every capability is mapped to the old minimal primitives:

```text
Observe   receive or measure reality without authorizing an external effect
Transform assess, reason, validate, route, allocate, compress or decide
Act       write, archive, publish, send, execute or otherwise affect reality
```

The primitive is stable; implementations may change.

Every implementation receives one current status:

| Status | Meaning |
|---|---|
| `PRODUCTION_ACTIVE` | current wiring plus current runtime evidence |
| `PRODUCTION_DEGRADED` | current execution with a measured defect or failed gate |
| `CODE_READY_RELOAD_PENDING` | tests pass; live process predates the repair |
| `TESTED_NOT_WIRED` | regression evidence exists; no production call path |
| `IMPLEMENTED_UNVERIFIED` | code exists; current use was not established |
| `HISTORICAL_RUNTIME` | a past runtime artifact exists; no current execution |
| `DESIGN_ONLY` | definition or design exists without proven implementation |
| `BLOCKED` | implementation exists but a mandatory gate is not ready |
| `DISABLED` | side effect is intentionally off |
| `SUPERSEDED_OR_DUPLICATE` | duplicate or non-canonical implementation |
| `SENSITIVE_EXCLUDED` | deliberately excluded from ordinary discovery |

## What ACE Currently Knows How to Do in Production

Seventeen capability families have both a current production path and runtime
evidence.

### Observe

- maintain heartbeat, run identity and bounded lifecycle-stage closure;
- scan local files and fragment indexes;
- persist Runtime Observations and convert eligible observations into tasks;
- observe mine-seed Git increments;
- monitor provider health, fallback and task-call traces;
- produce a daily cognitive-work and growth ledger.

### Transform

- discover evidence-backed local and model Work;
- allocate existing Work across Local, Learning, Reasoning, Strategic,
  Execution, Exploration and Financial Research categories;
- apply Task, ModelTask and Evidence admission;
- maintain TaskPool state, leases, fairness and aging;
- perform local evidence research;
- route real model Work through the model execution fabric;
- validate work and route insufficient work through bounded rework;
- classify approved results through Guardian;
- retrieve local runtime memory and knowledge indexes.

### Act

- archive naturally approved tasks through Archivist.

This is a substantial cognitive substrate.  ACE is not an empty shell waiting
for another framework.

## Current Production-Active Inventory

| ID | Capability | Owner |
|---|---|---|
| OBS-RUNTIME-HEALTH | heartbeat and cycle closure | `ace_daemon.py`, `core/heartbeat.py` |
| OBS-FILESYSTEM | file and fragment observation | FileScanner / LocalArchaeologist |
| OBS-OBSERVATION | Runtime Observation ledger | Observation / ObservationToTask |
| OBS-GIT-MINE-SEED | mine-seed increment observation | MineSeedScanner |
| WORK-DISCOVERY | evidence-backed Work discovery | Discovery / ModelWorkDiscovery |
| WORK-ALLOCATION | category allocation | AutonomousWorkAllocation |
| WORK-ADMISSION | task/model/evidence admission | Admission modules |
| TASKPOOL-LIFECYCLE | state and lease lifecycle | TaskPool |
| TASKPOOL-FAIRNESS | fairness and aging | TaskPool / task roles |
| RESEARCH-LOCAL | local evidence research | Researcher |
| EXECUTION-MODEL-POOL | model execution fabric | MinerPool |
| EXECUTION-PROVIDER-HEALTH | health/fallback trace | ProviderWatchdog |
| VALIDATION-TASK | validation and rework | Validator |
| GOVERNANCE-GUARDIAN | knowledge classification | Guardian |
| KNOWLEDGE-ARCHIVE | approved task archive | Archivist |
| KNOWLEDGE-MEMORY-INDEX | local retrieval | MemoryIndex / Memory |
| KNOWLEDGE-DAILY-GROWTH | cognitive supply ledger | DailyGrowthLedger |

## What ACE Owns but Cannot Yet Trust as Fully Ready

### Production degraded

| Capability | Measured reason |
|---|---|
| A-share data observation | independent-source, freshness, completeness and coverage gates not satisfied |
| Skill generation | ran successfully, but generic and duplicated archaeology evidence makes quality provisional |
| Repository Curator | cycles close, but it repeatedly reports roughly the whole repository as new rather than a current-run delta |

### Code ready, not production loaded

Experience deposition now has tested stable identity, idempotency, legacy
loading, exclusive file creation and explicit failure observability.  The live
daemon started before the repair and has not naturally reloaded it.

```text
CAPABILITY_OWNED = YES
CODE_READY = YES
CURRENT_PRODUCTION_SEMANTICS = OLD
PRODUCTION_READY = NOT YET VERIFIED
```

### Tested but intentionally not wired

- Evidence Relevance Shadow Audit;
- read-only operator audits such as TaskPool Observer and Autonomous Audit.

These are real diagnostic capabilities.  Their absence from the production
decision path is a safety property, not necessarily a defect.

## Implemented Capabilities That ACE Has Forgotten or Not Proven

Nine code families exist without sufficient current production evidence:

| Capability family | Why not called active |
|---|---|
| External Web Learning | initialized, but no current governed learning output established |
| Shenwen strategic route | health evidence is not a production-task trace |
| Shenwen execution route | health evidence is not a production-task trace |
| Semantic Slice / clustering | conditional code exists; no current governed output established |
| Knowledge reconciliation package | pieces support DailyLearning, but no single current full-chain trace |
| Recovery and backup | backup artifacts exist; current restore was not exercised |
| Binary sensing / protocol analysis | substantial code, absent from current daemon |
| Companion / desktop interaction | code exists, absent from current daemon |
| Alternative autonomous/survival kernels | code exists, but activating it risks a second scheduler/worker architecture |

The correct action is not to activate all nine.  The correct action is to
retain their identity, owner, evidence and current non-active state so future
work does not rebuild them blindly.

## Historical Capabilities ACE Still Owns as Evidence

Historical capability is still an asset even when its runtime should not be
restored.

| Capability | Proven historical value | Current decision |
|---|---|---|
| Cross-civilization observation | R1 Keeper persisted a 2026-07-19 multi-repository observation; mine-seed has index-sync code | preserve and adapt semantics; do not run old single-repository sync as current catalog |
| Browser/Desktop/TG interfaces | Reality-interface exploration | preserve evidence; no current core integration |
| Roundtable variants | asset/policy/debate review attempts | do not merge by name; no current daily Roundtable |
| Law Discovery and Replay | evidence-to-policy governance work | historical, not current daemon production |
| Ops Cycle | one real daily handoff artifact | recover handoff semantics, not the old runtime |

This distinction lets ACE remember without resurrecting obsolete machinery.

## Blocked and Disabled Capabilities

Blocked:

```text
DailyLearning  → priority backlog globally blocks the learning window
Advisor        → Runtime/Data/Model/Risk/Advisor gates are not all ready
Risk           → required production risk evidence is missing
```

Deliberately disabled:

```text
Repository synchronization
Owner Telegram output
Automatic recommendation push
```

Disabled does not mean missing.  It means ACE owns the code or contract while
the authority or readiness gate intentionally prevents the side effect.

## Design-Only Capabilities

Two items remain questions rather than implementations:

```text
automated Today-in-the-Lab handoff
Experiment Work contract
```

They must not be reported as current ACE capability.  Their existence in the
catalog prevents them from being repeatedly rediscovered as if nobody had
considered them.

## Duplicate Capability Memory

ACE also owns exact duplicate implementations:

```text
Roundtable       ace_core/04_PROTOCOLS == ace_core/core
Awareness Loop   ace_core/04_PROTOCOLS == ace_core/core
Governor helper  ace_core/04_PROTOCOLS == ace_core/core
Recovery         ace_core/04_PROTOCOLS == ace_core/core == mine-seed/04_PROTOCOLS
```

These are not four additional capabilities.  They are one capability identity
with multiple implementation locations.  The catalog records the duplication
without deleting user work or choosing an owner prematurely.

## Repository Scope and Trust

The census used repository metadata and non-sensitive capability evidence from:

```text
ace_core
mine-seed
R1
r1-archaeology
r1-open-source-seed
```

`claw-soul` and `mine-seed-credentials` are now restricted to Git metadata.
Commit metadata for `claw-soul` indicates credential-related history, so no
further content archaeology is authorized without a separate secret-safety
review.  Both must remain outside ordinary scanning, model context,
publication and cross-repository copying.

## What ACE Does Not Yet Remember Automatically

The census exposes five self-knowledge gaps:

1. **No canonical repository catalog.** Current scanning privileges mine-seed
   rather than recognizing all civilization repositories and trust classes.
2. **No evidence-backed capability state updater.** Old ACTIVE labels survive
   after wiring disappears.
3. **No canonical capability owner map.** Exact copies and same-name/different-
   meaning implementations coexist.
4. **No capability-to-runtime trace link.** A module, test, health probe and
   production task call are not consistently distinguished.
5. **No explicit sensitive-source exclusion contract in capability discovery.**
   The safety rule exists operationally in this audit, not as a proven catalog
   boundary.

These are memory and provenance problems, not reasons to create a new execution
framework.

## Durable Catalog Contract Candidate

The JSON delivered with this report is a frozen audit snapshot, not a new
production registry.  If a durable catalog is later admitted, the smallest
useful record is:

```yaml
capability_id:
name:
primitive: Observe | Transform | Act
owner:
implementations:
evidence_class:
evidence_refs:
test_state:
runtime_state:
last_runtime_evidence_at:
blocker:
duplicates:
trust_boundary:
superseded_by:
```

It should describe capabilities, not start them.  Discovery may update a
Candidate view, but production state must come from runtime evidence.

## What Not to Do Next

- do not build another Capability Layer merely because an old report proposed
  one;
- do not mark all code families ACTIVE;
- do not activate alternative autonomous kernels;
- do not restart old heartbeat or ops-cycle loops;
- do not merge same-name Roundtables;
- do not delete exact duplicates before owner and imports are proven;
- do not scan credential-repository content;
- do not let a health probe upgrade a production execution capability;
- do not let a manual report masquerade as an automated daily handoff.

## Recommended Next Validation

The next step is not capability creation.  It is owner and evidence validation:

1. wait for the natural daemon reload and validate the repaired Experience
   capability through one real archive;
2. verify each `PRODUCTION_ACTIVE` item against a bounded current-run artifact;
3. determine canonical owner and import consumers for the four exact duplicate
   groups;
4. define repository identity and trust metadata without scanning sensitive
   content;
5. compare the frozen catalog with a later snapshot to detect forgotten wiring,
   not to trigger work automatically.

## Final Verdict

```text
CAPABILITY_FAMILIES_CENSUSED          47
CURRENT_PRODUCTION_ACTIVE             17
CURRENT_PRODUCTION_DEGRADED            3
CODE_READY_RELOAD_PENDING              1
TESTED_NOT_WIRED                       2
IMPLEMENTED_UNVERIFIED                 9
HISTORICAL_RUNTIME                     5
BLOCKED                                3
DISABLED                               3
DESIGN_ONLY                            2
SUPERSEDED_OR_DUPLICATE                1
SENSITIVE_EXCLUDED                     1

NEW_PRODUCTION_CAPABILITY_ADDED        0
PRODUCTION_CODE_CHANGED                0
DAEMON_RESTARTED                       NO
TASK_CREATED                           NO
MODEL_CALLED                           NO
```

ACE already owns a capable execution and governance substrate, several dormant
or historical capability families, and multiple duplicate implementations.
Its next architectural gain is to preserve capability identity, ownership,
evidence and state over time—not to increase the number of things it can do.
