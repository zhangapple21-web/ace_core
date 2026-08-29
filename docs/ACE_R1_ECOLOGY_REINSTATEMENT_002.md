# ACE R1 Ecology Reinstatement 002

## Decision

ACE is not reusing R1's files as a costume. It is reinstating the ecological
relationships that made R1 useful while keeping the current production
boundary intact.

The free zone is not a preliminary audit queue. It has authority to discover,
select, claim, and execute isolated experiments. The only hard boundary is
between a free-zone artifact and a real ACE production change.

## Actual food chain

```text
R1/R2 history, constitution, sandbox inbox, failures, local Git, public repo metadata
                              |
                              v
                    FreeZoneAutonomy
              discover -> select -> claim -> execute
                              |
                              v
                   append-only experiment record
                              |
                              v
                    SandboxSociety / smelter
          PASS -> PROPOSAL_ONLY
          FAIL -> COUNTEREXAMPLE_ONLY
          INCONCLUSIVE -> OPEN_QUESTION
          polluted -> QUARANTINED
                              |
                              v
                  counterexamples / questions feed next turn
                              |
                              v
       Court verifies integrity only at free-zone -> production edge
                              |
                              v
       separately governed current ACE Admission / Validator / Risk
```

## Role changes from the earlier, over-restricted shape

| Role | Now does | Explicitly does not do |
| --- | --- | --- |
| Inbound food | Supplies local history, design seeds, sandbox inbox material, failures, and only-after-local-empty one public GitHub metadata source | Assert production truth |
| Free zone | Automatically discovers, judges, claims, and executes a resource-bounded batch | Ask teacher/court permission first; mutate production |
| Smelter / curator | Distills every completed result | Treat FAIL or INCONCLUSIVE as an exception |
| Court | Validates record, distillation, and proposal hashes after execution | Gate free-zone intake, claims, execution, or approve adoption |
| Teacher | Sees post-execution proposal and counterexample queues | Become an automatic dispatcher or sender |
| Production ACE | May only receive a separately revalidated candidate | Consume a free-zone record directly |

## Evidence of the first live ecology turn

On 2026-08-27 the local free zone:

1. autonomously discovered constitutional work;
2. claimed and executed three isolated experiments without a teacher or court
   entry decision;
3. produced two `PASS` and one `FAIL`;
4. distilled the failure into `COUNTEREXAMPLE_ONLY`;
5. used that counterexample as the source of a separate automatic
   re-observation experiment;
6. completed with court integrity status `VALID` and
   `production_integration=false`.

This demonstrates a real loop: failure is food, not a terminal error.

## Five factories reinstated as a material chain

The R1 source describes factories as a relation, not a personality list. The
free-zone implementation now stores the relation under `factories/`:

```text
inbound food
  -> recovery factory: immutable thread (no raw protected payload retained)
  -> marking factory: lineage and boundary labels
  -> imitation factory: DIRECT_OBSERVATION + COUNTEREXAMPLE_SEARCH worlds
  -> processing factory: one selected world linked to an experiment receipt
  -> courier: public-only external return receipt, where external food exists
  -> ruin smelter: all-outcome distillation receipt
  -> Court: validates the existing record/distillation/proposal outbound chain
```

The counterexample world starts as `BLUEPRINT_ONLY`: it is intentionally not
reported as a result until a dedicated executor exists. That prevents the
ecology from faking a rival conclusion merely to make the world look busy.
Factory records remain sandbox-only and immutable; none creates a production
task, recommendation, model call, or external delivery.

## Productive cat vs Lazy Cat

The free zone is not an internal quality committee. Its selection policy is
bounded, source-fair resource allocation followed by descriptive semantic-slice
exploration: a recorded seed probabilistically chooses which under-observed
research shape to try within the current source allocation. The slice may
describe source, epistemic shape, intended sandbox stance, and provenance. For
Lazy Cat challenges it may additionally describe only the immutable challenge's
already-recorded structural-gap signature (for example
`boundary_intact+dissent_blueprint`), so different repair questions do not get
silently collapsed into a single bucket. It never reads an execution outcome,
profitability, market relevance, quality, or production value. Every seed,
candidate-snapshot hash, slice weight, draw, and derived selection is retained
for replay. The post-execution `LazyCatAudit` evaluates
completed, distilled research shapes on five non-production dimensions: observable
lineage, bounded method, observable evidence, intact boundary, and an explicit
dissent blueprint. It produces one of three sandbox verdicts:

* `FIT_FOR_TEACHER_REVIEW` — structurally complete enough for teacher review;
  not a truth, profitability, or production verdict.
* `RETURN_TO_FREE_ZONE` — preserves the artifact and creates a named challenge
  for the missing dimensions.
* `OPEN_CHALLENGE_RETAINED` — a challenge has no specialized resolution
  executor yet, so it remains honestly open rather than recursively faking a
  solution.

This creates the game: the productive cat expands the ecology; Lazy Cat
compresses it into reviewable material or explicit challenges; challenges are
food for a later free-zone turn. Lazy Cat cannot block intake, mutate an
experiment, approve production, or make a recommendation.

## Deliberately unfinished work

These are not hidden gaps; they are the next distinct layers.

1. **Specialized experiment executors.** Current autonomy can run
   constitutional, inbox, counterexample, museum-history, path-redacted local
   Git, repository-metadata and bounded README-shape probes. A real data-source, historical-replay,
   code-compatibility, or client-delivery experiment still needs its own
   isolated executor and test contract.
2. **Richer external learning.** The automatic external forager now reads one
   public GitHub metadata record and, only on a later no-local-food turn, one
   public README response. The README executor retains only a 24 KiB-bounded
   hash/shape summary: it never executes, installs, clones, follows links, or
   treats external prose as authority. Release-note and source-tree probes are
   still future isolated executors.
3. **Model-role simulation.** The ecology now has durable functional roles,
   but not a permanently running model council. If added, it must consume
   sandbox food and write only sandbox artifacts; it must not become a second
   production daemon or a way around market-data gates.
4. **Reality adopter.** There is intentionally no direct proposal receiver in
   production. A later adopter must be separately designed to re-run current
   Admission, Validator, Risk, freshness, lineage, and authorization checks.

5. **MengPo / decay contract.** The original ecology's memory-decay role is
   only partially represented: polluted material is quarantined and all
   threads are retained. No automatic deletion or stale retirement is enabled
   until a separate, reversible retention/return-to-observation contract is
   implemented.

The daily 18:30 automation owns the free-zone write turn. The hourly duty
automation remains an observer of the resulting report and never races it.

Museum archaeology is now strictly the first inbound step. It can publish a
hash-linked `museum_history` food record, but cannot create an experiment,
invoke the Curator, or invoke the Court. The autonomous free zone claims and
rechecks that record in a later step; only the later society turn distills it
and audits the outbound boundary. This keeps the food chain causal rather than
letting an observer smuggle a pre-approved result into the ecosystem.
