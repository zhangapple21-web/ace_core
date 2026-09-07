# ACE Human Context Archaeology 001

## Decision

The historical word **perception** did not primarily mean desktop monitoring.
It described a human-facing meaning layer: translate a real observation into
what it may mean for the system's owner, while preserving the distinction
between fact, inference, and hypothesis.

```text
Reality / evidence
  -> Observation
  -> Meaning hypothesis
  -> bounded, reviewable candidate
  -> human confirmation
  -> existing governed work path
```

This is compatible with the present Environment Awareness boundary, but it is
not the same capability.  `environment_context.py` supplies one minimized
technical feature; it does not implement a user model, infer mood, record
private activity, or create work.

## Recovered evidence

| Historical artifact | Evidence-backed semantic | Status for ACE |
| --- | --- | --- |
| `mine-seed/02_MEMORY/recent_memory/daily/2026-06-19.md` | Observation was extended to `O -> E -> M -> C -> R`; the missing `M` was "what does this mean", not another data collector | `ADAPT` |
| `mine-seed/02_MEMORY/recent_memory/cases/case_20260621_001_monitoring_blind_spot.md` | Fact, inference, and hypothesis must remain distinct; a monitoring blind spot is not a production incident | `ABSORB` |
| `claw-soul/lab_02/01_IDENTITY/USER.md` | Conversation should remain natural and reality-first; the owner is not an administrator, test fixture, or raw data source | `ADAPT` as interaction boundary, not a personal data store |
| `claw-soul/lab_02/02_MEMORY/project/meaning-layer-research-20260619.md` | Meaning/reflection needed evidence lineage, relevance and expiry rather than an uncontrolled memory pile | `ADAPT` |
| `mine-seed/02_MEMORY/recent_memory/daily/2026-06-19.md` | The three historical gaps were memory routing, self-evaluation, and rhythm awareness | `VERIFY_CURRENT_STATE` before claiming they are solved |
| R1 free exploration notes | A system needs a non-production wandering/research space; it must not be turned into a production-task quota | Already represented by the governed Free Zone; retain the egress boundary |

## What the historical system actually contributed

### 1. Meaning is a translation lens, not private surveillance

An ACE report may responsibly add a **meaning hypothesis** only when it is
grounded in an existing evidence bundle and framed as conditional, for example:

```text
Fact: a repeated provider failure blocked an admitted research task.
Meaning hypothesis: this threatens continuity and warrants a bounded recovery
candidate.
```

It may not fabricate a claim about the user's emotions, intent, finances,
relationships, screen activity, or private communications.

### 2. The "owner observation axis" is not a behavioural profile

The reusable part is a review question:

```text
Does this evidence-backed result reduce a real burden, preserve continuity,
or answer a currently expressed concern?
```

It is not a license to keep an always-on biography, collect ambient personal
signals, or convert model guesses into tasks.  Explicit user input and the
currently authorized project context remain the only human-facing sources.

### 3. Reality and observation must be independently auditable

Every human-context statement must declare one of:

```text
FACT            direct, traceable evidence
INFERENCE       evidence-backed interpretation
HYPOTHESIS      proposed explanation needing review
UNKNOWN         observation coverage is insufficient
```

`UNKNOWN` is not a failure condition and cannot trigger an automatic repair,
model call, escalation, or financial action.  This restores the R1 monitoring
blind-spot lesson without reviving its old runtime.

### 4. Continuity is better carried by small evidence lines than by personas

The portable inheritance is an append-only, expiring evidence line with:

```text
source_ref, observed_at, claim_class, meaning_hypothesis,
expiry, review_status, counterexample_ref
```

Any future implementation must retain only the minimized claim and lineage.
It must not copy raw chats, full screen captures, browser history, or an
unbounded personal dossier into ACE.

## Current gaps and non-claims

- Current ACE has a Daily Shift, Experience, Free Zone and environment-context
  boundary, but this archaeology does **not** establish that it has a working
  Meaning layer, complete memory router, or validated self-evaluation loop.
- The historical documents demonstrate design and operating traces, not a
  current production permission to collect human-environment data.
- The present workspace-only context contract is intentionally insufficient to
  infer user intent; it remains `INCONCLUSIVE` by design.

## Safe next implementation gate

Before adding another sensor, introduce a **pure, injected Meaning Line
validator** with fixtures only.  It should validate claim class, evidence
references, expiry, and a prohibition on raw personal payloads.  It must have:

1. no collector and no daemon consumer;
2. no TaskPool/model/message/file-mutation action;
3. a `HYPOTHESIS` default for any owner-facing translation;
4. explicit human confirmation before a real research question reaches the
   existing Work Discovery path.

Only after that boundary has regression evidence should a separate opt-in
scope be considered.  The next sensible question is not "what else can ACE
watch?" but "can ACE distinguish an evidence-backed human-relevant hypothesis
from an attractive story?"
