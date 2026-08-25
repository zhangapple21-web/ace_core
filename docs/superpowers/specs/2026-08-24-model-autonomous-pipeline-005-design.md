# Model Autonomous Pipeline-005 Design

## Goal

Wire the existing `ModelTaskAdmission` policy into the production Discovery-to-Task path so ACE creates a `reasoning` task only for an evidence-qualified, non-local cognitive need. The task may then use the existing Researcher, MinerPool, Router, and Provider chain. This phase does not force any model selection and does not create demand to activate a model pool.

## Scope

The production path becomes:

```text
Discovery
-> Observation
-> ModelTaskAdmission
-> reasoning Task
-> Researcher
-> MinerPool
-> Router
-> actual Provider/Model
-> outputs.model_execution
```

This phase permits only `reasoning` tasks. It preserves the current model profiles and uses the actual Router selection as an execution observation.

The phase does not change TaskPool state transitions, Researcher throughput, fairness, Validator behavior, Data Health, FinanceDataGateway, ModelRouter, providers, Shenwen credentials, task profiles, AUTO_PUSH, Telegram, or any stock recommendation behavior.

## Production Admission Contract

`ModelTaskAdmission` is the sole model-eligibility decision for Discovery-derived candidates. The converter constructs an admission candidate from the Discovery Observation and passes it to `ModelTaskAdmission.evaluate()`.

An eligible model candidate requires all of:

- a source type other than `archaeology`;
- no explicit `local_evidence_only` marker;
- at least two distinct, non-empty, traceable evidence `source_ref` values;
- a non-empty research question or cognition gap;
- a non-empty expected result;
- a non-empty verification method;
- a complete Task admission record.

A rejected candidate creates no model task. Its decision is recorded in the converter and daemon-cycle metrics with stable rejection reasons. When no candidate is eligible in a cycle, the cycle records `NO_VALID_MODEL_TASK_TARGET`.

`strategic` and `execution` remain schema values only. Discovery cannot create either value in this phase. A candidate that requests either is rejected; it is not renamed or downgraded to `reasoning`.

## Local-Only Protection

Archaeology and explicit local-only candidates cannot cross the model boundary, even when they contain otherwise valid evidence. They remain local-only under existing handling or are counted as rejected model candidates.

Discovery route metadata is not a model-eligibility signal. In particular, `route_mode == "local_evidence_only"` is retained as observation metadata but is removed from `ModelTaskAdmission` and task-role local-only classification. The final model decision remains at the existing Task -> MinerPool -> Router boundary.

## Task Trace Contract

For every created reasoning task, the converter persists:

- `task_type:reasoning` in tags;
- `outputs.discovery.task_type == "reasoning"`;
- `outputs.model_task_admission`, including the decision, source reference, and evidence references;
- the source Observation ID and existing Discovery contract;
- the complete validated Task admission.

Only trace entries from a task with a persisted eligible reasoning decision count as `production_task_call`. Existing health probes and controlled model probes are excluded.

A task trace is complete when it contains the persisted source Observation, admission decision, reasoning task type, and a `model_execution` item that records provider, selected model, API result, attempted models, and fallback state.

## Cycle Metrics

Each daemon cycle records a stable model-pipeline summary:

```text
candidate_count
eligible_count
created_count
rejected_count
rejection_reasons
reasoning_tasks_created
model_tasks_claimed
miner_pool_reached
production_task_calls
shenwen_5_6_calls
shenwen_5_4_calls
api_success
api_failure
fallback
task_trace_complete
```

Metrics are derived from Observation decisions, created Task IDs, and persisted `outputs.model_execution` traces. They do not query or modify Router, Provider, or MinerPool state. `shenwen_5_6_calls` and `shenwen_5_4_calls` are observational counters, not pass conditions.

## Execution and Acceptance

The task execution path remains unchanged after reasoning task creation. A task may call any model selected by the existing Router and profile. This phase does not require `reasoning` to select `gpt-5.6-terra` and does not manufacture `execution` work for `gpt-5.4-mini`.

Before runtime observation, tests must cover:

- qualified Discovery Observation creates a traceable `reasoning` task;
- insufficient evidence, missing required fields, archaeology, and explicit local-only candidates create no model task;
- requested `strategic` and `execution` candidates are rejected rather than relabeled;
- Discovery route metadata cannot suppress otherwise eligible reasoning admission;
- only persisted eligible reasoning task traces count as `production_task_call`;
- empty cycles return `NO_VALID_MODEL_TASK_TARGET` with zero stable metrics.

After regression and code freeze, exactly one ACE daemon process is restarted and its new PID and loaded code are confirmed. Five complete daemon cycles are then observed without artificial task creation or fixed model calls.

A five-cycle window with no qualified cognitive need ends as `MODEL_PIPELINE_IDLE_BY_DESIGN`. A window with an autonomous qualified task and a complete successful production trace establishes `MODEL_POOL_PRODUCTION_ACTIVE`.
