"""Acceptance for the governance <-> reuse merge on one production AceDaemon.

Covers exactly what the alignment order asks to be provable, and nothing that
the two existing modules already prove on their own:

* the Governor is injected before the reuse gate and both share one TaskPool;
* a task matched by identity key receives one ``knowledge_join`` record naming
  the graded knowledge record;
* a delivered artifact that cites that id is booked as a contribution;
* the reuse pointer cannot raise the evidence count or re-enter the gate;
* the Governor's ``reference_count`` stays governance-owned.

The wiring-inert behaviour of the gate stays in
``ops/test_knowledge_reuse_daemon_stage.py``; the reader's own selection rules
stay in ``ops/test_knowledge_reuse.py``.
"""
import json
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ace_daemon import AceDaemon  # noqa: E402
from core.experience_deposition import ExperienceDeposition  # noqa: E402
from core.knowledge_reuse import artifact_contributions  # noqa: E402
from core.outcome_receipt import OutcomeReceiptRecorder  # noqa: E402
from core.task import TaskPool  # noqa: E402
from core.task_roles import Validator, _is_reuse_pointer  # noqa: E402

SETTINGS = {
    "runtime": {
        "knowledge_reuse": {
            "enabled": True,
            "mode": "canary",
            "canary_task": None,
            "budget_evidence_per_task": 3,
            "index_path": "09_KNOWLEDGE/join_index.v1.json",
            "report_dir": "06_RUNTIME/ace/data/knowledge_reuse",
        },
        "allow_repository_sync": False,
        "allow_external_learning": False,
    },
    "data": {"memory_cache_dir": "06_RUNTIME/ace/data/memory"},
}


def _admission(ref, kind="archaeology"):
    return {
        "source_type": kind,
        "source_ref": ref,
        "why_now": "merge acceptance",
        "evidence": [{"source": ref, "content": "measured input",
                      "risk": "low", "source_ref": ref}],
        "expected_result": "bounded result",
        "verification_method": "re-read the delivered file",
        "risk": "read-only",
        "estimated_scope": "one file",
    }


def _root(tmp: str) -> Path:
    root = Path(tmp)
    for sub in ("06_RUNTIME/ace/data/memory", "09_KNOWLEDGE", "08_GOVERNANCE"):
        (root / sub).mkdir(parents=True, exist_ok=True)
    return root


def _posix(path) -> str:
    """The join index records forward-slashed paths; compare on that form."""
    return str(path).replace("\\", "/")


