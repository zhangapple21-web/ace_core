"""Read-only, evidence-first inventory for MinerPool model residents.

This module is deliberately an observability seam.  It joins the existing
Provider Registry, task profiles, and persisted execution traces without
selecting a model, changing a profile, updating provider verification, or
calling an API.  A successful trace is usage evidence only; it can never
promote a resident into a production route.
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .resident_shelter import shelter_for

CONTRACT_VERSION = "ace.miner_pool_resident_atlas.v1"


def _resident_id(provider: object, model: object) -> str:
    provider_text = str(provider or "").strip()
    model_text = str(model or "").strip()
    return f"{provider_text}:{model_text}" if provider_text and model_text else ""


def _profile_references(profiles: Mapping[str, Any]) -> dict[str, list[str]]:
    references: dict[str, list[str]] = defaultdict(list)
    for profile_name, profile in profiles.items():
        if not isinstance(profile, Mapping):
            continue
        for field in ("preferred_models", "fallback_models"):
            values = profile.get(field, [])
            if not isinstance(values, list):
                continue
            for model_id in values:
                resident_id = str(model_id or "").strip()
                if resident_id and profile_name not in references[resident_id]:
                    references[resident_id].append(str(profile_name))
    return {resident_id: sorted(names) for resident_id, names in references.items()}


def _execution_evidence(traces: Iterable[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    evidence: dict[str, dict[str, int]] = defaultdict(
        lambda: {"attempted": 0, "successful": 0, "failed": 0}
    )
    for trace in traces:
        if not isinstance(trace, Mapping):
            continue
        resident_id = _resident_id(trace.get("provider"), trace.get("selected_model") or trace.get("model"))
        if not resident_id:
            continue
        row = evidence[resident_id]
        row["attempted"] += 1
        if trace.get("api_result") == "success":
            row["successful"] += 1
        else:
            row["failed"] += 1
    return dict(evidence)


def _registered_models(registry: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for provider in registry.get("providers", []) if isinstance(registry, Mapping) else []:
        if not isinstance(provider, Mapping):
            continue
        provider_name = str(provider.get("name") or "").strip()
        provider_status = str(provider.get("status") or "unknown").strip()
        for model in provider.get("models", []):
            if not isinstance(model, Mapping):
                continue
            resident_id = _resident_id(model.get("provider") or provider_name, model.get("model_id"))
            if resident_id:
                rows[resident_id] = {
                    "provider_status": provider_status,
                    "model_status": str(model.get("status") or "unknown").strip(),
                    "verified": bool(model.get("verified")),
                    "capabilities": sorted(str(value) for value in model.get("capabilities", []) if str(value)),
                    "meta": dict(model.get("meta", {})) if isinstance(model.get("meta"), Mapping) else {},
                }
    return rows


def _classification(registry_row: Mapping[str, Any] | None, profile_references: list[str]) -> tuple[str, str]:
    if registry_row is None:
        return (
            "UNREGISTERED_PROFILE_REFERENCE" if profile_references else "UNOBSERVED_REFERENCE",
            "EVIDENCE_REQUIRED" if profile_references else "NOT_ROUTABLE",
        )
    meta = registry_row["meta"]
    if registry_row["model_status"] == "deprecated" or registry_row["provider_status"] in {"deprecated", "inactive"}:
        return "DEPRECATED_REFERENCE", "NOT_ROUTABLE"
    if meta.get("shadow_only"):
        if registry_row["verified"]:
            return "SHADOW_EVALUATION", "SHADOW_ONLY"
        return "SHADOW_CANDIDATE", "DIALOGUE_VERIFICATION_REQUIRED"
    if registry_row["verified"] and registry_row["model_status"] == "active" and meta.get("production_eligible") is True:
        return "VERIFIED_PRODUCTION_ELIGIBLE", "EXISTING_ROUTER_POLICY"
    return "UNVERIFIED_CANDIDATE", "EVIDENCE_REQUIRED"


def build_resident_atlas(
    registry: Mapping[str, Any],
    profiles: Mapping[str, Any],
    traces: Iterable[Mapping[str, Any]],
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Return a pure, JSON-safe model roster without routing side effects."""
    registered = _registered_models(registry)
    profile_references = _profile_references(profiles)
    execution = _execution_evidence(traces)
    resident_ids = sorted(set(registered) | set(profile_references) | set(execution))
    residents = []
    for resident_id in resident_ids:
        registry_row = registered.get(resident_id)
        catalog_state, routing_eligibility = _classification(registry_row, profile_references.get(resident_id, []))
        residents.append({
            "resident_id": resident_id,
            "catalog_state": catalog_state,
            "routing_eligibility": routing_eligibility,
            "safe_room": shelter_for(catalog_state, routing_eligibility),
            "profile_references": profile_references.get(resident_id, []),
            "execution": execution.get(resident_id, {"attempted": 0, "successful": 0, "failed": 0}),
            "registry": registry_row,
            "production_integration": False,
        })
    summary = {
        "resident_count": len(residents),
        "shadow_evaluation": sum(row["catalog_state"] == "SHADOW_EVALUATION" for row in residents),
        "unregistered_profile_reference": sum(row["catalog_state"] == "UNREGISTERED_PROFILE_REFERENCE" for row in residents),
        "verified_production_eligible": sum(row["catalog_state"] == "VERIFIED_PRODUCTION_ELIGIBLE" for row in residents),
    }
    return {
        "contract_version": CONTRACT_VERSION,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "residents": residents,
        "summary": summary,
        "routing_authority": "EXISTING_MINER_POOL_ONLY",
        "production_integration": False,
    }


def _traces_from_task_pool(root: Path) -> Iterable[Mapping[str, Any]]:
    for task_path in sorted((root / "task_pool").glob("*/*.json")):
        try:
            task = json.loads(task_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        outputs = task.get("outputs", {}) if isinstance(task, Mapping) else {}
        traces = outputs.get("model_execution", []) if isinstance(outputs, Mapping) else []
        if isinstance(traces, list):
            yield from (trace for trace in traces if isinstance(trace, Mapping))


def collect_resident_atlas(root: Path) -> dict[str, Any]:
    """Read current local ledgers.  This performs no network or runtime action."""
    registry_path = root / "08_GOVERNANCE" / "provider_registry" / "registry.json"
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        registry = {"providers": []}
    from .task_profiles import TASK_PROFILES

    return build_resident_atlas(registry, TASK_PROFILES, _traces_from_task_pool(root))
