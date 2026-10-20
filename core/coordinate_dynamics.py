"""ACE Coordinate Dynamics v1.

This is the recovered R1-shaped state loop expressed as a governed, replayable
runtime contract:

    state -> active axes -> direction -> bounded action -> feedback -> update

It is deliberately not a second scheduler, TaskPool, governance owner, or
"soul" implementation.  It computes a coordinate receipt for the existing
closed-loop engine; callers remain responsible for admission and execution.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping

CONTRACT_VERSION = "ace.coordinate_dynamics.v1"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()[:24]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Axis:
    axis_id: str
    weight: float = 1.0
    enabled: bool = True


@dataclass
class CoordinateReceipt:
    contract_version: str
    coordinate_id: str
    created_at: str
    objective: str
    active_axes: list[str]
    position: dict[str, float]
    target: dict[str, float]
    direction: dict[str, float]
    selected_axis: str
    confidence: float
    feedback: dict[str, Any] = field(default_factory=dict)
    updated_position: dict[str, float] = field(default_factory=dict)
    lineage: dict[str, Any] = field(default_factory=dict)
    receipt_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["receipt_hash"] = ""
        payload["receipt_hash"] = _hash(payload)
        return payload


class CoordinateDynamics:
    """Deterministic coordinate selection and feedback update."""

    def __init__(self, axes: list[Axis] | None = None) -> None:
        self.axes = axes or []

    def locate(
        self,
        *,
        objective: str,
        position: Mapping[str, Any],
        target: Mapping[str, Any],
        state: Mapping[str, Any] | None = None,
        feedback: Mapping[str, Any] | None = None,
        lineage: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not str(objective).strip():
            raise ValueError("objective_required")
        position_f = self._numeric_map(position, "position")
        target_f = self._numeric_map(target, "target")
        names = sorted(set(position_f) | set(target_f) | {axis.axis_id for axis in self.axes if axis.enabled})
        state = state or {}
        active_requested = state.get("active_axes")
        if active_requested is not None and not isinstance(active_requested, list):
            raise ValueError("active_axes_must_be_list")
        allowed = {str(item) for item in active_requested} if isinstance(active_requested, list) else set(names)
        weights = {axis.axis_id: float(axis.weight) for axis in self.axes if axis.enabled}
        active = [name for name in names if name in allowed and (name in position_f or name in target_f)]
        if not active:
            raise ValueError("no_active_axis")
        direction = {name: round(target_f.get(name, 0.0) - position_f.get(name, 0.0), 8) for name in active}
        ranked = sorted(active, key=lambda name: (abs(direction[name]) * weights.get(name, 1.0), name), reverse=True)
        selected = ranked[0]
        magnitude = abs(direction[selected])
        total = sum(abs(direction[name]) * weights.get(name, 1.0) for name in active)
        confidence = round((abs(direction[selected]) * weights.get(selected, 1.0)) / total, 8) if total else 0.0
        current_feedback = dict(feedback or {})
        updated = dict(position_f)
        delta = current_feedback.get("observed_delta", {})
        if delta is not None:
            if not isinstance(delta, Mapping):
                raise ValueError("observed_delta_must_be_mapping")
            for name, value in delta.items():
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ValueError(f"observed_delta_not_numeric:{name}")
                updated[str(name)] = round(updated.get(str(name), 0.0) + float(value), 8)
        receipt = CoordinateReceipt(
            contract_version=CONTRACT_VERSION,
            coordinate_id=f"CD-{_hash({'objective': objective, 'position': position_f, 'target': target_f, 'lineage': lineage or {}})}",
            created_at=_now(),
            objective=str(objective).strip(),
            active_axes=active,
            position=position_f,
            target=target_f,
            direction=direction,
            selected_axis=selected if magnitude else "",
            confidence=confidence,
            feedback=current_feedback,
            updated_position=updated,
            lineage=dict(lineage or {}),
        )
        payload = receipt.to_dict()
        payload["state_transition"] = "FEEDBACK_APPLIED" if delta else "LOCATED"
        return payload

    @staticmethod
    def _numeric_map(value: Mapping[str, Any], label: str) -> dict[str, float]:
        if not isinstance(value, Mapping):
            raise ValueError(f"{label}_must_be_mapping")
        result: dict[str, float] = {}
        for key, item in value.items():
            if isinstance(item, bool) or not isinstance(item, (int, float)):
                raise ValueError(f"{label}_not_numeric:{key}")
            result[str(key)] = float(item)
        return result


class WorkConservationGate:
    """Prevent a closed loop from manufacturing work without new discovery."""

    def __init__(self) -> None:
        self._seen: set[tuple[str, str]] = set()

    def admit(self, *, work_signature: str, discovery_refs: list[str], window_id: str) -> dict[str, Any]:
        signature = str(work_signature).strip()
        window = str(window_id).strip()
        refs = sorted({str(ref).strip() for ref in discovery_refs if str(ref).strip()})
        if not signature or not window:
            raise ValueError("work_signature_and_window_required")
        key = (window, signature)
        if not refs:
            return {"admitted": False, "reason": "NO_NEW_DISCOVERY", "work_signature": signature, "window_id": window, "discovery_refs": []}
        if key in self._seen:
            return {"admitted": False, "reason": "DUPLICATE_WORK_IN_WINDOW", "work_signature": signature, "window_id": window, "discovery_refs": refs}
        self._seen.add(key)
        return {"admitted": True, "reason": "NEW_DISCOVERY", "work_signature": signature, "window_id": window, "discovery_refs": refs}


__all__ = ["Axis", "CoordinateDynamics", "CoordinateReceipt", "WorkConservationGate", "CONTRACT_VERSION"]
