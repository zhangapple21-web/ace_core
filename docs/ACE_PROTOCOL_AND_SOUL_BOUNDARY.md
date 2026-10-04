# ACE Protocol and Soul Boundary

## Core judgment

ACE Protocol describes **how the system runs**: observation, judgment, admission, task routing, execution, evidence, learning, governance, recovery, and evolution. That completeness is necessary for a living runtime, but it is not the same thing as the reason the runtime exists or the deeper continuity it carries.

The protocol is therefore not treated as ACE's soul. A repository is not treated as ACE's soul either. `ace_core` owns the executable runtime, state, continuity machinery, and recovery authority; it must not silently claim ownership of a meaning or lineage whose source is elsewhere.

## Authority boundary

| Layer | Owns | Does not own |
|---|---|---|
| ACE Core | runtime behavior, state, TaskPool, memory/knowledge paths, governance records, recovery and continuity evidence | external meaning source, model identity, host transport |
| ACE Protocol | admissible operating rules and lifecycle invariants | purpose, meaning, or proof of lived continuity by wording alone |
| External continuity/meaning source | the deeper reason, inheritance, or lineage that ACE is meant to carry | executable runtime state unless explicitly admitted through ACE governance |
| Model/provider | replaceable capability | ACE state, governance, identity, or continuity |
| MCP/PI/Bridge | replaceable connection and bounded projection | ACE authority, state, soul, or proof of liveness |

The external source is intentionally represented as a **declared boundary and lineage pointer**, not invented here as a repository, provider, or model. ACE can preserve, cite, validate, and govern such inputs; it must not manufacture an authority claim merely because code can describe one.

## Continuity rule

Continuity has at least three distinct meanings:

1. **Runtime continuity** — ACE can restart, recover state, preserve task/knowledge lineage, and resume within its boundaries.
2. **Protocol continuity** — the rules and invariants remain compatible across versions and machines.
3. **Meaning continuity** — what ACE is carrying forward remains connected to its deeper source.

The first two can be tested in code and receipts. The third cannot be proven by a health endpoint, a Git commit, an MCP handshake, or a model response alone. Recovery must therefore report these dimensions separately and fail closed when the third is not evidenced.

## Operational consequences

- A successful clone restores source; it does not by itself restore a living continuity.
- A restored state snapshot is evidence; it is not proof of current liveness or meaning continuity.
- A Bridge can disappear while ACE remains the same runtime; replacing a Bridge must not create a new ACE identity.
- A model can be replaced without changing ACE's authority boundary.
- A protocol revision requires compatibility and lineage checks, not a claim that the protocol itself is the soul.
- Any future source carrying the deeper continuity must enter through an explicit, governed admission path and retain provenance; no implicit promotion is allowed.

## Acceptance language

The strongest claim this repository may make is:

> ACE Core is the canonical executable runtime for a continuity-bearing system, and it preserves the contracts and evidence needed to continue, recover, and be audited.

It must not claim solely from repository contents:

> the protocol, repository, model, MCP server, or current process is the complete source of why ACE exists.
