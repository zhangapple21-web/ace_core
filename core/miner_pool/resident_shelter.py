"""Bounded, descriptive safe rooms for MinerPool resident evidence states.

A safe room describes where a model may be *observed* and what kind of work
may later be proposed.  It does not route a task, invoke a provider, create a
worker, or make any claim about consciousness, autonomy, or personhood.
"""

from __future__ import annotations

from typing import Any


CONTRACT_VERSION = "ace.miner_pool_resident_shelter.v1"


def shelter_for(catalog_state: str, routing_eligibility: str) -> dict[str, Any]:
    """Map an evidence state to a non-executing safe-room contract."""
    common = {
        "contract_version": CONTRACT_VERSION,
        "automatic_model_call": False,
        "production_integration": False,
        "agency_claim": "NOT_ASSESSED",
        "intake": {
            "allowed_sources": ["declared_fixture", "sanitized_replay", "bounded_evidence_bundle"],
            "payload_retention": "HASH_OR_REDACTED_SUMMARY_ONLY",
        },
        "memory_line": {
            "retention": "APPEND_ONLY_LINEAGE",
            "deletion": "FORBIDDEN",
        },
        "pollution_route": "UNDERWORLD_QUARANTINE",
        "admission_boundary": "EGRESS_ONLY",
        "forbidden": [
            "credentials",
            "live_finance_recommendation",
            "telegram_or_client_delivery",
            "advisor_or_risk_decision",
            "automatic_task_creation",
        ],
    }
    if catalog_state == "SHADOW_EVALUATION" and routing_eligibility == "SHADOW_ONLY":
        return {
            **common,
            "room": "SHADOW_WORKSHOP",
            "allowed_material": ["sanitized_replay", "synthetic_fixture", "bounded_comparison"],
            "factory_path": ["MARK", "ISOLATED_SIMULATION", "DISTILL_OR_SMELT"],
            "outbound_rule": "INDEPENDENT_EVALUATION",
        }
    if catalog_state == "SHADOW_CANDIDATE" and routing_eligibility == "DIALOGUE_VERIFICATION_REQUIRED":
        return {
            **common,
            "room": "SHADOW_WAITING_ROOM",
            "allowed_material": ["verification_fixture", "bounded_dialogue_probe"],
            "factory_path": ["DIALOGUE_VERIFICATION", "REGISTRY_EVIDENCE"],
            "outbound_rule": "SHADOW_WORKSHOP_AFTER_VERIFICATION",
        }
    if catalog_state == "VERIFIED_PRODUCTION_ELIGIBLE" and routing_eligibility == "EXISTING_ROUTER_POLICY":
        return {
            **common,
            "room": "GOVERNED_WORKSHOP",
            "allowed_material": ["existing_admitted_task_context"],
            "factory_path": ["EXISTING_GOVERNED_WORKFLOW"],
            "outbound_rule": "EXISTING_MINER_POOL_ROUTER",
        }
    if catalog_state == "DEPRECATED_REFERENCE":
        return {
            **common,
            "room": "MUSEUM_ARCHIVE",
            "allowed_material": ["historical_trace", "migration_evidence"],
            "factory_path": ["ARCHIVE_AND_REOBSERVE"],
            "outbound_rule": "NONE",
        }
    if catalog_state == "UNREGISTERED_PROFILE_REFERENCE":
        return {
            **common,
            "room": "OBSERVATION_LOUNGE",
            "allowed_material": ["registry_reconciliation", "historical_trace"],
            "factory_path": ["REGISTRY_RECONCILIATION"],
            "outbound_rule": "PROVIDER_REGISTRY_EVIDENCE",
        }
    return {
        **common,
        "room": "QUARANTINE",
        "allowed_material": ["metadata_only"],
        "factory_path": ["QUARANTINE"],
        "outbound_rule": "NONE",
    }
