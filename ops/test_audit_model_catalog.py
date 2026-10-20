# The catalog audit must flag allowed-but-unserved refs without network.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_audit_flags_unserved_and_passes_served():
    from ops.audit_model_catalog import audit

    profiles = {
        "strategic": {
            "preferred_models": ["oneapi:gpt-5.6-terra", "oneapi:gpt-6.1-sol"],
            "fallback_models": ["glm:glm-4-flash"],
        },
    }
    catalogs = {"oneapi": {"gpt-5.6-terra", "glm-4-flash"}}
    result = audit(profiles, catalogs)
    assert [i["ref"] for i in result["unserved"]] == ["oneapi:gpt-6.1-sol"]
    assert {i["ref"] for i in result["served"]} == {"oneapi:gpt-5.6-terra"}
    assert [i["ref"] for i in result["unknown"]] == ["glm:glm-4-flash"]


def test_audit_marks_other_gateway_refs_unknown_not_unserved():
    from ops.audit_model_catalog import audit

    profiles = {
        "strategic": {
            "preferred_models": ["shenwen:gpt-5.6-terra", "oneapi:gpt-6.1-sol"],
        },
    }
    catalogs = {"oneapi": {"gpt-5.6-terra"}}
    result = audit(profiles, catalogs)
    # Cross-gateway name matches prove nothing: shenwen's serving is unknown
    # here even though the bare name exists in oneapi's catalog.
    assert [i["ref"] for i in result["unknown"]] == ["shenwen:gpt-5.6-terra"]
    assert [i["ref"] for i in result["unserved"]] == ["oneapi:gpt-6.1-sol"]


def test_audit_ignores_non_model_profile_keys():
    from ops.audit_model_catalog import audit

    profiles = {"weird": {"preferred_models": "not-a-list", "temperature": 0.5}}
    assert audit(profiles, {"oneapi": {"m"}}) == {
        "served": [], "unserved": [], "unknown": []}
