import os
from typing import Any, Dict, List

from core.beneficiary_check import RED_FLAG, check_admission

BENEFICIARY_GATE_ENV = "ACE_BENEFICIARY_GATE"


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


def beneficiary_gate(admission: Dict[str, Any]) -> Dict[str, Any]:
    """受益人测试的准入载体。

    shadow（默认）= 只把结论计数附到准入卡上，不阻断；
    enforce = 红旗直接拒绝准入（ ValueError，与既有拒绝语同族）。
    只存 verdict/计数/模式名，不存正文聚合（C7/G-20：聚合值不落盘）。
    """
    report = check_admission(admission)
    if not report.get("applies"):
        return report
    summary = {
        "applies": True,
        "source_type": report["source_type"],
        "verdict": report["verdict"],
        "red_flags": report["red_flags"],
        "warnings": report["warnings"],
        "patterns": sorted({p for finding in report["findings"] for p in finding["patterns"]}),
    }
    mode = (os.environ.get(BENEFICIARY_GATE_ENV) or "shadow").strip().lower()
    if mode == "enforce" and report["verdict"] == "DISCARD":
        first = next(
            (f for f in report["findings"] if f["severity"] == RED_FLAG),
            {"patterns": [], "line": 0},
        )
        raise ValueError(
            "beneficiary_red_flag:"
            + ",".join(first.get("patterns", []))
            + f":unit_line_{first.get('line')}"
        )
    return summary


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
    result = dict(admission)
    gate = beneficiary_gate(admission)
    if gate.get("applies"):
        result["beneficiary_check"] = gate
    return result


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
