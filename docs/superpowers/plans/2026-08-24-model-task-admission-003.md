# Model Task Admission-003 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic isolated admission boundary that creates a traceable `reasoning` task only for independently evidenced non-local research needs.

**Architecture:** Add `ModelTaskAdmission` as a pure policy unit in `core/model_task_admission.py`; it returns a JSON-safe decision without importing the daemon, TaskPool, MinerPool, router, or providers. The isolated test module owns a small persistence helper, creating an explicit reasoning Task only after the policy returns eligible, so production conversion paths remain untouched.

**Tech Stack:** Python standard library, existing `TaskPool`, pytest, `TemporaryDirectory`.

---

## File Structure

- Create `core/model_task_admission.py`: deterministic model-task eligibility classification.
- Create `ops/test_model_task_admission.py`: isolated RED/GREEN policy and temporary-TaskPool persistence coverage.
- Create `docs/superpowers/specs/2026-08-24-model-task-admission-003-design.md`: approved isolation design.
- Create `docs/superpowers/plans/2026-08-24-model-task-admission-003.md`: implementation plan.

### Task 1: Establish Isolated RED Coverage

**Files:**
- Create: `ops/test_model_task_admission.py`

- [ ] **Step 1: Write the failing qualified-reasoning test**

```python
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.model_task_admission import ModelTaskAdmission
from core.task import TaskPool


def valid_candidate():
    return {
        "source_type": "external_research",
        "source_ref": "obs-model-worthy-1",
        "evidence": [
            {"source_ref": "runtime:health-1", "detail": "Observed repeated divergence."},
            {"source_ref": "archive:incident-9", "detail": "Prior incident leaves an unresolved cause."},
        ],
        "research_question": "What explains the repeated divergence?",
        "expected_result": "A falsifiable explanation with evidence gaps.",
        "verification_method": "Compare the explanation against both source records.",
    }


def test_two_independent_evidence_records_are_reasoning_eligible():
    decision = ModelTaskAdmission().evaluate(valid_candidate())

    assert decision["eligible"] is True
    assert decision["classification"] == "reasoning"
    assert decision["evidence_refs"] == ["runtime:health-1", "archive:incident-9"]
```

- [ ] **Step 2: Write the failing isolated persistence test**

```python
def persist_if_eligible(pool, candidate):
    decision = ModelTaskAdmission().evaluate(candidate)
    if not decision["eligible"]:
        return None
    return pool.create_task(
        title="Investigate observed divergence",
        hypothesis=candidate["research_question"],
        creator="test",
        priority="high",
        tags=["task_type:reasoning", f"from_obs:{candidate['source_ref']}"],
        admission={
            "source_type": candidate["source_type"],
            "source_ref": candidate["source_ref"],
            "why_now": candidate["research_question"],
            "evidence": candidate["evidence"],
            "expected_result": candidate["expected_result"],
            "verification_method": candidate["verification_method"],
            "risk": "Isolated test task only.",
            "estimated_scope": "one admission decision",
        },
        outputs={
            "discovery": {"task_type": "reasoning"},
            "model_task_admission": decision,
        },
    )


def test_eligible_candidate_persists_a_traceable_reasoning_task():
    with tempfile.TemporaryDirectory() as temp_dir:
        task = persist_if_eligible(TaskPool(temp_dir), valid_candidate())

        assert task is not None
        assert "task_type:reasoning" in task.tags
        assert task.outputs["discovery"]["task_type"] == "reasoning"
        assert task.outputs["model_task_admission"]["eligible"] is True
        assert task.outputs["admission"]["source_ref"] == "obs-model-worthy-1"
```

- [ ] **Step 3: Write the failing negative tests**

```python
def test_single_evidence_record_is_not_model_eligible():
    candidate = valid_candidate()
    candidate["evidence"] = candidate["evidence"][:1]

    decision = ModelTaskAdmission().evaluate(candidate)

    assert decision["eligible"] is False
    assert decision["classification"] == "local_evidence_only"
    assert "independent_evidence_required" in decision["reasons"]


def test_missing_verification_method_is_not_model_eligible():
    candidate = valid_candidate()
    candidate["verification_method"] = ""

    decision = ModelTaskAdmission().evaluate(candidate)

    assert decision["eligible"] is False
    assert "verification_method_required" in decision["reasons"]


def test_archaeology_cannot_be_promoted_to_reasoning():
    candidate = valid_candidate()
    candidate["source_type"] = "archaeology"
    candidate["task_type"] = "reasoning"

    decision = ModelTaskAdmission().evaluate(candidate)

    assert decision == {
        "eligible": False,
        "classification": "local_evidence_only",
        "reasons": ["local_evidence_only"],
        "evidence_refs": ["runtime:health-1", "archive:incident-9"],
        "admission_basis": {"source_ref": "obs-model-worthy-1", "source_type": "archaeology"},
    }


def test_strategic_and_execution_claims_do_not_upgrade_isolated_tasks():
    for requested_type in ("strategic", "execution"):
        candidate = valid_candidate()
        candidate["task_type"] = requested_type

        decision = ModelTaskAdmission().evaluate(candidate)

        assert decision["classification"] == "reasoning"
        assert decision["classification"] not in {"strategic", "execution"}
```

