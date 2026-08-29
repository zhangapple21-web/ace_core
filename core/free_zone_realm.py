"""Portable artifact-state labels for the R1 five-realm relationship.

This is intentionally descriptive data, not a runtime, router, scheduler,
permission system, or promotion engine.  It gives a sandbox artifact a clear
home and a bounded next edge while keeping free-zone intake open.
"""

from __future__ import annotations

from typing import Any


CONTRACT_VERSION = "ace.free_zone_realm.v1"


def _state(realm: str, authority: str, retention: str, outbound_rule: str) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "realm": realm,
        "authority": authority,
        "retention": retention,
        "outbound_rule": outbound_rule,
        "production_integration": False,
    }


def state_for(
    artifact_kind: str,
    *,
    source_kind: str = "unknown",
    distillation_status: str | None = None,
    polluted: bool = False,
) -> dict[str, Any]:
    """Return a deterministic realm state without performing any transition.

    ``REALITY`` deliberately has no producer here.  A free-zone artifact may
    only point to the existing governed Admission as an outbound possibility;
    it can never label itself a real-world/production artifact.
    """
    if polluted or distillation_status == "QUARANTINED":
        return _state("UNDERWORLD", "SANDBOX_ONLY", "ARCHIVED", "NONE")
    if artifact_kind == "inbound":
        retention = "LINE" if source_kind in {"semantic_seed_unstructured", "inbox"} else "SEED"
        return _state("FREE", "SANDBOX_ONLY", retention, "REOBSERVE")
    if artifact_kind == "factory_thread":
        return _state("FREE", "SANDBOX_ONLY", "SEED", "REOBSERVE")
    if artifact_kind == "factory_mark":
        return _state("SHADOW", "SANDBOX_ONLY", "ACTIVE", "NONE")
    if artifact_kind == "world_blueprint":
        return _state("INTERNAL", "SANDBOX_ONLY", "ACTIVE", "NONE")
    if artifact_kind in {"experiment", "processing_receipt", "smelter_receipt"}:
        return _state("SHADOW", "SANDBOX_ONLY", "ACTIVE", "NONE")
    if artifact_kind == "distillation":
        if distillation_status == "PROPOSAL_ONLY":
            return _state("SHADOW", "GOVERNED", "SEED", "EXISTING_ADMISSION")
        return _state("SHADOW", "SANDBOX_ONLY", "SEED", "REOBSERVE")
    if artifact_kind == "courier_receipt":
        return _state("SHADOW", "SANDBOX_ONLY", "ARCHIVED", "REOBSERVE")
    raise ValueError(f"unsupported free-zone artifact kind: {artifact_kind}")
