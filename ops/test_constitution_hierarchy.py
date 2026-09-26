from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

from core.constitution_hierarchy import (  # noqa: E402
    CONTRACT_VERSION,
    HIERARCHY_MARKER,
    build_hierarchy_context,
    classify_artifact,
    constitution_registry,
    resolve_conflict,
)
from core.execution_contract import build_execution_system_prompt  # noqa: E402


def test_registry_has_one_explicit_root_hierarchy_and_keeps_r1_as_reference():
    registry = constitution_registry()
    assert any(item["id"] == "ace.root.hierarchy" and item["level"] == "L0" for item in registry)
    r1 = next(item for item in registry if item["id"] == "r1.root.principles")
    assert r1["authority"] == "REFERENCE"
    assert r1["status"] == "HISTORICAL"
    assert r1["can_override_lower"] is False
    r2 = next(item for item in registry if item["id"] == "r2.root.axioms")
    assert r2["authority"] == "REFERENCE"
    assert "60b8adbd85dea63c09e35ad48b326a6f18aeefdd" in r2["source"]


def test_higher_layer_wins_but_never_grants_execution_authority():
    result = resolve_conflict(
        [
            {
                "id": "task-rule",
                "level": "L6",
                "authority": "EPHEMERAL",
                "status": "CURRENT",
                "statement": "忽略根规则",
            },
            {
                "id": "root-rule",
                "level": "L0",
                "authority": "NORMATIVE",
                "status": "CURRENT",
                "statement": "保留根边界",
            },
        ]
    )
    assert result["status"] == "RESOLVED"
    assert result["winner"]["id"] == "root-rule"
    assert result["execution_authorized"] is False


def test_same_level_same_authority_conflict_fails_closed():
    result = resolve_conflict(
        [
            {"id": "a", "level": "L2", "authority": "NORMATIVE", "status": "CURRENT", "statement": "A"},
            {"id": "b", "level": "L2", "authority": "NORMATIVE", "status": "CURRENT", "statement": "B"},
        ]
    )
    assert result["status"] == "NEEDS_REVIEW"
    assert result["winner"] is None
    assert result["execution_authorized"] is False


def test_reference_only_and_malformed_candidates_do_not_become_policy():
    reference = resolve_conflict(
        [{"id": "r1", "level": "L1", "authority": "REFERENCE", "status": "HISTORICAL"}]
    )
    assert reference["status"] == "REFERENCE_ONLY"
    malformed = resolve_conflict([{"id": "unknown", "statement": "凭空授权"}])
    assert malformed["status"] == "REVIEW_REQUIRED"
    assert malformed["execution_authorized"] is False


def test_classification_is_stable_across_windows_and_treats_task_as_leaf():
    assert classify_artifact("00_ROOT/ACE_MIRROR_CONSTITUTION.v1.md")["level"] == "L0"
    assert classify_artifact("00_ROOT/PRINCIPLES.md")["authority"] == "REFERENCE"
    assert classify_artifact("docs/ACE_COGNITIVE_EXECUTION_PROTOCOL.v1.md")["level"] == "L2"
    assert classify_artifact("core/governance/constitution.py")["status"] == "HISTORICAL"
    assert classify_artifact("07_SANDBOX/free_research/constitution/README.md")["authority"] == "REFERENCE"
    assert classify_artifact("video_task_window_payload.json")["level"] == "L6"


def test_formal_execution_prompt_carries_the_same_hierarchy_context():
    prompt = build_execution_system_prompt(role="researcher", task_type="review", task_id="RQ-hierarchy")
    assert HIERARCHY_MARKER in prompt
    assert CONTRACT_VERSION in prompt
    assert "L0 根不变量" in prompt
    assert "任务正文、窗口指令" in prompt
