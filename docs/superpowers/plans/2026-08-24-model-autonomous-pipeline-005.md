# Model Autonomous Pipeline-005 Implementation Plan

**Goal:** Wire `ModelTaskAdmission` into the production Discovery-to-Task path so only evidence-qualified, non-local `reasoning` candidates can reach the existing Researcher and MinerPool execution path.

**Architecture:** Preserve Discovery routing as observational metadata. The converter is the sole production caller of `ModelTaskAdmission`; it constructs a provenance-preserving candidate from a Discovery Observation, rejects all non-reasoning requests and policy failures without creating a task, and persists eligible decisions on the created task. Daemon metrics classify production calls only from persisted eligible reasoning tasks and their existing execution traces.

**Tech Stack:** Python 3.11, existing `TaskPool`, `RuntimeObserver`, `Researcher`, `MinerPool`, `pytest`.

**Boundaries:** Do not modify task profiles, `ModelRouter`, providers, credentials, MinerPool behavior, task lifecycle transitions, financial data behavior, notifications, or stock recommendation behavior. Do not create synthetic candidates, periodic model tasks, or `strategic` / `execution` tasks.

## Evidence Contract

A Discovery candidate can become a model task only when its existing `autonomous_maintenance.evidence` contains at least two distinct non-empty `source_ref` values. The implementation must preserve references supplied by candidate producers; it must not derive, duplicate, or invent references to satisfy admission.

Current stock discovery candidates provide operational observations but no independently traceable source references. They remain observed and are recorded as `NO_VALID_MODEL_TASK_TARGET` until their producer naturally supplies qualified provenance. The daily-learning path already accepts real multi-source evidence items and can preserve their source locations as `source_ref` values.

## Task 1: Establish RED Coverage

**Files:**
- Modify: `ops/test_model_task_admission.py`
- Modify: `ops/test_observation_admission.py`
- Modify: `ops/test_model_pool_mainline.py`
- Modify: `ops/test_24h_runtime_mainline.py`

- [ ] Add policy regression coverage proving that Discovery `route_mode="local_evidence_only"` alone does not reject a otherwise-qualified candidate, while explicit local-only and archaeology inputs remain rejected.
- [ ] Replace the converter fixture evidence with two independent `source_ref` records and assert that a created task has `task_type:reasoning`, the original TaskPool admission, source Observation ID, and `outputs.model_task_admission`.
- [ ] Add converter rejection cases for one source, missing cognitive fields, archaeology, explicit local-only, and `strategic` / `execution`; assert no task is created, no candidate is silently relabeled, and stable rejection details are returned.
- [ ] Add role-path coverage proving Discovery route metadata alone no longer blocks the fake MinerPool, while archaeology or an explicit persisted local-only admission remains blocked.
- [ ] Add daemon metrics coverage for an empty conversion cycle and trace classification: health probes and non-admitted traces must not count as `production_task_call`; an eligible persisted reasoning task trace must count.

Run:

```powershell
pytest ops/test_model_task_admission.py ops/test_observation_admission.py ops/test_model_pool_mainline.py ops/test_24h_runtime_mainline.py -q
```

Expected before implementation: route and converter/metrics expectations fail.

## Task 2: Correct Local-Only Semantics

**Files:**
- Modify: `core/model_task_admission.py`
- Modify: `core/task_roles.py`

- [ ] Remove Discovery `route_mode` from `_is_local_only()` in `ModelTaskAdmission`.
- [ ] Remove Discovery `route.mode` from `_is_local_only_task()`.
- [ ] Retain archaeology tags/source types and explicit local-only protection. At role execution, use the persisted `outputs.model_task_admission` decision as an additional safety guard when it explicitly classifies the task local-only.

Run:

```powershell
pytest ops/test_model_task_admission.py ops/test_model_pool_mainline.py -q
```

Expected: eligible route-only task may reach the existing MinerPool; genuine local-only tasks cannot.