def _seeded_rule(daemon: AceDaemon):
    """Archive one task and let the Governor grade it as a RULE."""
    pool = daemon.task_pool
    prior = pool.create_task(
        "prior boundary", hypothesis="archived conclusion worth reusing",
        creator="merge", priority="high", tags=["archaeology"],
        admission=_admission("merge://prior"),
        outputs={"source_file": "merge://prior-source"},
    )
    pool.move_task(prior.task_id, "active", actor="merge")
    pool.move_task(prior.task_id, "review", actor="merge")
    pool.move_task(prior.task_id, "approved", actor="merge")
    prior = pool.load_task(prior.task_id)
    prior.guardian_decision = "experience"
    pool.update_task(prior)
    pool.move_task(prior.task_id, "archived", actor="merge")

    prior = pool.load_task(prior.task_id)
    prior.outputs = dict(prior.outputs or {})
    prior.outputs["verified_outcome_receipt"] = OutcomeReceiptRecorder().verify(
        prior,
        result_ref="merge://prior/result.json",
        verification_ref="merge://prior/verify.json",
        evidence_refs=["merge://prior/e0", "merge://prior/e1", "merge://prior/e2"],
        independent_evidence_groups=2,
        verifier="merge_independent_verifier",
    )
    pool.update_task(prior)

    graded = daemon.experience_deposition.deposit(
        pool.load_task(prior.task_id), "constraint",
        conclusion="archived conclusion worth reusing",
    )
    record = (daemon.base_dir / "09_KNOWLEDGE" / "constraint"
              / f"{graded.experience_id}.json")
    (daemon.base_dir / "09_KNOWLEDGE" / "join_index.v1.json").write_text(
        json.dumps({
            "protocol": "ace.knowledge.join.v1",
            "built_at": datetime.now().isoformat(),
            "by_task": {prior.task_id: {"patterns": [str(record)], "cards": []}},
            "by_experience": {graded.experience_id: [str(record)]},
            "by_observation": {},
            "dangling": [],
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    daemon.knowledge_reuse._index_cache = None
    daemon.knowledge_reuse._archive_cache = None
    return prior, graded, record


def test_governor_is_injected_before_the_reuse_gate_and_shares_one_pool(tmp_path):
    root = _root(str(tmp_path))
    daemon = AceDaemon(root, SETTINGS)

    assert daemon.knowledge_governor.ace_runtime_dir == root.resolve()
    assert daemon.knowledge_reuse.task_pool is daemon.task_pool
    # Researcher's experience_deposition stays None on purpose: archived-knowledge
    # reuse has exactly one owner, and a second reader would be a parallel path.
    assert daemon.researcher.experience_deposition is None


def test_intent_task_matches_the_graded_record_and_records_a_join(tmp_path):
    root = _root(str(tmp_path))
    daemon = AceDaemon(root, SETTINGS)
    prior, graded, record = _seeded_rule(daemon)

    assert graded.experience_type == "constraint"
    assert graded.epistemic_status == "RULE"
    assert record.is_file()

    subject = daemon.task_pool.create_task(
        "intent: apply the archived boundary",
        hypothesis="apply the archived boundary to the new material",
        creator="intent", priority="high", tags=["intent"],
        admission=_admission("merge://prior-source"),
        outputs={
            "source_file": "merge://prior-source",
            "delivery": {
                "required_path": "docs/REUSE_PROOF.md",
                "success_metric": "file_exists_nonempty",
                "domain": "analysis",
            },
        },
    )
    daemon.knowledge_reuse.settings["canary_task"] = subject.task_id

    entry = daemon._run_knowledge_reuse_stage(
        daemon.task_pool.load_task(subject.task_id), {})

    assert entry["mode"] == "canary"
    assert entry["attached"] == 1
    assert entry["selected"][0]["source"].startswith("knowledge_join:")
    assert entry["selected"][0]["artifact"] == _posix(record)
    assert entry["selected"][0]["archived_task"] == prior.task_id

    live = daemon.task_pool.load_task(subject.task_id)
    joined = [e for e in live.evidence if str(e.get("source", "")).startswith("knowledge_join:")]
    assert len(joined) == 1

    deliverable = root / "docs" / "REUSE_PROOF.md"
    deliverable.parent.mkdir(parents=True, exist_ok=True)
    deliverable.write_text(
        "# reuse proof\n\nApplied the archived boundary.\n"
        f"Source: {joined[0]['source']}\n", encoding="utf-8")

    contributions = artifact_contributions(live, "docs/REUSE_PROOF.md", root)
    assert len(contributions) == 1
    assert contributions[0]["archived_task"] == prior.task_id
    assert contributions[0]["cited_artifact"] == _posix(record)

    daemon._knowledge_reuse_contributions.extend(contributions)
    report = json.loads(Path(daemon._write_knowledge_reuse_report({})).read_text(encoding="utf-8"))
    assert report["verdict"] == "BENEFIT_PROVEN"
    assert len(report["changed"]["artifact_contributions"]) == 1


def test_reuse_pointer_is_not_corroboration_and_cannot_reach_a_rule(tmp_path):
    root = _root(str(tmp_path))
    daemon = AceDaemon(root, SETTINGS)
    _prior, graded, _record = _seeded_rule(daemon)

    subject = daemon.task_pool.create_task(
        "intent: subject", hypothesis="apply the archived boundary",
        creator="intent", priority="high", tags=["intent"],
        admission=_admission("merge://prior-source"),
        outputs={"source_file": "merge://prior-source"},
    )
    daemon.knowledge_reuse.settings["canary_task"] = subject.task_id
    daemon._run_knowledge_reuse_stage(daemon.task_pool.load_task(subject.task_id), {})

    live = daemon.task_pool.load_task(subject.task_id)
    joined = [e for e in live.evidence if str(e.get("source", "")).startswith("knowledge_join:")]
    assert joined and all(_is_reuse_pointer(e) for e in joined)
    # A pointer at ACE's own memory must never stand in for a second source.
    assert len(Validator._unique_evidence(live)) == 0

    before = daemon.experience_deposition.get_stats()
    poison = daemon.task_pool.create_task(
        "reuse is not proof", hypothesis="reuse pointer is not proof of a new rule",
        creator="merge", priority="high", tags=["merge"],
        admission=_admission("merge://pollution", kind="system_observation"),
    )
    promoted = daemon.experience_deposition.deposit(
        daemon.task_pool.load_task(poison.task_id), "axiom",
        conclusion="reuse pointer is not proof of a new rule",
    )
    after = daemon.experience_deposition.get_stats()

    assert promoted.experience_type == "pattern"
    assert promoted.epistemic_status == "EVIDENCE"
    assert after["by_type"]["constraint"] == before["by_type"]["constraint"]

    on_disk = ExperienceDeposition(str(root / "09_KNOWLEDGE"))._load_experience(
        root / "09_KNOWLEDGE" / "constraint" / f"{graded.experience_id}.json")
    # Reuse is not a reuse of the record: only the governance writer may count it.
    assert on_disk.reference_count == 0


def test_dry_run_plans_the_same_match_and_writes_nothing(tmp_path):
    root = _root(str(tmp_path))
    daemon = AceDaemon(root, SETTINGS)
    _seeded_rule(daemon)
    daemon.knowledge_reuse.settings["mode"] = "dry-run"
    daemon.knowledge_reuse.settings["canary_task"] = None

    subject = daemon.task_pool.create_task(
        "intent: dry-run subject", hypothesis="dry run must be inert",
        creator="intent", priority="high", tags=["intent"],
        admission=_admission("merge://prior-source", kind="system_observation"),
        outputs={"source_file": "merge://prior-source"},
    )

    entry = daemon._run_knowledge_reuse_stage(
        daemon.task_pool.load_task(subject.task_id), {})

    assert entry["mode"] == "dry-run"
    assert len(entry["selected"]) == 1          # the match is still computed
    assert entry["attached"] == 0              # but nothing is written
    assert entry["attach_reason"] == "DRY_RUN"
    assert not daemon.task_pool.load_task(subject.task_id).evidence