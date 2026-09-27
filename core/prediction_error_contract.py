"""ACE 预测误差契约。

这不是一个新的调度器，也不替代 ``ClosedLoopEngine``。它把一次行动中最
容易丢失的现实反馈固定成可回放收据：

    expected state -> success observables -> actual observation -> mismatch
    -> KEEP / RETRY / ROLLBACK / UNKNOWN

模型输出、任务完成和 Provider 返回成功都不能代替 actual observation。
只有真实可观测结果才能结束预测；未知结果保持 UNKNOWN，不能被乐观地
解释为通过。收据本身不授予执行权或生产集成权。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping


CONTRACT_VERSION = "ace.prediction_error.v1"
SCHEMA = CONTRACT_VERSION
DECISIONS = {"KEEP", "RETRY", "ROLLBACK", "UNKNOWN"}
OBSERVATION_STATUSES = {"MATCHED", "MISMATCHED", "UNKNOWN"}
_MISSING = object()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _path_get(value: Any, path: str) -> Any:
    """读取点号路径；数组下标也支持，但越界必须返回 UNKNOWN。"""

    current = value
    for part in str(path or "").split("."):
        if not part:
            return _MISSING
        if isinstance(current, Mapping):
            if part not in current:
                return _MISSING
            current = current[part]
        elif isinstance(current, (list, tuple)) and part.isdigit():
            index = int(part)
            if index >= len(current):
                return _MISSING
            current = current[index]
        else:
            return _MISSING
    return current


def _display(value: Any) -> Any:
    return "<MISSING>" if value is _MISSING else value


def _refs(value: Iterable[Any] | str | None) -> list[str]:
    if value is None:
        return []
    raw = [value] if isinstance(value, str) else value
    if not isinstance(raw, (list, tuple, set)):
        return []
    result: list[str] = []
    for item in raw:
        text = str(item or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _observable_specs(value: Iterable[Mapping[str, Any]] | Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """标准化成功观测定义，拒绝无名称的模糊观测。"""

    if value is None:
        return []
    if isinstance(value, Mapping):
        raw: list[Any] = [
            {"name": key, "path": key, **(item if isinstance(item, Mapping) else {"expected": item})}
            for key, item in value.items()
        ]
    elif isinstance(value, (list, tuple)):
        raw = list(value)
    else:
        raise ValueError("success_observables_must_be_list_or_mapping")
    specs: list[dict[str, Any]] = []
    for index, item in enumerate(raw, start=1):
        if not isinstance(item, Mapping):
            raise ValueError(f"observable_must_be_mapping:{index}")
        name = str(item.get("name") or item.get("path") or "").strip()
        path = str(item.get("path") or name).strip()
        if not name or not path:
            raise ValueError(f"observable_name_and_path_required:{index}")
        spec = dict(item)
        spec["name"] = name
        spec["path"] = path
        spec["required"] = item.get("required", True) is not False
        specs.append(spec)
    return specs


def compare_prediction(
    expected_state: Mapping[str, Any] | None,
    actual_observation: Mapping[str, Any] | None,
    success_observables: Iterable[Mapping[str, Any]] | Mapping[str, Any] | None,
) -> dict[str, Any]:
    """比较预期和真实观测。

    每个 observable 可以指定 ``expected`` 覆盖 expected_state 中的值，并可
    指定数值 ``tolerance``。没有真实值或没有预期值都只能得到 UNKNOWN。
    ``None`` 是合法的真实值，因此不能用 truthiness 判断是否缺失。
    """

    expected = expected_state if isinstance(expected_state, Mapping) else {}
    actual = actual_observation if isinstance(actual_observation, Mapping) else {}
    rows: list[dict[str, Any]] = []
    unknown_count = 0
    mismatch_count = 0
    matched_count = 0
    for spec in _observable_specs(success_observables):
        path = spec["path"]
        expected_value = spec["expected"] if "expected" in spec else _path_get(expected, path)
        actual_value = _path_get(actual, path)
        row = {
            "name": spec["name"],
            "path": path,
            "expected": _display(expected_value),
            "actual": _display(actual_value),
            "required": spec["required"],
        }
        if expected_value is _MISSING or actual_value is _MISSING:
            row["status"] = "UNKNOWN"
            row["reason"] = "expected_or_actual_value_missing"
            unknown_count += 1
            rows.append(row)
            continue
        tolerance = spec.get("tolerance", 0)
        numeric = isinstance(expected_value, (int, float)) and not isinstance(expected_value, bool) and isinstance(actual_value, (int, float)) and not isinstance(actual_value, bool)
        if numeric:
            try:
                matched = abs(float(actual_value) - float(expected_value)) <= float(tolerance or 0)
            except (TypeError, ValueError):
                matched = False
        else:
            matched = actual_value == expected_value
        row["status"] = "MATCHED" if matched else "MISMATCHED"
        if matched:
            matched_count += 1
        else:
            mismatch_count += 1
        rows.append(row)

    if unknown_count:
        status = "UNKNOWN"
    elif mismatch_count:
        status = "MISMATCHED"
    elif matched_count:
        status = "MATCHED"
    else:
        status = "UNKNOWN"
    return {
        "status": status,
        "matched_count": matched_count,
        "mismatch_count": mismatch_count,
        "unknown_count": unknown_count,
        "observables": rows,
    }


def _derive_decision(comparison: Mapping[str, Any], specs: Iterable[Mapping[str, Any]], hint: str | None) -> str:
    status = str(comparison.get("status") or "UNKNOWN")
    normalized_hint = str(hint or "").strip().upper()
    if normalized_hint and normalized_hint not in DECISIONS:
        raise ValueError(f"invalid_prediction_decision:{normalized_hint}")
    if status == "UNKNOWN":
        return "UNKNOWN"
    if status == "MATCHED":
        if normalized_hint in {"RETRY", "ROLLBACK"}:
            return normalized_hint
        return "KEEP"
    critical_names = {
        str(spec.get("name") or spec.get("path") or "")
        for spec in specs
        if spec.get("rollback_required") is True or str(spec.get("severity") or "").lower() == "critical"
    }
    mismatches = {
        str(row.get("name") or "")
        for row in comparison.get("observables", [])
        if row.get("status") == "MISMATCHED"
    }
    if critical_names & mismatches or normalized_hint == "ROLLBACK":
        return "ROLLBACK"
    if normalized_hint == "UNKNOWN":
        return "UNKNOWN"
    return "RETRY"


def build_prediction_receipt(
    *,
    subject: str,
    expected_state: Mapping[str, Any],
    success_observables: Iterable[Mapping[str, Any]] | Mapping[str, Any],
    actual_observation: Mapping[str, Any] | None,
    resource_budget: Mapping[str, Any] | None = None,
    observation_refs: Iterable[Any] | str | None = None,
    experience_ref: str = "",
    decision_hint: str | None = None,
    prediction_id: str = "",
) -> dict[str, Any]:
    """生成一份可验证、不可伪造为生产授权的预测误差收据。"""

    subject = str(subject or "").strip()
    if not subject:
        raise ValueError("prediction_subject_required")
    if not isinstance(expected_state, Mapping):
        raise ValueError("expected_state_must_be_mapping")
    if actual_observation is not None and not isinstance(actual_observation, Mapping):
        raise ValueError("actual_observation_must_be_mapping_or_none")
    specs = _observable_specs(success_observables)
    if not specs:
        raise ValueError("success_observables_required")
    actual = actual_observation if isinstance(actual_observation, Mapping) else {}
    comparison = compare_prediction(expected_state, actual_observation, specs)
    decision = _derive_decision(comparison, specs, decision_hint)
    refs = _refs(observation_refs)
    # A payload supplied by a caller is not automatically a reality observation.
    # Without a traceable readback/receipt reference, keep the epistemic status
    # UNKNOWN even when the values happen to match.
    if not refs:
        decision = "UNKNOWN"
    semantic = {
        "subject": subject,
        "expected_state": dict(expected_state),
        "success_observables": specs,
        "actual_observation": dict(actual),
        "observation_refs": refs,
        "comparison": comparison,
        "decision": decision,
    }
    generated_id = "PE-" + _sha(semantic)[:20]
    supplied_id = str(prediction_id or generated_id).strip()
    if not supplied_id:
        raise ValueError("prediction_id_required")
    receipt = {
        "schema": SCHEMA,
        "contract_version": CONTRACT_VERSION,
        "prediction_id": supplied_id,
        "created_at": _now(),
        "subject": subject,
        "expected_state": dict(expected_state),
        "success_observables": specs,
        "resource_budget": dict(resource_budget or {}),
        "observation_refs": refs,
        "observation_verified": bool(refs),
        "actual_observation": dict(actual),
        "comparison": comparison,
        "mismatch": comparison["status"] == "MISMATCHED",
        "decision": decision,
        "experience_ref": str(experience_ref or ""),
        "learning_status": "LINKED" if str(experience_ref or "").strip() else ("PENDING" if decision in {"RETRY", "ROLLBACK", "UNKNOWN"} else "NOT_REQUIRED"),
        "execution_authorized": False,
        "production_integration": False,
        "receipt_hash": "",
    }
    receipt["receipt_hash"] = _sha({key: value for key, value in receipt.items() if key not in {"receipt_hash", "created_at"}})
    return receipt


def validate_prediction_receipt(receipt: Mapping[str, Any] | None) -> dict[str, Any]:
    """在任何运行时消费前重算关键字段，阻止手工改成 KEEP 或授权。"""

    if not isinstance(receipt, Mapping) or receipt.get("schema") != SCHEMA:
        raise ValueError("invalid_prediction_receipt_schema")
    item = dict(receipt)
    if item.get("execution_authorized") is not False or item.get("production_integration") is not False:
        raise ValueError("prediction_receipt_has_execution_authority")
    decision = str(item.get("decision") or "")
    if decision not in DECISIONS:
        raise ValueError("invalid_prediction_receipt_decision")
    expected = item.get("expected_state")
    actual = item.get("actual_observation")
    specs = item.get("success_observables")
    comparison = compare_prediction(expected, actual, specs)
    derived = _derive_decision(comparison, _observable_specs(specs), decision)
    if not _refs(item.get("observation_refs")):
        derived = "UNKNOWN"
    if derived != decision:
        raise ValueError("prediction_receipt_decision_mismatch")
    supplied_comparison = item.get("comparison")
    if supplied_comparison != comparison:
        raise ValueError("prediction_receipt_comparison_mismatch")
    receipt_hash = str(item.get("receipt_hash") or "")
    if not receipt_hash:
        raise ValueError("prediction_receipt_hash_missing")
    expected_hash = _sha({key: value for key, value in item.items() if key not in {"receipt_hash", "created_at"}})
    if receipt_hash != expected_hash:
        raise ValueError("prediction_receipt_hash_mismatch")
    return item


def append_prediction_receipt(receipt: Mapping[str, Any], out_path: str | Path) -> dict[str, Any]:
    """幂等地写入预测误差收据；坏收据不会进入知识流。"""

    validated = validate_prediction_receipt(receipt)
    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    prediction_id = str(validated["prediction_id"])
    existing: set[str] = set()
    if target.exists():
        for line in target.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, Mapping) and item.get("prediction_id"):
                existing.add(str(item["prediction_id"]))
    if prediction_id in existing:
        return {"status": "UNCHANGED", "out": str(target), "prediction_id": prediction_id, "added": 0}
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(validated, ensure_ascii=False, sort_keys=True) + "\n")
    return {"status": "RECORDED", "out": str(target), "prediction_id": prediction_id, "added": 1}


__all__ = [
    "CONTRACT_VERSION",
    "DECISIONS",
    "OBSERVATION_STATUSES",
    "SCHEMA",
    "append_prediction_receipt",
    "build_prediction_receipt",
    "compare_prediction",
    "validate_prediction_receipt",
]
