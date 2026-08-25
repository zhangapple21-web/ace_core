from core.evidence_admission import evaluate_candidate, evidence_signature


def admission(source_ref="obs-1"):
    return {
        "source_type": "system_observation",
        "source_ref": source_ref,
        "why_now": "A current runtime observation requires review.",
        "evidence": [{"source_ref": source_ref, "detail": "runtime fact"}],
        "expected_result": "A bounded, evidence-backed conclusion.",
        "verification_method": "Re-observe the runtime condition.",
        "risk": "Internal maintenance only.",
        "estimated_scope": "one candidate",
    }


def evidence():
    return [
        {"source": "runtime:a", "content": "A" * 60},
        {"source": "archive:b", "content": "B" * 60},
        {"source": "code:c", "content": "C" * 60},
    ]


def test_admits_sufficient_independent_evidence_without_side_effects():
    candidate = {"admission": admission(), "evidence": evidence()}
    result = evaluate_candidate(candidate)
    assert result.decision == "admit"
    assert result.reason == "evidence_quality_satisfied"
    assert result.quality.unique_evidence_count == 3
    assert result.quality.independent_source_count == 3
    assert result.to_dict()["decision"] == "admit"


def test_defers_missing_admission_before_quality_is_considered():
    result = evaluate_candidate({"evidence": evidence()})
    assert result.decision == "defer"
    assert result.reason == "task_admission_required"
    assert result.admission_valid is False


def test_defers_single_source_evidence():
    candidate = {
        "admission": admission(),
        "evidence": [
            {"source": "same", "content": "A" * 80},
            {"source": "same", "content": "B" * 80},
            {"source": "same", "content": "C" * 80},
        ],
    }
    result = evaluate_candidate(candidate)
    assert result.decision == "defer"
    assert result.reason == "independent_evidence_required"


def test_duplicate_signature_is_reported_before_new_admission():
    candidate = {"admission": admission("obs-new"), "evidence": evidence()}
    existing = {
        "task_id": "RQ-existing",
        "status": "pending",
        "evidence": evidence(),
        "outputs": {},
    }
    result = evaluate_candidate(candidate, [existing])
    assert result.decision == "duplicate"
    assert result.reason == "duplicate_evidence_signature"
    assert result.duplicate_task_ids == ("RQ-existing",)
    assert result.evidence_signature == evidence_signature(evidence())


def test_terminal_duplicate_does_not_block_new_candidate():
    candidate = {"admission": admission("obs-new"), "evidence": evidence()}
    terminal = {
        "task_id": "RQ-archived",
        "status": "archived",
        "evidence": evidence(),
        "outputs": {},
    }
    result = evaluate_candidate(candidate, [terminal])
    assert result.decision == "admit"


def test_evaluator_does_not_make_model_admission_decision():
    candidate = {
        "admission": admission(),
        "evidence": evidence(),
        "model_task_admission": {"eligible": False, "classification": "local_evidence_only"},
    }
    result = evaluate_candidate(candidate)
    assert result.decision == "admit"
    assert result.admission_valid is True


def test_empty_evidence_sets_are_not_duplicates_of_each_other():
    candidate = {"admission": admission("obs-new"), "evidence": []}
    existing = {
        "task_id": "RQ-empty",
        "status": "pending",
        "evidence": [],
        "outputs": {},
    }
    result = evaluate_candidate(candidate, [existing])
    assert result.decision == "defer"
    assert result.reason == "minimum_evidence_required"
    assert result.evidence_signature == ""
    assert result.duplicate_task_ids == ()