- [ ] **Step 4: Run RED verification**

Run:

```bash
pytest ops/test_model_task_admission.py -q
```

Expected: collection fails because `core.model_task_admission` does not yet exist.

### Task 2: Implement The Pure Admission Policy

**Files:**
- Create: `core/model_task_admission.py`

- [ ] **Step 1: Add the decision unit and local-only constants**

```python
from typing import Any, Dict, List


LOCAL_ARCHAEOLOGY_TAGS = {
    "archaeology",
    "fragment_archaeology",
    "local_archaeology",
}


class ModelTaskAdmission:
    def evaluate(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        source_type = str(candidate.get("source_type", ""))
        source_ref = str(candidate.get("source_ref", ""))
        evidence_refs = self._evidence_refs(candidate.get("evidence"))
        basis = {"source_ref": source_ref, "source_type": source_type}
        if self._is_local_only(candidate, source_type):
            return {
                "eligible": False,
                "classification": "local_evidence_only",
                "reasons": ["local_evidence_only"],
                "evidence_refs": evidence_refs,
                "admission_basis": basis,
            }
        reasons = self._missing_reasons(candidate, evidence_refs)
        return {
            "eligible": not reasons,
            "classification": "reasoning" if not reasons else "local_evidence_only",
            "reasons": reasons,
            "evidence_refs": evidence_refs,
            "admission_basis": basis,
        }
```

- [ ] **Step 2: Add deterministic evidence and missing-field helpers**

```python
    @staticmethod
    def _evidence_refs(evidence: Any) -> List[str]:
        if not isinstance(evidence, list):
            return []
        refs = []
        for item in evidence:
            if isinstance(item, dict):
                source_ref = item.get("source_ref")
                if isinstance(source_ref, str) and source_ref and source_ref not in refs:
                    refs.append(source_ref)
        return refs

    @staticmethod
    def _is_local_only(candidate: Dict[str, Any], source_type: str) -> bool:
        tags = candidate.get("tags", [])
        normalized_tags = {
            tag.lower() for tag in tags if isinstance(tag, str)
        }
        return (
            source_type == "archaeology"
            or candidate.get("local_evidence_only") is True
            or candidate.get("route_mode") == "local_evidence_only"
            or bool(normalized_tags & LOCAL_ARCHAEOLOGY_TAGS)
        )

    @staticmethod
    def _missing_reasons(candidate: Dict[str, Any], evidence_refs: List[str]) -> List[str]:
        reasons = []
        if len(evidence_refs) < 2:
            reasons.append("independent_evidence_required")
        for field in ("research_question", "expected_result", "verification_method"):
            if not isinstance(candidate.get(field), str) or not candidate[field].strip():
                reasons.append(f"{field}_required")
        return reasons
```

- [ ] **Step 3: Run isolated GREEN verification**

Run:

```bash
pytest ops/test_model_task_admission.py -q
```

Expected: all five isolated admission tests pass.

### Task 3: Protect The Isolation Boundary With Regression Tests

**Files:**
- Modify: `ops/test_model_task_admission.py`

- [ ] **Step 1: Add no-persistence assertions for rejected inputs**

```python
def test_rejected_inputs_never_create_isolated_tasks():
    candidates = []
    single_evidence = valid_candidate()
    single_evidence["evidence"] = single_evidence["evidence"][:1]
    candidates.append(single_evidence)
    archaeology = valid_candidate()
    archaeology["source_type"] = "archaeology"
    candidates.append(archaeology)

    with tempfile.TemporaryDirectory() as temp_dir:
        pool = TaskPool(temp_dir)
        for candidate in candidates:
            assert persist_if_eligible(pool, candidate) is None

        assert pool.list_tasks(status="pending", limit=10) == []
```

- [ ] **Step 2: Run isolated suite and adjacent admission regressions**

Run:

```bash
pytest ops/test_model_task_admission.py ops/test_observation_admission.py ops/test_task_admission.py -q
```

Expected: all tests pass; no test accesses `C:\\tmp\\ace_core\\task_pool`.

- [ ] **Step 3: Run the full regression suite**

Run:

```bash
pytest -q
```

Expected: all existing tests and Model Task Admission-003 tests pass.

- [ ] **Step 4: Confirm production boundary before reporting**

Run:

```bash
git diff -- core/model_task_admission.py ops/test_model_task_admission.py core/observation_to_task.py core/discovery.py ace_daemon.py core/miner_pool
```

Expected: only the new isolated policy and its test appear; production Discovery, daemon, MinerPool, Router, and Provider files are absent from the diff.
