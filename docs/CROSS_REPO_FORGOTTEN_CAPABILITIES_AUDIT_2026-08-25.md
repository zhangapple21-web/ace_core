# Cross-Repository Forgotten Capabilities Audit — 2026-08-25

> Mode: read-only archaeology and convergence design.  No production code was
> changed by this audit, no daemon was restarted, no task or model call was
> created, and no repository content was moved, deleted, committed, or pushed.

## Executive Answer

ACE's civilization evidence is not contained in `mine-seed` alone.  The local
drawer contains seven Git checkouts with different roles and trust boundaries:

```text
ace_core              current core and production daemon
mine-seed             historical civilization protocols and runtime artifacts
R1                    public ancestor source
r1-archaeology        evidence correction and provenance review
r1-open-source-seed   public reconstruction seed
claw-soul             not publicly observable; private or unavailable unproven
mine-seed-credentials sensitive; excluded from content archaeology
```

Five remotes are publicly observable through anonymous GitHub metadata.
`claw-soul` and `mine-seed-credentials` return anonymous 404 and must not be
called private merely from that response.  The latter is treated as sensitive
regardless of remote visibility and was not searched for capability content.

The forgotten `ops` family contains useful lifecycle semantics, but its old
implementations are not safe production candidates.  The current consolidation
rule should be:

```text
recover proven semantics
map them onto the current lifecycle
do not restart historical runtimes
do not merge files merely because their names match
```

## Evidence Classes

Every claim in this audit uses one of:

```text
DESIGN_EVIDENCE    documentation, comments, declared topology, persona text
PRODUCTION_CODE    executable implementation or a callable production path
RUNTIME_ARTIFACT   persisted output proving that a path executed
CURRENT_RUNTIME    live process plus current-run trace or persisted state
```

File presence and a `Running` label are not runtime evidence.

## Current Canonical Runtime

The only observed current ACE lifecycle process is `ace_core/ace_daemon.py`.
Its active chain includes TaskPool, Researcher, Validator, Guardian, Archivist,
ExperienceDeposition, Work Discovery, DailyLearning, and Curator.  It does not
call `ops_cycle`, `awareness_loop`, `roundtable`, `RoundtableMeeting`, or the
mine-seed heartbeat debate path.

Therefore:

```text
CURRENT_RUNTIME_OWNER = ace_core/ace_daemon.py
SECOND_SCHEDULER_ALLOWED = NO
HISTORICAL_HEARTBEAT_RESTART_ALLOWED = NO
```

## Forgotten Capability Matrix

| Capability | Repository / path | Design | Code | Runtime artifact | Current runtime | Disposition |
|---|---|---:|---:|---:|---:|---|
| Ops Cycle | `mine-seed/04_PROTOCOLS/ops_cycle.py` | yes | yes | one 2026-07-10 report | no | recover handoff semantics only |
| Asset Roundtable | `ace_core/04_PROTOCOLS/roundtable.py` | yes | yes | none found | no | archaeology candidate |
| Staged Asset Roundtable copy | `ace_core/core/roundtable.py` | inherited | exact copy | none found | no | duplicate-owner decision required |
| Persona / debate Roundtable | `mine-seed/04_PROTOCOLS/roundtable.py` | yes | yes | no recent debate artifact | no | do not restore as-is |
| Governor RoundtableMeeting | `ace_core/core/governance/governor_protocol.py` | yes | yes | none found | no | map semantics before reuse |
| Awareness Loop | `ace_core/core/awareness_loop.py` | yes | yes | none found | no | do not wire as-is |
| Historical Awareness Loop | `mine-seed/04_PROTOCOLS/awareness_loop.py` | yes | yes | no current artifact | no | do not wire as-is |
| Heartbeat Debate | `mine-seed/04_PROTOCOLS/heartbeat.py` | yes | yes | no current heartbeat/debate log | no | second-runtime risk |
| Advisor policy review | `mine-seed/05_TOOLS/advisor/policy_manager.py` | yes | yes | POLICY-002, 2026-07-14 | no current Advisor readiness | keep application-isolated |
| CouncilOfThree | generated/history claims | yes | no source proof | none | no | rejected as production fact |
| Daily Lab Review | current requirement | yes | no unified path found | TODAY_IN_THE_LAB is manual audit | no | semantic recovery candidate |

