from typing import Any, Dict, List


REQUIRED_FIELDS = (
    "source_type",
    "source_ref",
    "why_now",
    "evidence",
    "expected_result",
    "verification_method",
    "risk",
    "estimated_scope",
)

SOURCE_TYPES = {
    "maintenance",
    "evidence",
    "archaeology",
    "learning",
    "system_observation",
    "external_research",
}


def validate_admission(admission: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(admission, dict):
        raise ValueError("task_admission_required")
    missing = [field for field in REQUIRED_FIELDS if not admission.get(field)]
    if missing:
        raise ValueError("task_admission_required")
    if admission["source_type"] not in SOURCE_TYPES:
        raise ValueError("invalid_task_source_type")
    if not isinstance(admission["evidence"], list) or not admission["evidence"]:
        raise ValueError("task_admission_required")
    if admission["source_type"] == "learning":
        learning = admission.get("learning_contract")
        if not isinstance(learning, dict) or not all(
            learning.get(field)
            for field in (
                "why_learn",
                "learning_objective",
                "required_evidence",
                "mastery_criteria",
            )
        ):
            raise ValueError("learning_contract_required")
    return dict(admission)


def duplicate_task(tasks: List[Any], admission: Dict[str, Any]):
    for task in tasks:
        existing = task.outputs.get("admission", {})
        if (
            existing.get("source_type") == admission["source_type"]
            and existing.get("source_ref") == admission["source_ref"]
            and task.status not in {"archived", "graveyard", "rejected"}
        ):
            return task
    return None