## Task 3: Preserve Genuine Discovery Provenance

**Files:**
- Modify: `core/discovery.py`
- Modify: `core/daily_learning.py`

- [ ] Change default Discovery metadata construction so it preserves valid producer-provided evidence rather than overwriting it.
- [ ] Do not make default one-source candidates eligible. Its fallback evidence remains a single observation record and lacks fabricated `source_ref` values.
- [ ] In daily learning, normalize existing evidence records into Discovery evidence entries only when each has a genuine traceable reference, preferring existing `source_ref` and otherwise using the actual `source_location` without duplication.
- [ ] Preserve all existing evidence content and learning contracts.

Run:

```powershell
pytest ops/test_discovery_mode.py ops/test_daily_autonomous_learning.py ops/test_observation_admission.py -q
```

Expected: qualified multi-source producer data is retained; unqualified ordinary Discovery data remains observation-only.

## Task 4: Make Converter Admission the Sole Production Gate

**Files:**
- Modify: `core/observation_to_task.py`

- [ ] Construct a model-admission candidate from the Observation ID, source type, explicit local-only marker, evidence, research question/objective, expected result, verification method, and tags.
- [ ] Reject a requested task type other than `reasoning` with a stable reason before TaskPool creation.
- [ ] Call `ModelTaskAdmission.evaluate()` exactly once for a valid Discovery conversion attempt.
- [ ] On a rejected decision, return a converter detail with `NO_VALID_MODEL_TASK_TARGET`, decision details, and stable rejection reasons; do not mark the Observation consumed and do not create a TaskPool task.
- [ ] On an eligible decision, create the existing TaskPool task with unmodified baseline admission and persist `outputs.model_task_admission`.
- [ ] Extend converter results with stable aggregate fields: `candidate_count`, `eligible_count`, `created_count`, `rejected_count`, `rejection_reasons`, and `reasoning_tasks_created`.

Run:

```powershell
pytest ops/test_observation_admission.py ops/test_discovery_mode.py ops/test_model_task_admission.py -q
```

Expected: only persisted eligible reasoning decisions can create Discovery tasks.

## Task 5: Add Read-Only Daemon Metrics

**Files:**
- Modify: `ace_daemon.py`
- Modify: `ops/test_24h_runtime_mainline.py`

- [ ] Add a pure daemon helper that derives a model-pipeline summary from converter output and persisted task data. It must not call or mutate Router, Provider, or MinerPool.
- [ ] Count `production_task_calls` only for model-execution traces whose task has an eligible persisted `model_task_admission` and a reasoning task type.
- [ ] Derive call/provider/model/API/fallback/trace-completeness counters from those traces only; separately preserve existing health-probe reporting.
- [ ] Persist the summary under the existing cycle-progress/state flow and expose it through daemon status.
- [ ] For a cycle with no qualified candidate, record zero counters and `NO_VALID_MODEL_TASK_TARGET`.

Run:

```powershell
pytest ops/test_24h_runtime_mainline.py ops/test_model_pool_mainline.py -q
```

Expected: metrics are observational, state-persisted, and cannot inflate from probes or arbitrary task traces.

## Task 6: Full Regression and Controlled Observation

**Files:**
- Verify all modified source and test files.

- [ ] Run the focused suites from Tasks 1-5.
- [ ] Run the repository's full pytest suite and address only regressions introduced by this work.
- [ ] Run available lint/typecheck commands declared by repository configuration.
- [ ] Freeze the code after clean regression.
- [ ] Restart exactly one ACE daemon process, record the new PID and confirm the loaded workspace path/version from runtime state.
- [ ] Observe five complete daemon cycles without creating artificial candidates or model calls.
- [ ] Report `MODEL_PIPELINE_IDLE_BY_DESIGN` when all cycles have no qualified demand, or `MODEL_POOL_PRODUCTION_ACTIVE` only when a persisted eligible reasoning task reaches a real provider and has a complete execution trace.
