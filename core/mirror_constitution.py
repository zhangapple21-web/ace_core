"""ACE 镜子宪法的最小运行时契约。

R2 留下了 ``Identity -> Intent -> Routing -> Execution -> Memory``、经验反哺、
分层记忆和 Guardian 否决权等结构。这个模块只把这些结构收敛成纯校验函数，
不新增队列、调度器、人格或执行权限。

核心边界：
* 学习只接收明确来源，不把推断当成主人意图；
* 超越只产生候选和验证要求，不获得执行权；
* 守护通过数据分级、出站检查和责任收口保护 ACE；
* 模型输出永远是建议，不是事实、授权或生产收据。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Optional


CONTRACT_VERSION = "ace.mirror_constitution.v1"
RESPONSIBILITY_PROTOCOL = "ACE-RESPONSIBILITY-COMPLETION-1.0"

LEARN = "LEARN"
EXTEND = "EXTEND"
GUARD = "GUARD"

DATA_CLASSES = {"PUBLIC", "CAPABILITY", "STRUCTURE", "PRIVATE", "CORE"}
INTENT_KINDS = {
    "REQUEST",
    "PRINCIPLE",
    "PREFERENCE",
    "OBSERVATION",
    "CAPABILITY",
    "STRUCTURE_CHANGE",
    "UNKNOWN",
}
SOURCE_SCOPES = {"EXPLICIT_USER_INPUT", "AUTHORIZED_PROJECT_CONTEXT", "VERIFIED_EVIDENCE"}
EGRESS_TARGETS = {"INTERNAL", "MODEL_CONTEXT", "PUBLIC", "EXTERNAL"}

MIRROR_CONTEXT = """镜子宪法（ACE-MIRROR-CONSTITUTION-1.0）：
1. 学习你：只从明确输入、授权项目上下文和独立验证证据学习；不得把模型推测当作主人意图、事实或长期偏好。
2. 超越你：主动发现缺口、提出方案、询问模型并补全验证，但思考和模型调用永不获得执行、生产、晋升或路由修改权。
3. 守护你：每个记忆/输出必须有数据分级；PRIVATE/CORE 不得外发，STRUCTURE/CAPABILITY 对外必须脱敏；Guardian、Admission 和现有生命周期是唯一收口。
4. 责任完成：任务只有在目标、验收标准、证据、结果、评估、学习回流、未知/下一步和权限边界都被记录后，才可声称责任完成；缺项必须保留 UNKNOWN 或 WARNING。
5. 责任位置可替换：模型、Provider、窗口、Skill 和 Worker 都是临时执行资源，不是 ACE 身份或治理者。
"""


def build_mirror_context() -> str:
    """返回注入模型执行契约的稳定上下文。"""

    return MIRROR_CONTEXT.strip()


def build_intent_envelope(
    *,
    intent_kind: str,
    claim: str,
    source_scope: str = "EXPLICIT_USER_INPUT",
    source_refs: Optional[list[str]] = None,
    data_class: str = "STRUCTURE",
) -> dict[str, Any]:
    """构造无执行权的意图候选。

    该函数只构造候选，不读取环境、不调用模型、不写文件。
    """

    return {
        "contract_version": CONTRACT_VERSION,
        "intent_kind": str(intent_kind or "UNKNOWN").strip().upper(),
        "claim": str(claim or "").strip(),
        "source_scope": str(source_scope or "").strip(),
        "source_refs": [
            ref.strip()
            for ref in (source_refs or [])
            if isinstance(ref, str) and ref.strip()
        ],
        "data_class": str(data_class or "").strip().upper(),
        "authority": {
            "execution_authorized": False,
            "production_integration": False,
            "routing_change": False,
            "promotion": False,
        },
        "review_status": "NEEDS_VALIDATION",
        "created_at": datetime.now().isoformat(),
    }


def validate_intent_envelope(envelope: Any) -> dict[str, Any]:
    """校验意图候选，防止解释层越权成为执行授权。"""

    errors: list[str] = []
    if not isinstance(envelope, Mapping):
        return {"valid": False, "errors": ["intent_envelope_missing"], "contract_version": CONTRACT_VERSION}
    if envelope.get("contract_version") != CONTRACT_VERSION:
        errors.append("intent_contract_version_mismatch")
    if envelope.get("intent_kind") not in INTENT_KINDS:
        errors.append("intent_kind_invalid")
    if not isinstance(envelope.get("claim"), str) or not envelope["claim"].strip():
        errors.append("intent_claim_missing")
    if envelope.get("source_scope") not in SOURCE_SCOPES:
        errors.append("intent_source_scope_invalid")
    refs = envelope.get("source_refs")
    if not isinstance(refs, list) or not refs or not all(isinstance(ref, str) and ref.strip() for ref in refs):
        errors.append("intent_source_refs_missing")
    if envelope.get("data_class") not in DATA_CLASSES:
        errors.append("intent_data_class_invalid")
    authority = envelope.get("authority")
    if not isinstance(authority, Mapping):
        errors.append("intent_authority_missing")
    else:
        for field in ("execution_authorized", "production_integration", "routing_change", "promotion"):
            if authority.get(field) is not False:
                errors.append(f"intent_authority_{field}_must_be_false")
    return {
        "valid": not errors,
        "errors": list(dict.fromkeys(errors)),
        "contract_version": CONTRACT_VERSION,
        "side_effects": {"model_called": False, "persistent_write": False, "execution_authorized": False},
    }


def validate_data_boundary(record: Any, *, target: str = "INTERNAL") -> dict[str, Any]:
    """检查数据分级和出站目标；未知分级默认拒绝外发。"""

    errors: list[str] = []
    target = str(target or "").strip().upper()
    if target not in EGRESS_TARGETS:
        errors.append("egress_target_invalid")
    if not isinstance(record, Mapping):
        errors.append("data_boundary_record_missing")
        return {"valid": False, "errors": errors, "data_class": None, "target": target}
    data_class = str(record.get("data_class") or "").strip().upper()
    if data_class not in DATA_CLASSES:
        errors.append("data_class_unknown")
    if data_class in {"PRIVATE", "CORE"} and target != "INTERNAL":
        errors.append("sensitive_data_cannot_egress")
    if data_class in {"CAPABILITY", "STRUCTURE"} and target in {"MODEL_CONTEXT", "PUBLIC", "EXTERNAL"}:
        if record.get("sanitized") is not True:
            errors.append("sanitization_required_before_egress")
    return {
        "valid": not errors,
        "errors": list(dict.fromkeys(errors)),
        "data_class": data_class or None,
        "target": target,
        "execution_authorized": False,
    }


def _nonempty(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Mapping):
        return bool(value)
    if isinstance(value, (list, tuple, set)):
        return bool(value)
    return value is not None


def _evidence_refs(task: Any) -> list[str]:
    refs: list[str] = []
    for item in getattr(task, "evidence", []) or []:
        if isinstance(item, Mapping):
            ref = item.get("source") or item.get("source_ref")
        else:
            ref = ""
        if isinstance(ref, str) and ref.strip() and ref.strip() not in refs:
            refs.append(ref.strip())
    return refs


def build_responsibility_packet(task: Any, *, scope: Optional[Mapping[str, Any]] = None) -> dict[str, Any]:
    """从现有 Task/协议投影责任收口包，不增加第二个生命周期。"""

    outputs = getattr(task, "outputs", None)
    outputs = outputs if isinstance(outputs, Mapping) else {}
    work = outputs.get("work_contract", {}) if isinstance(outputs.get("work_contract", {}), Mapping) else {}
    evidence_packet = outputs.get("evidence_packet", {}) if isinstance(outputs.get("evidence_packet", {}), Mapping) else {}
    receipt = outputs.get("release_receipt", {}) if isinstance(outputs.get("release_receipt", {}), Mapping) else {}
    criteria = work.get("acceptance_criteria", [])
    if not isinstance(criteria, list):
        criteria = []
    refs = _evidence_refs(task)
    if not refs and isinstance(evidence_packet.get("items"), list):
        refs = [str(item.get("source")).strip() for item in evidence_packet["items"] if isinstance(item, Mapping) and str(item.get("source", "")).strip()]
    result = getattr(task, "result", None)
    validator = outputs.get("last_validator_result", {})
    if not isinstance(validator, Mapping):
        validator = {}
    requested_purpose = (scope or {}).get("purpose") or outputs.get("protocol_purpose")
    if not requested_purpose:
        tags = {str(tag).strip().lower() for tag in (getattr(task, "tags", []) or [])}
        if "external_delivery" in tags or "delivery" in tags or "release" in tags:
            requested_purpose = "external_delivery"
        elif "long_term_rule" in tags or "axiom" in tags or "constraint" in tags:
            requested_purpose = "long_term_rule"
    purpose = str(requested_purpose or "internal_production")
    data_class = str(
        (scope or {}).get("data_class")
        or outputs.get("data_class")
        or "STRUCTURE"
    ).strip().upper()
    outcome_receipt = outputs.get("verified_outcome_receipt") or outputs.get("outcome_receipt")
    return {
        "protocol": RESPONSIBILITY_PROTOCOL,
        "contract_version": CONTRACT_VERSION,
        "task_id": str(getattr(task, "task_id", "")),
        "intent": str(getattr(task, "hypothesis", "") or getattr(task, "title", "")).strip(),
        "acceptance_criteria": criteria,
        "evidence_refs": list(dict.fromkeys(refs)),
        "outcome": result if _nonempty(result) else {"status": getattr(task, "status", "UNKNOWN"), "unknown": "task_result_missing"},
        "evaluation": {
            "validator": dict(validator),
            "evidence_status": evidence_packet.get("status", "UNKNOWN"),
            "release_status": receipt.get("status", "NOT_APPLICABLE"),
            "outcome_receipt_status": (
                outcome_receipt.get("status", "UNKNOWN")
                if isinstance(outcome_receipt, Mapping)
                else "UNKNOWN"
            ),
        },
        "task_status": str(getattr(task, "status", "UNKNOWN")),
        "guardian_decision": getattr(task, "guardian_decision", None),
        "learning_return": outputs.get("learning_return", ""),
        "unknowns": outputs.get("unknowns", ["learning_return_pending"]),
        "next_action": outputs.get("next_action", "继续现有 Validator/Guardian 生命周期并补齐缺项"),
        "authority": {
            "execution_authorized": False,
            "production_integration": False,
            "promotion": False,
            "source": "existing_ace_lifecycle",
        },
        "data_class": data_class,
        "purpose": purpose,
        "created_at": datetime.now().isoformat(),
    }


def validate_responsibility_packet(
    packet: Any,
    *,
    task_id: Optional[str] = None,
    strict: bool = False,
) -> dict[str, Any]:
    """验证责任收口；strict 只由既有 Guardian/交付边界显式启用。"""

    errors: list[str] = []
    if not isinstance(packet, Mapping):
        return {"valid": False, "status": "INCOMPLETE", "errors": ["responsibility_packet_missing"]}
    if packet.get("protocol") != RESPONSIBILITY_PROTOCOL:
        errors.append("responsibility_protocol_mismatch")
    if packet.get("contract_version") != CONTRACT_VERSION:
        errors.append("responsibility_contract_version_mismatch")
    if task_id and str(packet.get("task_id")) != str(task_id):
        errors.append("responsibility_task_id_mismatch")
    for field in ("task_id", "intent", "outcome", "evaluation", "next_action"):
        if not _nonempty(packet.get(field)):
            errors.append(f"responsibility_{field}_missing")
    warnings: list[str] = []
    for field in ("acceptance_criteria", "evidence_refs", "unknowns"):
        if not isinstance(packet.get(field), list):
            errors.append(f"responsibility_{field}_invalid")
    if isinstance(packet.get("acceptance_criteria"), list) and not packet["acceptance_criteria"]:
        warnings.append("responsibility_acceptance_criteria_pending")
    if isinstance(packet.get("evidence_refs"), list) and not packet["evidence_refs"]:
        warnings.append("responsibility_evidence_refs_pending")
    if not isinstance(packet.get("authority"), Mapping):
        errors.append("responsibility_authority_missing")
    else:
        for field in ("execution_authorized", "production_integration", "promotion"):
            if packet["authority"].get(field) is not False:
                errors.append(f"responsibility_authority_{field}_must_be_false")
    if packet.get("data_class") not in DATA_CLASSES:
        errors.append("responsibility_data_class_invalid")
    learning_return = packet.get("learning_return")
    learning_return_valid = _nonempty(learning_return)
    if isinstance(learning_return, Mapping):
        if str(learning_return.get("status", "")).strip().upper() == "NOT_APPLICABLE":
            learning_return_valid = bool(str(learning_return.get("reason", "")).strip())
    elif isinstance(learning_return, str) and learning_return.strip().upper() == "NOT_APPLICABLE":
        learning_return_valid = False
    if not learning_return_valid:
        if strict:
            errors.append("responsibility_learning_return_missing")
        else:
            warnings.append("responsibility_learning_return_pending")
    if packet.get("unknowns") and not _nonempty(packet.get("next_action")):
        errors.append("responsibility_unknowns_without_next_action")
    outcome = packet.get("outcome")
    if strict and isinstance(outcome, Mapping) and outcome.get("unknown") == "task_result_missing":
        errors.append("responsibility_outcome_unverified")
    if strict and not packet.get("acceptance_criteria"):
        errors.append("responsibility_acceptance_criteria_missing")
    if strict and not packet.get("evidence_refs"):
        errors.append("responsibility_evidence_refs_missing")
    errors = list(dict.fromkeys(errors))
    warnings = list(dict.fromkeys(warnings))
    status = "INCOMPLETE" if errors else ("COMPLETE_WITH_WARNINGS" if warnings else "COMPLETE")
    return {
        "valid": not errors,
        "status": status,
        "errors": errors,
        "warnings": warnings,
        "protocol": RESPONSIBILITY_PROTOCOL,
        "strict": bool(strict),
        "execution_authorized": False,
    }


__all__ = [
    "CONTRACT_VERSION",
    "DATA_CLASSES",
    "EGRESS_TARGETS",
    "EXTEND",
    "GUARD",
    "INTENT_KINDS",
    "LEARN",
    "MIRROR_CONTEXT",
    "RESPONSIBILITY_PROTOCOL",
    "build_intent_envelope",
    "build_mirror_context",
    "build_responsibility_packet",
    "validate_data_boundary",
    "validate_intent_envelope",
    "validate_responsibility_packet",
]
