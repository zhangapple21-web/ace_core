"""Epistemic gate on the canonical Knowledge store.

The invariant under test: an execution result may not become a long-term rule
(axiom / constraint) without an independent verification receipt.  Without this,
one archived task's own evidence count was enough to write a rule that every
later agent would then treat as a fact.
"""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.experience_deposition import (  # noqa: E402
    EPISTEMIC_STATUS,
    LONG_TERM_TYPES,
    MAX_UNVERIFIED_TYPE,
    ExperienceDeposition,
)
from core.outcome_receipt import OutcomeReceiptRecorder  # noqa: E402


def task(task_id, conclusion="a conclusion", decision="axiom", receipt=None):
    outputs = {} if receipt is None else {"verified_outcome_receipt": receipt}
    return SimpleNamespace(
        task_id=task_id,
        guardian_decision=decision,
        hypothesis=conclusion,
        title=f"Task {task_id}",
        evidence=[{"source": f"fixture://{task_id}", "content": "a measured reading"}],
        tags=["test"],
        outputs=outputs,
    )


def verified_receipt(groups=2, refs=2):
    return OutcomeReceiptRecorder().verify(
        task("RQ-verify"),
        result_ref="fixture://result",
        verification_ref="fixture://verify",
        evidence_refs=[f"fixture://e{i}" for i in range(refs)],
        independent_evidence_groups=groups,
        verifier="fixture_verifier",
    )


def test_epistemic_status_is_declared_for_every_type():
    assert set(EPISTEMIC_STATUS) == {"axiom", "constraint", "pattern", "lesson", "observation"}
    assert EPISTEMIC_STATUS["axiom"] == "VERIFIED_FACT"
    assert EPISTEMIC_STATUS["constraint"] == "RULE"
    assert EPISTEMIC_STATUS["pattern"] == "EVIDENCE"
    assert EPISTEMIC_STATUS["observation"] == "OBSERVATION"


def test_unverified_long_term_grade_is_downgraded_and_the_reason_recorded(tmp_path):
    deposition = ExperienceDeposition(str(tmp_path))

    for requested in LONG_TERM_TYPES:
        conclusion = f"unverified {requested} claim"
        experience = deposition.deposit(
            task(f"RQ-unverified-{requested}", conclusion=conclusion),
            requested,
            conclusion=conclusion,
        )
        assert experience.experience_type == MAX_UNVERIFIED_TYPE
        assert experience.epistemic_status == EPISTEMIC_STATUS[MAX_UNVERIFIED_TYPE]
        assert experience.downgrade_reason.startswith(f"downgraded_from_{requested}")
        assert experience.verification["status"] == "UNVERIFIED"


def test_unverified_record_never_reaches_a_long_term_tier(tmp_path):
    deposition = ExperienceDeposition(str(tmp_path))

    experience = deposition.deposit(
        task("RQ-pollution", conclusion="the dashboard is permanently broken"),
        "axiom",
        conclusion="the dashboard is permanently broken",
    )

    for tier in LONG_TERM_TYPES:
        directory = tmp_path / tier
        assert not directory.exists() or not list(directory.glob("EXP-*.json"))
    assert experience.experience_type == "pattern"
    index = json.loads((tmp_path / "index.json").read_text(encoding="utf-8"))
    assert index[experience.experience_id]["type"] == "pattern"
    assert index[experience.experience_id]["epistemic_status"] == "EVIDENCE"


def test_verified_work_may_still_reach_a_long_term_tier(tmp_path):
    deposition = ExperienceDeposition(str(tmp_path))
    conclusion = "independently verified boundary"

    experience = deposition.deposit(
        task("RQ-verified", conclusion=conclusion, receipt=verified_receipt()),
        "constraint",
        conclusion=conclusion,
    )

    assert experience.experience_type == "constraint"
    assert experience.epistemic_status == "RULE"
    assert experience.verification["status"] == "VERIFIED"
    assert experience.verification["independent_evidence_groups"] == 2
    assert experience.downgrade_reason == ""
    assert (tmp_path / "constraint" / f"{experience.experience_id}.json").is_file()


def test_single_source_verification_is_not_enough(tmp_path):
    """Defense in depth against a hand-written or legacy weak receipt.

    ``OutcomeReceiptRecorder.verify`` refuses to mint such a receipt, so this
    state can only arrive from outside the recorder.  The deposition gate must
    not trust the ``VERIFIED`` string alone.
    """
    deposition = ExperienceDeposition(str(tmp_path))
    weak_receipt = {
        "schema_version": 1,
        "status": "VERIFIED",
        "task_id": "RQ-weak",
        "verifier": "unverified_operator",
        "result_ref": "fixture://result",
        "verification_ref": "fixture://verify",
        "evidence_refs": ["fixture://e0"],
        "independent_evidence_groups": 1,
    }

    experience = deposition.deposit(
        task("RQ-weak", conclusion="one source is not independent verification",
             receipt=weak_receipt),
        "axiom",
        conclusion="one source is not independent verification",
    )

    assert experience.experience_type == "pattern"
    assert experience.verification["reason"] == "independent_evidence_required"
    assert experience.downgrade_reason == "downgraded_from_axiom:independent_evidence_required"


def test_reuse_is_persisted_so_a_later_reader_can_prove_it(tmp_path):
    deposition = ExperienceDeposition(str(tmp_path))
    lesson = deposition.deposit(
        task("RQ-lesson", decision="discard"),
        "lesson",
        conclusion="an earlier failed approach must not be repeated",
    )
    assert lesson.reference_count == 0

    consulted = deposition.find_related(
        "an earlier failed approach must not be repeated", limit=3)

    assert [item.experience_id for item in consulted] == [lesson.experience_id]
    on_disk = json.loads(
        (tmp_path / "lesson" / f"{lesson.experience_id}.json").read_text(encoding="utf-8")
    )
    assert on_disk["reference_count"] == 1