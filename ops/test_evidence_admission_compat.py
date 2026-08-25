from core.evidence_admission import evidence_signature
from core.evidence_admission_compat import (
    CURRENT_SIGNATURE_VERSION,
    shadow_report,
    signature_state,
)

def admission():
    return {
        "source_type": "system_observation",
        "source_ref": "obs-compat",
        "why_now": "A current runtime observation requires review.",
        "evidence": [{"source_ref": "obs-compat", "detail": "runtime fact"}],
        "expected_result": "A bounded conclusion.",
        "verification_method": "Re-observe the condition.",
        "risk": "Internal only.",
        "estimated_scope": "one candidate",
    }


def evidence():
    return [
        {"source": "runtime:a", "content": "A" * 60},
        {"source": "archive:b", "content": "B" * 60},
        {"source": "code:c", "content": "C" * 60},
    ]


def test_signature_states_distinguish_current_legacy_and_unavailable():
    current_evidence = evidence()
    current = {
        "evidence": current_evidence,
        "outputs": {
            "last_validated_evidence_signature": evidence_signature(current_evidence),
            "evidence_signature_version": CURRENT_SIGNATURE_VERSION,
        },
    }
    legacy = {
        "evidence": current_evidence,
        "outputs": {"last_validated_evidence_signature": "old-signature"},
    }
    unavailable = {
        "evidence": [],
        "outputs": {"evidence_signature_version": CURRENT_SIGNATURE_VERSION},
    }
    inconsistent = {
        "evidence": current_evidence,
        "outputs": {
            "last_validated_evidence_signature": "wrong",
            "evidence_signature_version": CURRENT_SIGNATURE_VERSION,
        },
    }
    assert signature_state(current) == "current"
    assert signature_state(legacy) == "legacy"
    assert signature_state(unavailable) == "unavailable"
    assert signature_state(inconsistent) == "unavailable"


def test_shadow_report_is_explicitly_non_mutating_mode():
    task = {
        "task_id": "RQ-shadow",
        "status": "pending",
        "evidence": evidence(),
        "outputs": {"admission": admission()},
    }
    before = repr(task)
    report = shadow_report([task])
    assert report["mode"] == "shadow_only"
    assert report["task_count"] == 1
    assert report["decisions"] == {"admit": 1}
    assert repr(task) == before
