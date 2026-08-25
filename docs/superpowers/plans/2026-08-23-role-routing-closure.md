# Role Routing Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing shared MinerPool enforce native strategic, execution, free_exploration, and reasoning routing semantics while recording FA as a post-model quality gate.

**Architecture:** Keep AceDaemon's single MinerPool and its existing ModelRouter. Add native task profiles and a small policy lookup in task_roles so task_type reaches MinerPool unchanged; unavailable strategic and execution target models are explicitly blocked and traced rather than silently remapped. FA is represented as a quality-gate result derived only from successful model output, not as a separate worker or provider call.

**Tech Stack:** Python, pytest, existing core.miner_pool MinerPool/ModelRouter/TASK_PROFILES, TaskPool task persistence.

---

### Task 1: Define role-routing policy and its tests

**Files:**
- Modify: `C:\tmp\ace_core\ops\test_model_pool_mainline.py`
- Modify: `C:\tmp\ace_core\core\miner_pool\task_profiles.py`

- [ ] **Step 1: Write failing profile-boundary tests**

```python
def test_role_profiles_preserve_native_task_types_and_boundaries():
    assert get_task_profile("strategic")["expected_model"] == "gpt-5.6-terra"
    assert get_task_profile("execution")["expected_model"] == "gpt-5.4"
    assert get_task_profile("free_exploration")["allowed_providers"] == {"glm", "nim", "ollama"}
    assert "gpt-5.6-terra" not in get_task_profile("free_exploration")["preferred_models"]
    assert "gpt-5.4" not in get_task_profile("free_exploration")["preferred_models"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
python -m pytest ops/test_model_pool_mainline.py -q
```

Expected: FAIL because the native role profiles and policy fields do not exist.

- [ ] **Step 3: Add only registry-backed role profiles**

Add `strategic`, `execution`, and `free_exploration` entries to `TASK_PROFILES`. The strategic and execution profiles must include their expected target aliases but set `enabled` false when no validated provider/model registry entry exists. The Free Zone profile must list only existing GLM and NIM model IDs and an explicit `allowed_providers` set; do not introduce a provider endpoint, credential, or unregistered model ID.

```python
"strategic": {
    "expected_model": "gpt-5.6-terra",
    "enabled": False,
    "blocked_reason": "expected_model_unavailable",
    "preferred_models": [],
    "fallback_models": [],
},
```

- [ ] **Step 4: Run the test to verify it passes**

Run:

```powershell
python -m pytest ops/test_model_pool_mainline.py -q
```

Expected: PASS for profile assertions.

### Task 2: Preserve task semantics and persist role-safe call traces

**Files:**
- Modify: `C:\tmp\ace_core\ops\test_model_pool_mainline.py`
- Modify: `C:\tmp\ace_core\core\task_roles.py:25-115`

- [ ] **Step 1: Write failing lifecycle tests for native role routing**

```python
def test_strategic_is_not_remapped_to_reasoning_when_target_unavailable():
    trace = _run_task_with_type("strategic")
    assert trace["task_type"] == "strategic"
    assert trace["profile"] == "strategic"
    assert trace["api_called"] is False
    assert trace["result"] == "expected_model_unavailable"


def test_execution_never_routes_to_strategic_model():
    trace = _run_task_with_type("execution")
    assert trace["task_type"] == "execution"
    assert trace["expected_model"] == "gpt-5.4"
    assert trace["selected_model"] == ""


def test_free_exploration_uses_only_free_zone_models():
    fake = FakeMinerPool()
    trace = _run_task_with_type("free_exploration", fake)
    assert fake.calls[0]["task_type"] == "free_exploration"
    assert trace["profile"] == "free_exploration"
    assert trace["provider"] in {"glm", "nim", "ollama"}
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
python -m pytest ops/test_model_pool_mainline.py -q
```

Expected: FAIL because `_record_model_execution()` rewrites strategic to `reasoning`, excludes execution/free_exploration, and lacks the new trace fields.

- [ ] **Step 3: Implement a policy lookup and enrich the trace**

Replace `MODEL_TASK_TYPES` with native role eligibility based on `get_task_profile(task_type)`. Pass the original `task_type` to `llm_router.chat()`. For disabled strategic/execution profiles, append a non-API trace with `result="expected_model_unavailable"`. For calls, append the required fields:

