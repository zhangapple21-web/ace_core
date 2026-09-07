# ACE Git Material Classification 001

## Purpose

Git is ACE's portable civilization map, but a working checkout also contains
machine-local evidence.  This inventory separates reviewable source and
provenance from generated state before any `.gitignore`, staging, pull, merge,
or push decision.  It is a read-only classification; it changes no remote and
does not stage files.

## Snapshot

- Repository: `ace_core`
- Remote: `origin = https://github.com/zhangapple21-web/ace_core.git`
- Remote comparison previously established: ahead `0`, behind `0`
- Working tree: deliberately dirty; never use `git add .`
- Observed untracked top-level material at review: `07_SANDBOX` (296 files),
  `core` (32), `ops` (47), `docs` (13), `agent_team` (20),
  `outputs` (24), `08_GOVERNANCE` (3), plus task-history and temporary
  PowerShell scripts.

## Classification

| Area | Classification | Commit rule | Reason |
| --- | --- | --- | --- |
| `core/**/*.py` | Source | Review and commit in a themed source change | Portable behavior and contracts |
| `ops/test_*.py` | Tests | Commit with the source behavior they verify | Reproducible regression evidence |
| `ops/*.py` | Operator tooling | Review individually; commit only reusable tools | Some are durable tools, some are probes |
| `docs/*.md` | Design / decision provenance | Commit in matching thematic change | Architecture and governance should travel with code |
| `07_SANDBOX/free_research/constitution/**` | Reusable governance schema | Review for secrets; eligible for a dedicated governance change | Constitutions and READMEs are portable contracts |
| `07_SANDBOX/free_research/{experiments,distillations,reports,marks,receipts}/**` | Generated sandbox evidence | Do not blanket-ignore or commit automatically | Mixed audit value and high churn; choose a curated, redacted evidence set per decision |
| `08_GOVERNANCE/**/*.json*` | Instance runtime ledger | Never add automatically; redact and select only when a stable schema/example is needed | Can expose local provider/cost/execution history and is not source |
| `agent_team/**/*.py` | Collaboration support source | Review separately before a collaboration-only change | Potentially reusable, but not ACE runtime |
| `agent_team/{state.json,active_work_manifest.json,**/state.json,**/task-board.md,**/packets/**}` | Local coordination state | Keep local by default; no automatic commit | Ephemeral task ownership and worker material, not application control plane |
| `outputs/**` | Generated outputs / logs / probe artifacts | Keep local; curate a redacted report only when it is decision evidence | Includes logs, watchdog state, research output and media |
| `.task_creator_history.json` | Local cache | Keep local; ignore only after checking it has no intentional provenance role | Machine execution history |
| `temp_*.ps1` | Transient operator scripts | Keep local; ignore after an explicit cleanup review | Not portable source unless intentionally promoted |

## Decision

Do **not** alter `.gitignore` in this change.  A blanket rule for
`07_SANDBOX`, `08_GOVERNANCE`, `agent_team`, or `outputs` would either erase
valuable provenance from the map or accidentally publish local runtime data.

The safe next Git operation is a manual, themed review with these boundaries:

1. Runtime continuity and Daily Shift source/tests/docs.
2. Free-zone ecology source/tests/constitution (not bulk generated artifacts).
3. MinerPool resident governance source/tests/docs.
4. Finance/evidence research source/tests/docs.
5. Environment Awareness source/tests/docs.

Each theme needs a secret scan and a file-by-file staging list.  No pull,
merge, rebase, commit, or push is implied by this classification.
