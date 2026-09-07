# ACE Environment Awareness Archaeology 001

## Decision

`ACE Environment Awareness` is a candidate Core input capability, not a pet
feature, desktop surveillance service, or automatic work dispatcher.  This
document records the boundary before any new sensor is implemented.

```text
Environment observation
  -> minimized context feature
  -> context hypothesis
  -> SHADOW candidate
  -> explicit human confirmation
  -> existing Work Discovery / Admission
```

No current environment observation may create a TaskPool task, invoke a
model, send a message, log in to a site, access mail, modify a file, or make a
financial decision.

## Archaeological evidence

| Source | What it proves | What it does not prove |
| --- | --- | --- |
| `mine-seed/02_MEMORY/assets/cognition/CG-002-environmental-awareness.md` | The recovered principle `Perception -> ... -> Experience`, and `Perception` before `Action` | A permission to collect arbitrary desktop data or act automatically |
| `mine-seed/04_PROTOCOLS/environment_sensor.py` | A legacy repository/provider/external-source observer existed | Human-environment sensing, privacy controls, or safe production ownership |
| `mine-seed/04_PROTOCOLS/awareness_loop.py` | A historical Sensor -> Question -> Task -> model -> Experience loop existed | A safe automatic dispatcher; it crosses today's Candidate/Admission boundary |
| `mine-seed/04_PROTOCOLS/shadow.py` | A replay-gated shadow comparison pattern existed | A current ACE production route or automatic promotion right |
| `AGENTS.md` | Current production observation is RuntimeObserver, DiscoveryMode, provider health and stock-data health; legacy Sensor/Awareness files are not daemon consumers | A current desktop sensor integration |

## What is inherited

1. **Perception before action.**  Observation is input, not authority.
2. **Shadow before production.**  A context inference is a reversible,
   reviewable candidate, never a command.
3. **Lineage and expiry.**  Any future context feature must name its source,
   observation time, expiry, scope and retention decision.
4. **Failure is material.**  False context inferences become counterexamples;
   they are not silently retried into action.

## What is rejected

- Legacy loops that auto-dispatch Questions to a model.
- Periodic desktop surveillance, bulk screenshots, keystroke capture, full
  browser history, clipboard collection, mail access, or silent use of an
  authenticated browser session.
- Treating a tab title, app name, domain or model guess as user intent.
- Any route from environmental observation to Telegram, Advisor, Risk, finance
  recommendation, production TaskPool creation or file mutation.

## Minimum future contract

A future opt-in sensor may emit only a minimized record such as:

```json
{
  "contract_version": "ace.environment_context.v1",
  "scope": "PROJECT | APP | WINDOW | BROWSER_DOMAIN | CALENDAR",
  "feature": "project=ace_core",
  "observed_at": "ISO-8601",
  "expires_at": "ISO-8601",
  "source_ref": "local-sensor-id",
  "raw_retention": "NONE | SHORT_LIVED",
  "production_integration": false
}
```

The next layer may form an `INCONCLUSIVE` `SHADOW_CONTEXT_CANDIDATE`, with
source references and a human-readable reason.  Only an explicit user
confirmation can hand a real research question to existing Work Discovery;
existing Admission remains the only path into TaskPool.

## First implementation gate

Before code is added, a separate decision must select **one** opt-in scope.
The safest starting point is the current ACE project/workspace identity only.
It must have a local visible audit record, raw-data expiry, a test fixture and
no daemon consumer.  APP, WINDOW, browser-domain, calendar, chat, screen and
clipboard scopes remain independent future permissions, not implied grants.

### Gate outcome — 2026-08-27

The workspace-only gate is now implemented in
`core/environment_context.py`, with its regression boundary in
`ops/test_environment_context.py`.  The module is intentionally an injected,
zero-privilege contract rather than a collector: it does not scan the
workspace, inspect a desktop, call a provider, persist an observation, or wire
into the daemon.  A valid `PROJECT` feature can only become an `INCONCLUSIVE`
`SHADOW_CONTEXT_CANDIDATE`; explicit human confirmation remains required
before existing Work Discovery may receive a research question.