```python
{
    "task_id": task.task_id,
    "task_type": task_type,
    "role": role,
    "profile": task_type,
    "expected_model": profile["expected_model"],
    "selected_model": response.get("model", ""),
    "provider": response.get("provider", ""),
    "fallback_chain": response.get("tried_models", []),
    "api_called": bool(response.get("api_called", response.get("success"))),
    "result": "success" if response.get("success") else "failed",
    "quality_gate": {},
}
```

Reject a successful response if its provider is outside `allowed_providers`; record `result="role_boundary_violation"` and do not accept it as executable evidence.

- [ ] **Step 4: Run the test to verify it passes**

Run:

```powershell
python -m pytest ops/test_model_pool_mainline.py -q
```

Expected: PASS with no `strategic -> reasoning` compatibility mapping.

### Task 3: Add an FA quality gate without a new worker or provider request

**Files:**
- Modify: `C:\tmp\ace_core\ops\test_model_pool_mainline.py`
- Modify: `C:\tmp\ace_core\core\task_roles.py:64-115`

- [ ] **Step 1: Write failing FA tests**

```python
def test_fa_does_not_execute_without_a_successful_model_result():
    trace = _run_task_with_type("strategic")
    assert trace["quality_gate"]["status"] == "not_run"
    assert trace["quality_gate"]["executed"] is False


def test_fa_records_pass_revise_or_reject_after_model_result():
    trace = _run_task_with_type("free_exploration", FakeMinerPool())
    assert trace["quality_gate"]["executed"] is True
    assert trace["quality_gate"]["status"] in {"pass", "revise", "reject"}
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
python -m pytest ops/test_model_pool_mainline.py -q
```

Expected: FAIL because quality-gate state is absent.

- [ ] **Step 3: Implement deterministic task-level FA gate state**

After a response is returned, compute only task-level gate state. A missing, failed, boundary-violating, or contentless response must record:

```python
{"executed": False, "status": "not_run", "reason": "no_successful_model_result"}
```

A successful, allowed response must record one of `pass`, `revise`, or `reject`, with `executed=True`. Do not make a second model call and do not instantiate a new worker.

- [ ] **Step 4: Run the test to verify it passes**

Run:

```powershell
python -m pytest ops/test_model_pool_mainline.py -q
```

Expected: PASS for FA execution accounting.

### Task 4: Verify role-safe behavior and controlled production evidence

**Files:**
- Modify: `C:\tmp\ace_core\ops\test_model_pool_mainline.py`
- Inspect: `C:\tmp\ace_core\core\task_roles.py`
- Inspect: `C:\tmp\ace_core\core\miner_pool\miner_pool.py`
- Inspect: `C:\tmp\ace_core\ace_daemon.py`

- [ ] **Step 1: Add fallback boundary tests**

```python
def test_fallback_chain_never_crosses_role_boundary():
    trace = _run_task_with_type("free_exploration", FakeMinerPool())
    assert all(
        model.split(":", 1)[0] in {"glm", "nim", "ollama"}
        for model in trace["fallback_chain"]
    )
```

- [ ] **Step 2: Run focused and regression tests**

Run:

```powershell
python -m pytest ops/test_model_pool_mainline.py ops/test_24h_runtime_mainline.py ops/test_production_admission_sources.py ops/test_observation_admission.py -q
python -m compileall core ace_daemon.py
python -m pytest ops/test_model_pool_mainline.py -q
```

Expected: all tests pass and compilation succeeds.

- [ ] **Step 3: Perform exactly three controlled non-stock calls**

Run one controlled task each with `task_type` `strategic`, `execution`, and `free_exploration`. Do not enable `AUTO_RUN` or `AUTO_PUSH`, send Telegram, run stock recommendations, alter providers, or commit. Store traces in task persistence and verify their `task_type`, profile, expected/selected models, provider, fallback chain, API state, result, and quality-gate state.

Expected:

```text
strategic: expected_model_unavailable unless a validated Terra mapping is present
execution: expected_model_unavailable unless a validated 5.4 mapping is present
free_exploration: allowed GLM/NIM/Ollama provider result, or explicit failure trace
```

- [ ] **Step 4: Reverse-audit the completed path**

Run:

```powershell
rg -n "MinerPool\(|pool_task_type = \"reasoning\"|\.chat\(" ace_daemon.py core ops
```

Expected: one daemon-owned MinerPool construction, no strategic compatibility remap, no direct worker provider bypass, and no Free Zone profile containing strategic/execution target aliases.
