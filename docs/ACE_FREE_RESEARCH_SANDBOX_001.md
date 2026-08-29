# ACE Free Research Sandbox v1

## Purpose

This is a local, durable place for speculative research to survive without
touching ACE production. It absorbs the prior `Experiment Zone`, `Replay →
Shadow`, and distillation semantics while avoiding their historical second
runtime, direct model governance, and automatic publication paths.

## Boundary

```text
local / historical / inbox food
  -> free-zone autonomous discovery
  -> autonomous judgment + claim
  -> isolated execution (PASS / FAIL / INCONCLUSIVE are all normal)
  -> immutable local record
  -> distill every outcome
  -> court validates only the free-zone -> production edge
  -> PASS: proposal-only / FAIL: counterexample / INCONCLUSIVE: open question
  -> a separately governed possible real-world adoption
```

The sandbox never writes TaskPool, Runtime, production evidence, Advisor, Risk,
Telegram, broker, or Experience. A proposal is not an admitted task, a model
call, a recommendation, or a delivery instruction. The boundary does not mean
that experiments need production admission before they are allowed to exist.

## Storage

The caller chooses the root. The canonical local root is
`07_SANDBOX/free_research/` and contains:

* `experiments/` — clean raw experiments, including failed hypotheses;
* `quarantine/` — polluted/untrusted material kept away from production;
* `distillations/` — every outcome after compression;
* `promotion_proposals/` — non-executable copies of clean passed work only;
* `inbox/` — new food for autonomous free-zone work;
* `SANDBOX_MANIFEST.json` — explicit non-production contract;
* `constitution/` — compressed design seeds, including the R1 ecology route;
* `reports/` — the latest society, court, and museum-observation records.

Records use atomic writes, experiment hashes, proposal hashes, source-record
hashes and timestamped contracts. Failed and inconclusive work remain evidence;
they are not silently discarded or promoted.

## Sandbox society

`SandboxSociety` gives the free zone a durable social structure without adding
a second ACE runtime or any permanently-running model process:

| Role | May do | Cannot do |
|---|---|---|
| Inbound food | offer local, historical, inbox or explicitly preserved outside material | obtain production authority |
| Free zone | discover, judge, claim and execute isolated experiments | alter production assets |
| Curator / smelter | distill every outcome | create a production task or promotion |
| Court | verify integrity only at the free-zone -> production boundary | gate discovery, claims, execution, approve, repair or promote |
| Teacher | view post-execution proposal and counterexample queues | approve automatically or deliver externally |

`ops/run_museum_archaeology_turn.py` is an inbound observer only: it writes a
versioned museum-food record and does not create an experiment or run the
Court. `ops/run_free_zone_autonomy_turn.py` is the active ecological turn: it
forages that food (plus local food), selects and claims work without human or
court pre-approval, then executes a bounded batch of isolated experiments.
`ops/run_free_research_sandbox_turn.py` is the later distillation/court turn.
Repeated turns are idempotent once all
currently discoverable food has been claimed: no new material gives
`NO_NEW_FREE_ZONE_WORK` or `NO_NEW_SANDBOX_WORK`.

Failure is a normal output. `FAIL` becomes `COUNTEREXAMPLE_ONLY`; an
`INCONCLUSIVE` result becomes `OPEN_QUESTION`; only pollution is marked
`QUARANTINED`. Quarantine protects production; it does not erase the material
or turn the free zone into a permission queue.

The loop is deliberately metabolic rather than archival: a
`COUNTEREXAMPLE_ONLY` or `OPEN_QUESTION` distillation is itself new food. The
next autonomous turn can claim it and create a separate re-observation
experiment while leaving the parent failure intact. This is how the ecology
learns from being wrong instead of merely filing the mistake away.

`LazyCatAudit` is a separate post-execution opponent, not an entrance guard.
It checks only whether a distilled research shape has observable lineage,
bounded method, evidence, an intact boundary, and an explicit dissent
blueprint. Missing dimensions become durable challenge cards for a later free
zone turn. A fitness verdict is never a production, investment, or truth
verdict.

The daily `ACE 自由区每日推演与蒸馏` automation is the only scheduled writer for
the free-zone turn. It runs museum observation, autonomous free-zone execution
and later all-outcome distillation, with a resource cap of three new local
experiments per daily turn. The hourly duty shift only reads the latest sandbox
report into its daily ledger. This avoids two schedules racing to write the
same ecology while keeping the free zone visible to the curator.

When local food is exhausted, external foraging is deliberately small: a
catalogued public GitHub repository is first observed through metadata; a
later turn may read a single README response and retain only a 24 KiB-bounded
digest and structural summary. It does not preserve the README body, execute
instructions, follow links, clone repositories, install dependencies, or make
production claims.

Current local Git changes are also eligible food, but only as a protected
shape: the free zone reads the repository head plus a bounded, credential-path
redacted list of changed path names. It retains a path digest and counts, not
diff bodies, and produces an `INCONCLUSIVE` question that requires a later
specialized test before any design conclusion.

## Design-seed observability

`R1_ECOLOGY_CONSTITUTION_v1.json` is a design seed, not executable authority.
Each society report records whether its route and invariants were observed and
labels the result `sandbox_report_only`. `DailyShift` may surface the court
state, experiment count, teacher queue, and design-seed status, but always
writes `production_integration=false` and `recommendation_authority=false`.
This makes continuity visible without allowing a historical philosophy to
silently become a production rule.

## External design references

The implementation uses an isolated directory and atomic persistence locally.
For code changes that need a separate checkout, Git worktrees are the preferred
external isolation mechanism: https://git-scm.com/docs/git-worktree . A Python
virtual environment may be used for dependencies but does not replace data and
runtime isolation: https://docs.python.org/3/library/venv.html .
