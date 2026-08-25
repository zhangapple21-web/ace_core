# ACE 24H Runtime Mainline Design

## Goal

Create one production runtime chain that can start from `python ace.py daemon --serve`, run repeatedly, own and recover TaskPool work, execute governed daily learning, and continue discovery without production-side recommendation or notification effects.

## Scope

The runtime owner is `AceDaemon`. Legacy `Scheduler`, `TaskQueue`, `local_miner`, `MinerPool`, and protocol loops remain compatibility paths and must not become TaskPool consumers. The existing Discovery, TaskPool, task roles, governance, archive, experience deposition, daily learning, and stock-data reliability components are reused.

## Main Chain

```text
Boot
  -> ace.py daemon --serve
  -> AceDaemon startup recovery
  -> run_daemon
  -> run_once
  -> market/data health gate
  -> Discovery -> Observation -> TaskPool
  -> atomic claim -> worker -> validation
  -> KnowledgeGovernor / lifecycle for learning assets
  -> Guardian -> Archivist -> ExperienceDeposition
  -> DailyLearningLoop when higher-priority work is absent
  -> next interval
```

## Startup and Boot

`AceDaemon` must not import or instantiate legacy `Scheduler`. Any shared startup dependencies are initialized directly by the daemon. Windows scheduled tasks must use the explicit daemon CLI mode and have a long-running task configuration suitable for service-like execution. The one-shot entry remains an explicit test/run-once command and cannot be the boot target.

## Task Ownership and Durability

Task files receive durable lease metadata: `lease_owner`, `lease_expires_at`, `claim_id`, `fencing_token`, and optional `block_type`. A TaskPool lock protects create, claim, transition, lease renewal, failure, and stale-lease recovery operations. State transitions write a fully durable replacement before removing the old state representation, so interruption cannot make a task disappear. Only an unexpired claim holder can update a claimed task. Startup and every lifecycle iteration reclaim expired active leases.

Block types are `dependency_blocked`, `external_condition_blocked`, and `manual_gate_blocked`. Only dependency blocks can be automatically released after dependencies become terminally satisfied.

## Work, Failure, and Recovery

Task roles claim only through TaskPool. Worker exceptions always classify into retryable failure, credential/permission block, external-condition block, or permanent failure. Retryable failures use bounded attempts and backoff; terminal failures enter graveyard. Restart recovery preserves active leases until expiry, reclaims expired work, preserves blocked work according to block type, and resumes unfinished archive/deposition compensation.

## Daily Learning and Governance

`DailyLearningLoop` is assembled by `AceDaemon` and runs only when normal higher-priority work is not executable. Its daily checkpoint records the selected candidate, task id, registered evidence, governance decision, lifecycle stage, deposition state, and terminal outcome. Restart resumes from recorded facts rather than re-registering evidence or restarting the day.

For learning assets, `KnowledgeGovernor` is the only adoption authority. Validator and Guardian outputs stay part of generic task processing but cannot declare knowledge adoption. Governor results determine `adopt`, `observe`, or `reject` and drive lifecycle/archive behavior.

## Market and Data Health Gates

A local runtime market-data policy produces `MARKET_CLOSED`, `READY`, `DEGRADED`, `CONFLICT`, `STALE`, or `UNAVAILABLE`. Market/recommendation-tagged work is claimable only when the policy returns `READY`. Other runtime work, discovery, research, learning, and archaeology remain eligible outside trading periods. No live data collection, recommendation, or push operation is introduced.

## Routing and Side Paths

The daemon has one explicit role routing policy: strategic reasoning uses the 5.6 profile, execution uses the 5.4 profile, Free Zone exploration uses GLM/Ollama/NIM fallback, and FA is a quality gate. It must use the actual production callable already available to the runtime. Other model systems are compatibility-only and must not consume TaskPool work. Maintenance scripts delegate to the formal lifecycle or remain read-only; they cannot directly transition production tasks.

## Validation

All new tests use temporary directories and injected fixtures. They cover clean daemon import/start configuration, atomic two-consumer claim behavior, interrupted transition recovery, stale lease reclamation, external-condition blocks, worker retry/graveyard behavior, daily-learning interruption/resume, governance admission, discovery-to-archive, no-task-to-learning, and legacy regression scripts. No test enables AUTO_RUN/AUTO_PUSH, accesses real market data, recommends stock, sends Telegram, publishes, or commits.