## What `ops_cycle` Proves

`mine-seed/02_MEMORY/ops_logs/ops_20260710T154013.json` is a real historical
runtime artifact.  It records:

```text
Discovery
→ Candidate
→ Roundtable
→ Archivist
→ Repository
→ Memory
→ Evolution
```

It therefore proves that ACE previously attempted a daily-laboratory handoff,
not merely that somebody wrote a blueprint.

It does not prove a stable continuous service:

- only one explicit ops-cycle report was found;
- its repository step committed and staged nothing;
- no current `ops_cycle.py` process exists;
- no current daemon calls it.

The old implementation also conflicts with current production invariants.  Its
Roundtable step directly calls `gpt-4o-mini`, parses free-form JSON, and decides
asset admission without the current ModelTaskAdmission, TaskPool, Validator,
Guardian, or evidence-governed lifecycle.  Its Discovery examines a single
workspace's dirty Git status and recent Downloads.  Its final Evolution step
generates a seed for tomorrow.  Running it now would create a second work loop
and could manufacture work from activity rather than admitted evidence.

Classification:

```text
OPS_DAILY_HANDOFF_SEMANTIC       RESTORE CANDIDATE
OPS_SINGLE-WORKSPACE_DISCOVERY   SUPERSEDED
OPS_DIRECT_MODEL_GOVERNANCE      DO NOT RESTORE
OPS_SECOND_LOOP                  DO NOT START
OPS_AUTOMATIC_TOMORROW_SEED      DO NOT RESTORE AS-IS
```

## Roundtable Findings

There is no single historical Roundtable.  The name refers to at least five
different mechanisms:

1. a simple three-rule asset review in `ace_core/04_PROTOCOLS/roundtable.py`;
2. an exact staged copy in `ace_core/core/roundtable.py`;
3. a persona/red-blue debate engine in `mine-seed/04_PROTOCOLS/roundtable.py`;
4. an in-memory `RoundtableMeeting` class in Governor Protocol;
5. an Advisor-specific policy review in `mine-seed`.

They have different subjects, gates, outputs, and risk.  Combining them by name
would be a semantic error.

The current truthful status is:

```text
ROUNDTABLE_CODE_EXISTS             YES
HISTORICAL_EXECUTION_EXISTS        YES, limited and workload-specific
DAILY_LAB_ROUNDTABLE_ACTIVE        NO
ACE_DAEMON_INTEGRATION             NO
ROUNDTABLE_HEALTH_VERIFIED         NO
```

The useful recoverable semantic is not a persona council.  It is a bounded,
multi-perspective review of already-existing Observation, Evidence, Candidate,
and Work, answering:

```text
what happened today;
what matters most;
what should Execute;
what should Learn;
what should Watch;
what should Block or Defer.
```

This semantic must not create Work or call a model merely to hold a meeting.

## Exact Duplicate Inventory

SHA-256 comparison found confirmed byte-identical copies:

| Content | Copies | Status |
|---|---:|---|
| ACE asset Roundtable | `04_PROTOCOLS/roundtable.py`, `core/roundtable.py` | exact duplicate |
| ACE Awareness Loop | `04_PROTOCOLS/awareness_loop.py`, `core/awareness_loop.py` | exact duplicate |
| ACE Governor helper | `04_PROTOCOLS/governor.py`, `core/governor.py` | exact duplicate |
| Recovery Protocol | ACE `04_PROTOCOLS`, ACE `core`, mine-seed `04_PROTOCOLS` | exact cross-repo duplicate |

The `core/roundtable.py` and `core/awareness_loop.py` copies are staged additions
in the dirty `ace_core` worktree and have no committed history of their own;
their `04_PROTOCOLS` twins trace to the existing repository commit.  This is
strong duplication evidence, but not authorization to delete either copy.

