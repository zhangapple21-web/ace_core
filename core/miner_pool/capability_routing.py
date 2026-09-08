"""Capability-driven routing primitives for the ACE MinerPool.

The model pool is an execution fabric, not a second scheduler.  This module
keeps the mapping explicit and deterministic:

    task context -> capability -> eligible labour (model)

Terra remains the normal labour.  Astra is a bounded escalation labour for
complex or high-risk work.  Astra is intentionally marked as a candidate
route until the persisted evidence gate is satisfied; using it for a complex
POC does not silently promote it to the default brain.
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional


ROUTING_SCHEMA_VERSION = "ace.capability-routing.v1"
COMPLEXITY_ORDER = {"simple": 0, "medium": 1, "complex": 2}
EVIDENCE_FIELDS = (
    "independent_call_evidence",
    "failure_recovery_evidence",
    "cost_records",
    "provider_stability",
    "capability_verification_receipts",
    "fallback_compatibility_tests",
)


# Provider-qualified IDs are deliberately kept here so a model with the same
# display name on another provider cannot accidentally inherit evidence.
MODEL_CAPABILITIES: Dict[str, Dict[str, Any]] = {
    "shenwen:gpt-5.6-terra": {
        "capabilities": ["general_reasoning", "structured_synthesis", "coding"],
        "tier": "default",
        "production_eligible": True,
        "route_state": "DEFAULT",
    },
    "shenwen:gpt-6-astra": {
        "capabilities": [
            "deep_reasoning",
            "complex_planning",
            "architecture",
            "long_horizon",
            "coding",
        ],
        "tier": "escalation",
        "production_eligible": False,
        "route_state": "POC_COMPLEX_ESCALATION",
    },
    "shenwen:gpt-5.4-mini": {
        "capabilities": ["execution", "classification", "structured_extraction"],
        "tier": "efficient",
        "production_eligible": True,
        "route_state": "DEFAULT_EXECUTION",
    },
    "glm:glm-4-flash": {
        "capabilities": ["general_reasoning", "classification", "hypothesis_generation"],
        "tier": "efficient",
        "production_eligible": True,
        "route_state": "PRODUCTION_CANDIDATE",
    },
}


TASK_CAPABILITIES = {
    "reasoning": "general_reasoning",
    "strategic": "deep_reasoning",
    "execution": "execution",
    "hypothesis_generation": "hypothesis_generation",
    "cross_validation": "cross_validation",
    "synthesis": "structured_synthesis",
    "classification": "classification",
    "extraction": "structured_extraction",
    "coding": "coding",
    "fast_response": "general_reasoning",
}


def model_capability(model_id: str) -> Dict[str, Any]:
    """Return a copy of the model capability record, preserving unknowns."""

    value = MODEL_CAPABILITIES.get(model_id)
    if value is None:
        return {
            "capabilities": [],
            "tier": "unknown",
            "production_eligible": False,
            "route_state": "UNVERIFIED",
        }
    return dict(value)


def capability_for_task(task_type: str) -> str:
    return TASK_CAPABILITIES.get(str(task_type or "").lower(), "general_reasoning")


def infer_complexity(
    task_type: str,
    task_context: Optional[Mapping[str, Any]] = None,
    explicit: Optional[str] = None,
) -> tuple[str, str]:
    """Infer complexity from persisted task context without inspecting content.

    A caller can provide the execution-discipline classification directly.  If
    it is absent, only conservative structured fields are considered; an
    arbitrary prompt never upgrades itself to Astra merely by being verbose.
    """

    if explicit in COMPLEXITY_ORDER:
        return explicit, "explicit"
    context = task_context if isinstance(task_context, Mapping) else {}
    for key in ("complexity", "execution_complexity"):
        value = str(context.get(key, "")).lower()
        if value in COMPLEXITY_ORDER:
            return value, key
    envelope = context.get("execution_discipline")
    if isinstance(envelope, Mapping):
        value = str(envelope.get("complexity", "")).lower()
        if value in COMPLEXITY_ORDER:
            return value, "execution_discipline"
    if str(context.get("risk_level", "")).lower() in {"high", "critical"}:
        return "complex", "risk_level"
    if str(context.get("value_level", "")).upper() in {"L2_STRATEGIC", "L3_EXECUTION"}:
        return "complex", "value_level"
    if context.get("depends_on") or context.get("cross_system") is True:
        return "complex", "dependencies_or_cross_system"
    if str(task_type or "").lower() == "strategic":
        # Strategic is a capability, not an automatic Astra override.  Keep
        # the historical Terra baseline unless the task envelope says complex.
        return "medium", "strategic_default"
    return "simple", "default_light_branch"


def is_complex_escalation(complexity: str, task_context: Optional[Mapping[str, Any]] = None) -> bool:
    if COMPLEXITY_ORDER.get(str(complexity), 0) >= COMPLEXITY_ORDER["complex"]:
        return True
    context = task_context if isinstance(task_context, Mapping) else {}
    return str(context.get("risk_level", "")).lower() in {"high", "critical"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _route_id(task_type: str, capability: str, model: str, at: str) -> str:
    seed = f"{task_type}|{capability}|{model}|{at}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:20]


class CapabilityEvidenceLedger:
    """Small append-only-ish ledger for route evidence.

    It stores metadata and hashes, never prompts, API keys, or response bodies.
    The ledger is operational evidence only; promotion remains a separate
    governed decision.
    """

    def __init__(self, state_dir: Optional[str] = None, max_entries: int = 500):
        self.state_dir = Path(state_dir) if state_dir else None
        self.max_entries = max_entries
        self.path = self.state_dir / "capability_routing_evidence.json" if self.state_dir else None
        self._data: Dict[str, Any] = {
            "schema_version": ROUTING_SCHEMA_VERSION,
            "updated_at": None,
            "capabilities": {},
        }
        self._load()

    def _load(self) -> None:
        if not self.path or not self.path.exists():
            return
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(value, dict) and isinstance(value.get("capabilities"), dict):
                self._data = value
        except (OSError, json.JSONDecodeError):
            # A corrupt evidence file must not block model work.  New records
            # start a fresh ledger and retain the unknown boundary in callers.
            return

    def _bucket(self, capability: str) -> Dict[str, Any]:
        bucket = self._data.setdefault("capabilities", {}).setdefault(
            capability,
            {
                "independent_call_evidence": [],
                "failure_recovery_evidence": [],
                "cost_records": [],
                "provider_stability": {},
                "capability_verification_receipts": [],
                "fallback_compatibility_tests": [],
            },
        )
        # Keep older ledgers forward-compatible without treating missing
        # evidence as a pass.  Every capability has the same auditable shape.
        for key in EVIDENCE_FIELDS:
            if key == "provider_stability":
                if not isinstance(bucket.get(key), dict):
                    bucket[key] = {}
            elif not isinstance(bucket.get(key), list):
                bucket[key] = []
        return bucket

    def ensure_capabilities(self, capabilities: Iterable[str]) -> None:
        """Materialize empty evidence buckets for the known capability graph.

        Empty buckets are intentional: they make ``UNOBSERVED`` explicit and
        prevent a missing key from being mistaken for a verified capability.
        """

        changed = False
        for capability in capabilities:
            name = str(capability or "").strip()
            if not name:
                continue
            before = name in self._data.setdefault("capabilities", {})
            self._bucket(name)
            changed = changed or not before
        if changed:
            self._save()

    def _save(self) -> None:
        if not self.path:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._data["updated_at"] = _now()
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            temporary.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temporary.replace(self.path)
        except OSError:
            return

    def record_call(
        self,
        *,
        task_type: str,
        capability: str,
        provider: str,
        model: str,
        success: bool,
        latency_ms: int = 0,
        usage: Optional[Mapping[str, Any]] = None,
        cost: Optional[Mapping[str, Any]] = None,
        attempts: Optional[Iterable[Mapping[str, Any]]] = None,
        route_state: str = "UNVERIFIED",
    ) -> Dict[str, Any]:
        at = _now()
        route = f"{provider}:{model}" if provider and model else model
        bucket = self._bucket(capability)
        evidence = {
            "route_id": _route_id(task_type, capability, route, at),
            "at": at,
            "task_type": task_type,
            "provider_and_model": route,
            "success": bool(success),
            "latency_ms": int(latency_ms or 0),
            "usage_known": bool(isinstance(usage, Mapping) and usage),
            "route_state": route_state,
        }
        calls = bucket["independent_call_evidence"]
        calls.append(evidence)
        del calls[:-self.max_entries]

        attempt_rows = [dict(item) for item in (attempts or []) if isinstance(item, Mapping)]
        failed_attempts = [item for item in attempt_rows if item.get("success") is not True]
        if failed_attempts:
            recovery = {
                "route_id": evidence["route_id"],
                "at": at,
                "initial_failure_count": len(failed_attempts),
                "recovered": bool(success and len(attempt_rows) > 1),
                "attempted_routes": [str(item.get("model", "")) for item in attempt_rows],
                "failure_types": [str(item.get("error", ""))[:120] for item in failed_attempts],
            }
            recoveries = bucket["failure_recovery_evidence"]
            recoveries.append(recovery)
            del recoveries[:-self.max_entries]

        cost_map = dict(cost) if isinstance(cost, Mapping) else {}
        cost_record = {
            "route_id": evidence["route_id"],
            "at": at,
            "provider_and_model": route,
            "status": "known" if isinstance(cost_map.get("total_usd"), (int, float)) else "unknown",
            "total_usd": cost_map.get("total_usd") if isinstance(cost_map.get("total_usd"), (int, float)) else None,
            "usage_source": cost_map.get("usage_source", "unknown"),
        }
        costs = bucket["cost_records"]
        costs.append(cost_record)
        del costs[:-self.max_entries]

        stability = bucket["provider_stability"].setdefault(
            route,
            {"calls": 0, "successes": 0, "failures": 0, "latency_ms_total": 0},
        )
        stability["calls"] += 1
        stability["successes"] += int(bool(success))
        stability["failures"] += int(not success)
        stability["latency_ms_total"] += int(latency_ms or 0)
        self._save()
        return evidence

    def record_verification(
        self,
        *,
        capability: str,
        provider_and_model: str,
        outcome: str,
        verifier_id: str,
        evidence_hash: str,
        independent_group_id: str,
    ) -> Dict[str, Any]:
        receipt = {
            "receipt_id": hashlib.sha256(
                f"{capability}|{provider_and_model}|{evidence_hash}|{verifier_id}".encode("utf-8")
            ).hexdigest()[:20],
            "at": _now(),
            "provider_and_model": provider_and_model,
            "outcome": outcome,
            "verifier_id": verifier_id,
            "evidence_hash": evidence_hash,
            "independent_group_id": independent_group_id,
        }
        bucket = self._bucket(capability)
        bucket["capability_verification_receipts"].append(receipt)
        del bucket["capability_verification_receipts"][:-self.max_entries]
        self._save()
        return receipt

    def record_fallback_test(
        self,
        *,
        capability: str,
        primary: str,
        fallback: str,
        compatible: bool,
        evidence_hash: str,
    ) -> Dict[str, Any]:
        item = {
            "at": _now(),
            "primary": primary,
            "fallback": fallback,
            "compatible": bool(compatible),
            "evidence_hash": evidence_hash,
        }
        bucket = self._bucket(capability)
        bucket["fallback_compatibility_tests"].append(item)
        del bucket["fallback_compatibility_tests"][:-self.max_entries]
        self._save()
        return item

    def snapshot(self) -> Dict[str, Any]:
        value = json.loads(json.dumps(self._data, ensure_ascii=False))
        for bucket in value.get("capabilities", {}).values():
            for key, rows in list(bucket.items()):
                if isinstance(rows, list) and len(rows) > 20:
                    bucket[key] = rows[-20:]
        return value

    def readiness_snapshot(self) -> Dict[str, Any]:
        """Summarize evidence completeness without granting promotion.

        A successful call proves only that one route worked once.  Promotion
        additionally needs independent capability verification, a recorded
        recovery/fallback observation, and reconciled cost evidence; those
        checks deliberately remain outside this operational ledger.
        """

        capabilities: Dict[str, Any] = {}
        for name in self._data.get("capabilities", {}):
            bucket = self._bucket(name)
            counts = {
                key: len(value) if isinstance(value, (list, dict)) else 0
                for key, value in bucket.items()
                if key in EVIDENCE_FIELDS
            }
            observed = bool(counts.get("independent_call_evidence"))
            blockers = [key for key in EVIDENCE_FIELDS if not counts.get(key)]
            if observed and not blockers:
                state = "EVIDENCE_COMPLETE_PENDING_GOVERNED_PROMOTION"
            elif observed:
                state = "POC_EVIDENCE_PARTIAL"
            else:
                state = "UNOBSERVED"
            capabilities[name] = {
                "state": state,
                "counts": counts,
                "missing_evidence": blockers,
            }
        return {
            "schema_version": ROUTING_SCHEMA_VERSION,
            "system_status": "AUTONOMOUS_CAPABILITY_ROUTING_POC_READY",
            "promotion_status": "PRODUCTION_MODEL_ROUTING_NOT_YET_PROMOTED",
            "capabilities": capabilities,
        }
