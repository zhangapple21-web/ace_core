# Daily Autonomous Learning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect ACE's existing discovery, task, evidence, governance, lifecycle, and archive components into an internal-first daily autonomous learning loop.

**Architecture:** Add a narrow `DailyLearningLoop` coordinator. It creates normal Discovery observations and normal TaskPool tasks, registers evidence in the existing registry, independently evaluates source origins, reuses triple cross validation and KnowledgeGovernor, then records adoption, observation, rejection, lifecycle, and archive outcomes without calling production recommendation or notification systems.

**Tech Stack:** Python standard library; existing `core` discovery, task, governance, lifecycle, and deposition modules.

---

## File Structure

- Modify `core/discovery.py`: add optional candidate metadata and preserve it in Observation metadata.
- Modify `core/observation_to_task.py`: require complete learning contract before conversion and tag learning tasks.
- Create `core/daily_learning.py`: narrow coordinator, internal-first candidate selection, source metadata/independence logic, registry/governance/lifecycle integration, daily result persistence.
- Create `ops/test_daily_autonomous_learning.py`: isolated Day 1-4 and no-target simulation.

### Task 1: Learning Contract Through Existing Discovery Path

**Files:**
- Modify: `core/discovery.py:10-36`
- Modify: `core/observation_to_task.py:141-153,306-332`
- Test: `ops/test_daily_autonomous_learning.py`

- [ ] **Step 1: Write the failing contract test**

```python
incomplete = DiscoveryCandidate(..., metadata={"learning": {"why_learn": "gap"}})
assert converter.convert()["tasks_created"] == 0
complete = DiscoveryCandidate(..., metadata={"learning": CONTRACT})
assert converter.convert()["tasks_created"] == 1
```

- [ ] **Step 2: Run the isolated test and verify it fails**

Run: `python ops/test_daily_autonomous_learning.py`
Expected: failure because `DiscoveryCandidate` has no metadata and the converter does not validate learning contracts.

- [ ] **Step 3: Extend the existing candidate metadata without creating a second candidate type**

```python
@dataclass(frozen=True)
class DiscoveryCandidate:
    ...
    metadata: Optional[Dict[str, Any]] = None

    def to_metadata(self, route):
        metadata = {...existing fields...}
        metadata.update(self.metadata or {})
        return metadata
```

Define `_valid_learning_contract()` in `observation_to_task.py`; require non-empty `why_learn`, `learning_objective`, `required_evidence`, and `mastery_criteria` if `discovery["learning"]` exists. Copy the contract to `task.outputs["learning"]` and add `learning` tag.

- [ ] **Step 4: Run the test and verify the contract gate passes**

Run: `python ops/test_daily_autonomous_learning.py`
Expected: contract gate checks pass before later lifecycle assertions.

### Task 2: Daily Learning Coordinator and Source Integrity Gate

**Files:**
- Create: `core/daily_learning.py`
- Test: `ops/test_daily_autonomous_learning.py`

- [ ] **Step 1: Write failing Day 1 and Day 4 tests**

```python
assert day1["mode"] == "internal"
assert day1["outcome"] == "adopt"
assert day4["outcome"] in {"observe", "reject"}
assert day4["source_independence"]["independent_count"] == 1
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `python ops/test_daily_autonomous_learning.py`
Expected: import error for `DailyLearningLoop`.

- [ ] **Step 3: Implement the narrow coordinator**

Implement `DailyLearningLoop` with constructor-injected `TaskPool`, `RuntimeObserver`, `ObservationToTaskConverter`, `EvidenceRegistry`, `Governor`, `LifecycleManager`, `ExperienceDeposition`, `Archivist`, `internal_candidate_sources`, and optional `external_discoverer`.

Implement:

```python
def run(self, run_date: str) -> dict: ...
def _choose_candidate(self) -> tuple[str, Optional[DiscoveryCandidate]]: ...
def _register_evidence(self, items: list[dict]) -> list[str]: ...
def _source_independence(self, items: list[dict]) -> dict: ...
def _record_daily_result(self, run_date: str, result: dict) -> None: ...
```

Internal candidate sources run first. Invoke external discovery only when no internal candidate remains. Reject `repost` and `search_result` items from independent-source counting. Deduplicate `independence_group` values. Persist all evidence metadata to the existing `EvidenceRegistry`.

- [ ] **Step 4: Run Day 1 and Day 4 assertions**

Run: `python ops/test_daily_autonomous_learning.py`
Expected: Day 1 registers internal evidence; Day 4 cannot adopt one-upstream/repost/search evidence.

### Task 3: Governance, Lifecycle, and Non-Adoption Results

**Files:**
- Modify: `core/daily_learning.py`
- Test: `ops/test_daily_autonomous_learning.py`

- [ ] **Step 1: Write failing Day 2, Day 3, and no-target tests**

```python
assert day2["mode"] == "external"
assert day3["outcome"] in {"observe", "reject"}
assert no_target["outcome"] == "NO_VALID_LEARNING_TARGET"
assert same_day == no_target
```

- [ ] **Step 2: Run the test and verify it fails**

Run: `python ops/test_daily_autonomous_learning.py`
Expected: outcomes/lifecycle records are absent.

- [ ] **Step 3: Implement result mapping and lifecycle history**

For every learning candidate, create/retrieve a `KnowledgeLifecycle`, record Observation, Research, Validation, Contract and Repository Candidate stages where permitted. Invoke `Governor.evaluate()` only after evidence/independence evaluation. Map `pass` to `adopt`, `delay/revise/merge/split/supersede` to `observe`, and `reject` to `reject`. Only `adopt` calls `ExperienceDeposition`; archive all final task records and persist the explicit task-role/governance discrepancy in task output. Persist one daily terminal JSON record; reuse it for same-day idempotency.

- [ ] **Step 4: Run all logical-day checks**

Run: `python ops/test_daily_autonomous_learning.py`
Expected: Day 2 external fallback, Day 3 duplicate prevention, Day 4 non-adoption, and no-target idempotency pass.

### Task 4: Isolated Safety Regression

**Files:**
- Test: `ops/test_daily_autonomous_learning.py`

- [ ] **Step 1: Add prohibited-path assertions**

```python
source = Path("core/daily_learning.py").read_text(encoding="utf-8")
for forbidden in ("tg_notifier", "stock_data_reliability", "AUTO_RUN", "AUTO_PUSH"):
    assert forbidden not in source
```

Use only temporary directories and fixture callables. Assert the external discoverer is called only on Day 2/Day 4 and the internal source is selected on Day 1.

- [ ] **Step 2: Run the isolated regression**

Run: `python ops/test_daily_autonomous_learning.py`
Expected: `daily autonomous learning simulation passed`.

- [ ] **Step 3: Run existing affected regressions**

Run: `python ops/test_discovery_mode.py; python ops/test_stock_data_reliability.py`
Expected: both existing isolated regression scripts pass.

- [ ] **Step 4: Do not commit**

The user explicitly prohibited a commit. Leave all implementation and test changes uncommitted.

## Self-Review

- Internal-first selection: Task 2.
- Learning contract enforcement: Task 1.
- External hierarchy and no fixed source list: Task 2 through injected discoverer and tier metadata.
- Evidence registration, independent origins, repost/search rejection: Task 2.
- Cross-validation, governor mapping, lifecycle, archive, deposition: Task 3.
- Day 1-4, no target, idempotency, prohibited-side-effect verification: Task 4.
- No general Validator/Guardian refactor: all tasks use only their existing interfaces and record the discrepancy in task output.