Near-name files that are not identical must remain separate until contracts are
mapped:

```text
mine-seed roundtable.py  != ace_core roundtable.py
mine-seed heartbeat.py   != ace_core core/heartbeat.py
mine-seed awareness_loop != ace_core awareness_loop
```

## Why Old `Running` Labels Are Not Trusted

`mine-seed/CURRENT_STATE.md` labels RoundTable as running, but
`mine-seed/04_PROTOCOLS/self_evolution.py` explicitly records its Roundtable
audit as skipped because a new architecture was pending integration.  Current
process inspection also found no Roundtable, heartbeat, ops-cycle, or awareness
loop process.  Production code and runtime artifacts take precedence over a
status table.

## Consolidation Ownership Proposal

This is a design recommendation, not a file migration:

| Concern | Proposed single owner | Historical sources become |
|---|---|---|
| Scheduling and daily cycle | current `ace_daemon.py` | evidence and semantics only |
| Work discovery | current Work Discovery / Allocation | candidate-source adapters only |
| Task lifecycle | current TaskPool and roles | no parallel queue |
| Validation | current Validator and Guardian | perspectives, not alternate gates |
| Distillation | current Experience / Archivist path | recovery evidence |
| Daily handoff | thin current-run report contract | ops semantics, not ops runtime |
| Application policy review | application-local Advisor boundary | never ACE Core governance |
| Repository discovery | cross-repository catalog | no credentials content |

## Restore Semantics

Candidates worth preserving after current Experience production verification:

- daily handoff: today's changes, decisions, failures, retained knowledge;
- multi-perspective classification: Execute / Learn / Watch / Block / Defer;
- explicit Candidate-to-Admission separation;
- failure and pending evidence carried into the next observation window;
- cross-repository discovery with repository identity and trust boundary;
- `NO_VALUABLE_WORK` when nothing is admitted.

## Do Not Restore As-Is

- old heartbeat or `ops_cycle --loop`;
- direct model call from governance;
- CouncilOfThree or persona council;
- fixed activity or tomorrow-seed generation;
- direct Experience writes before current governance;
- single-workspace Git status as civilization discovery;
- Advisor Roundtable as ACE Core governance;
- duplicate files merged solely by filename;
- sensitive repository contents entering model context or ordinary scanners.

## Safe Consolidation Sequence

1. Finish production verification of Experience identity and failure
   observability after a natural daemon reload.
2. Freeze an evidence table for all Roundtable/Ops variants using design/code/
   artifact/current-runtime classes.
3. Define one cross-repository catalog contract containing repository identity,
   visibility confidence, trust class, last observed commit, and capability
   ownership.  Do not copy repository content into the catalog.
4. Decide canonical ownership for the four exact duplicate groups before any
   deletion or move.
5. If evidence still supports it, design a shadow-only Daily Lab Review over
   existing current-run facts.  It may recommend Execute/Learn/Watch/Defer but
   may not create Work or mutate production.
6. Only after shadow evidence demonstrates missing value should an ADR consider
   production integration.

## Current Verdict

```text
CROSS_REPOSITORY_SCOPE_IDENTIFIED       YES
FORGOTTEN_OPS_RUNTIME_ARTIFACT_FOUND    YES
EXACT_DUPLICATES_CONFIRMED              YES
SAFE_TO_DELETE_OR_MERGE_NOW             NO
SAFE_TO_RESTART_OLD_OPS                 NO
ROUNDTABLE_CURRENTLY_RUNNING            NO
DAILY_HANDOFF_SEMANTIC_WORTH_RECOVERING CANDIDATE
PRODUCTION_CHANGE                       NO
```

The highest-value recovery is the forgotten daily handoff and review semantic,
not another scheduler or another council.  The highest-value consolidation is
to assign one owner per capability while preserving the old repositories as
evidence until provenance and runtime replacement are proven.
