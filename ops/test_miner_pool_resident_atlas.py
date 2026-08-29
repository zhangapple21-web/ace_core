import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.miner_pool.resident_atlas import build_resident_atlas


def test_atlas_keeps_registry_profile_and_execution_evidence_separate():
    registry = {
        "providers": [
            {
                "name": "shenwen_grok",
                "status": "active",
                "models": [
                    {
                        "provider": "shenwen_grok",
                        "model_id": "grok-4.6",
                        "status": "beta",
                        "verified": True,
                        "capabilities": ["research"],
                        "meta": {"shadow_only": True, "production_eligible": False},
                    }
                ],
            }
        ]
    }
    profiles = {
        "strategic": {"preferred_models": ["shenwen:gpt-5.6-terra"]},
        "grok_shadow": {"shadow_only": True, "preferred_models": ["shenwen_grok:grok-4.6"]},
    }
    traces = [
        {"provider": "shenwen_grok", "selected_model": "grok-4.6", "api_result": "success"},
        {"provider": "shenwen", "selected_model": "gpt-5.6-terra", "api_result": "failed"},
    ]

    atlas = build_resident_atlas(registry, profiles, traces, generated_at="2026-08-27T12:00:00Z")
    by_id = {row["resident_id"]: row for row in atlas["residents"]}

    grok = by_id["shenwen_grok:grok-4.6"]
    assert grok["catalog_state"] == "SHADOW_EVALUATION"
    assert grok["routing_eligibility"] == "SHADOW_ONLY"
    assert grok["safe_room"]["room"] == "SHADOW_WORKSHOP"
    assert grok["safe_room"]["automatic_model_call"] is False
    assert grok["safe_room"]["outbound_rule"] == "INDEPENDENT_EVALUATION"
    assert grok["safe_room"]["intake"]["payload_retention"] == "HASH_OR_REDACTED_SUMMARY_ONLY"
    assert grok["safe_room"]["factory_path"] == ["MARK", "ISOLATED_SIMULATION", "DISTILL_OR_SMELT"]
    assert grok["safe_room"]["memory_line"]["deletion"] == "FORBIDDEN"
    assert grok["safe_room"]["pollution_route"] == "UNDERWORLD_QUARANTINE"
    assert grok["execution"] == {"attempted": 1, "successful": 1, "failed": 0}
    assert grok["profile_references"] == ["grok_shadow"]

    terra = by_id["shenwen:gpt-5.6-terra"]
    assert terra["catalog_state"] == "UNREGISTERED_PROFILE_REFERENCE"
    assert terra["routing_eligibility"] == "EVIDENCE_REQUIRED"
    assert terra["safe_room"]["room"] == "OBSERVATION_LOUNGE"
    assert terra["safe_room"]["automatic_model_call"] is False
    assert terra["safe_room"]["factory_path"] == ["REGISTRY_RECONCILIATION"]
    assert terra["execution"] == {"attempted": 1, "successful": 0, "failed": 1}
    assert atlas["summary"] == {
        "resident_count": 2,
        "shadow_evaluation": 1,
        "unregistered_profile_reference": 1,
        "verified_production_eligible": 0,
    }


def test_atlas_never_promotes_execution_success_or_deprecated_history():
    registry = {
        "providers": [
            {
                "name": "openrouter",
                "status": "inactive",
                "models": [
                    {
                        "provider": "openrouter",
                        "model_id": "x-ai/grok-4.6",
                        "status": "deprecated",
                        "verified": True,
                        "meta": {"production_eligible": True},
                    }
                ],
            }
        ]
    }
    atlas = build_resident_atlas(
        registry,
        {"research": {"preferred_models": ["openrouter:x-ai/grok-4.6"]}},
        [{"provider": "openrouter", "model": "x-ai/grok-4.6", "api_result": "success"}],
    )

    resident = atlas["residents"][0]
    assert resident["catalog_state"] == "DEPRECATED_REFERENCE"
    assert resident["routing_eligibility"] == "NOT_ROUTABLE"
    assert resident["safe_room"]["room"] == "MUSEUM_ARCHIVE"
    assert resident["safe_room"]["automatic_model_call"] is False
    assert resident["safe_room"]["memory_line"]["deletion"] == "FORBIDDEN"
    assert resident["execution"]["successful"] == 1
    assert resident["production_integration"] is False


def test_unverified_shadow_candidate_waits_for_real_dialogue_verification():
    atlas = build_resident_atlas(
        {
            "providers": [{
                "name": "shenwen_grok",
                "status": "active",
                "models": [{
                    "provider": "shenwen_grok",
                    "model_id": "grok-4.5",
                    "status": "beta",
                    "verified": False,
                    "meta": {"shadow_only": True, "production_eligible": False},
                }],
            }]
        },
        {"grok_coding_shadow": {"shadow_only": True, "preferred_models": ["shenwen_grok:grok-4.5"]}},
        [],
    )

    resident = atlas["residents"][0]
    assert resident["catalog_state"] == "SHADOW_CANDIDATE"
    assert resident["routing_eligibility"] == "DIALOGUE_VERIFICATION_REQUIRED"
    assert resident["safe_room"]["room"] == "SHADOW_WAITING_ROOM"
    assert resident["safe_room"]["automatic_model_call"] is False
