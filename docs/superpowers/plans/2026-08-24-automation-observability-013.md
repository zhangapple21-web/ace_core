# AUM-MISSION-AUTOMATION-OBSERVABILITY-013 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Provide a read-only daily ACE production audit command that writes health, blocking, and trend reports without changing runtime behavior.

**Architecture:** A standalone `ops/autonomous_audit.py` parses only persisted JSON/JSONL evidence supplied through explicit paths. `ops/run_autonomous_audit.py` invokes it and writes the four current reports plus date-keyed historical JSON snapshots. The tool never imports `AceDaemon`, `TaskPool`, Router, Provider, MinerPool, notifier, or scheduling code.

**Tech Stack:** Python 3.11 standard library, pytest, JSON, pathlib.

---

### Task 1: Define read-only collector contracts

**Files:**
- Create: `ops/autonomous_audit.py`
- Create: `ops/test_autonomous_audit.py`

- [ ] **Step 1: Write failing tests for task and model evidence classification**

```python
def test_production_trace_requires_admitted_reasoning_task(tmp_path):
    audit = AutonomousAudit(paths_for(tmp_path))
    report = audit.collect()
    assert report["model_calls"]["PRODUCTION_TASK_CALL"]["count"] == 1
    assert report["model_calls"]["HEALTH_PROBE"]["count"] == 1
    assert report["model_calls"]["CONTROLLED_PROBE"]["count"] == 1
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest ops/test_autonomous_audit.py::test_production_trace_requires_admitted_reasoning_task -q`
Expected: FAIL because `AutonomousAudit` does not exist.

- [ ] **Step 3: Implement pure JSON readers and task aggregation**

```python
class AutonomousAudit:
    def __init__(self, paths):
        self.paths = paths

    def collect(self):
        tasks = self._load_task_records()
        return {"task_lifecycle": self._summarize_tasks(tasks), "model_calls": self._summarize_model_calls(tasks)}
```

- [ ] **Step 4: Run the targeted test to verify it passes**

Run: `pytest ops/test_autonomous_audit.py::test_production_trace_requires_admitted_reasoning_task -q`
Expected: PASS.

### Task 2: Add readiness, blocking, fairness, and trend calculations

**Files:**
- Modify: `ops/autonomous_audit.py`
- Modify: `ops/test_autonomous_audit.py`

- [ ] **Step 1: Write failing tests for missing evidence, starvation, and trend deltas**

```python
def test_missing_state_is_not_ready_and_backlog_growth_is_anomaly(tmp_path):
    audit = AutonomousAudit(paths_for(tmp_path))
    report = audit.collect()
    assert report["domains"]["runtime"]["state"] == "NOT_READY"
    assert "backlog_increasing" in report["trend"]["anomalies"]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest ops/test_autonomous_audit.py::test_missing_state_is_not_ready_and_backlog_growth_is_anomaly -q`
Expected: FAIL because readiness and trend reports do not exist.

- [ ] **Step 3: Implement deterministic domain states and one advisory action**

```python
def _overall_state(domains):
    states = {entry["state"] for entry in domains.values()}
    return "BLOCKED" if "BLOCKED" in states else "NOT_READY" if "NOT_READY" in states else "READY"
```

- [ ] **Step 4: Run the targeted test to verify it passes**

Run: `pytest ops/test_autonomous_audit.py::test_missing_state_is_not_ready_and_backlog_growth_is_anomaly -q`
Expected: PASS.

### Task 3: Add report writing and command entry point

**Files:**
- Modify: `ops/autonomous_audit.py`
- Create: `ops/run_autonomous_audit.py`
- Modify: `ops/test_autonomous_audit.py`

- [ ] **Step 1: Write failing report-output and read-only invariant tests**

```python
def test_run_writes_only_audit_outputs_and_retains_ninety_days(tmp_path):
    before = source_hashes(tmp_path)
    result = run_audit(paths_for(tmp_path))
    assert result["written"] == {"daily_health.json", "daily_health.md", "blocking_reasons.json", "trend_report.json"}
    assert source_hashes(tmp_path) == before
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest ops/test_autonomous_audit.py::test_run_writes_only_audit_outputs_and_retains_ninety_days -q`
Expected: FAIL because report writer and command entry point do not exist.

- [ ] **Step 3: Write fixed reports, dated JSON history, and retention cleanup scoped to history**

```python
def run_audit(paths=None):
    audit = AutonomousAudit(paths or default_paths())
    report = audit.collect()
    return audit.write_reports(report)
```

- [ ] **Step 4: Run the targeted test to verify it passes**

Run: `pytest ops/test_autonomous_audit.py::test_run_writes_only_audit_outputs_and_retains_ninety_days -q`
Expected: PASS.

### Task 4: Verify against production evidence without runtime mutation

**Files:**
- Modify: `ops/test_autonomous_audit.py`

- [ ] **Step 1: Run the full dedicated suite**

Run: `pytest ops/test_autonomous_audit.py -q`
Expected: PASS.

- [ ] **Step 2: Run the audit command once**

Run: `python ops/run_autonomous_audit.py`
Expected: exit code 0 and all four reports below `06_RUNTIME/ace/data/audits/`.

- [ ] **Step 3: Inspect the generated JSON reports**

Run: `python -c "import json; from pathlib import Path; p=Path('06_RUNTIME/ace/data/audits/daily_health.json'); print(json.loads(p.read_text(encoding='utf-8'))['overall_state'])"`
Expected: a state derived from current evidence; no Provider or daemon invocation.

- [ ] **Step 4: Run full regression**

Run: `pytest -q`
Expected: PASS.

- [ ] **Step 5: Create the daily silent audit automation only after all checks pass**

Create one daily 09:00 automation that runs `python ops/run_autonomous_audit.py` and silently persists reports to `06_RUNTIME/ace/data/audits/` without operating the daemon, TaskPool, Provider, or Telegram.
