# ACE Sandbox Society v1

ACE needs both a place that can fail freely and a reality that remains
trustworthy. The architecture is not a hierarchy of stronger prompts; it is a
set of separate jurisdictions with narrow crossings.

```text
                 PUBLIC INTERNET / LOCAL DRAWERS
                              |
                              v
                  [ Free Zone: experiment records ]
                    /             |              \
             clean evidence     failure       contamination
                  |                |              |
                  v                v              v
            [ Curator ]      experiments     [ Quarantine ]
                  |
                  v
          PROPOSAL_ONLY distillation
                  |
                  v
             [ Court / audit ] ---- invalid --> quarantine / reject
                  |
                  v
           [ Teacher review queue ]
                  |
       human confirmation + existing Admission + Validator
                  |
                  v
       ACE reality: TaskPool / Runtime / Data / Advisor / Delivery
```

## Jurisdictions

| Jurisdiction | Purpose | May change | Cannot change |
|---|---|---|---|
| Free Zone | speculation, counterexamples, failed probes | sandbox experiment records | production files or credentials |
| Curator | retain provenance and compress clean patterns | proposal-only records | production candidates or tasks |
| Court | integrity and source-chain checks | audit reports | evidence, outcome, approval |
| Teacher | prioritise what deserves human attention | manual decision outside sandbox | automatic approval or delivery |
| Reality | governed operational work | existing ACE lifecycle | sandbox evidence without admission |

## Living rhythm

* **Daily free-research shift** may add at most one traceable experiment.
* **Hourly curator/court turn** is deterministic and idempotent. It has no
  model call or external fetch; without new material it records
  `NO_NEW_SANDBOX_WORK`.
* **Reality** retains its existing daemon, evidence thresholds, admission and
  review boundaries. It does not consume a sandbox proposal automatically.

## Anti-patterns

* a second daemon posing as a sandbox;
* free-zone thoughts recorded as current market facts;
* a teacher queue that automatically becomes a recommendation;
* repeated model calls merely because a role is idle;
* deleting failures instead of retaining them as falsification evidence.
