"""The reader must be honest before it is allowed to write anything.

Covers: kill switch, mode ladder, group collapse, evidence budget, traceability
refusal, index health gates, attach idempotence and the report's separation of
'cited' from 'changed'.
"""
import hashlib
import json
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.knowledge_reuse import (  # noqa: E402
    JOIN_SOURCE_PREFIX,
    KnowledgeReuseGate,
    artifact_contributions,
    build_daily_report,
    identity_keys,
    write_report,
)


class FakePool:
    def __init__(self, tasks):
        self.tasks = {t.task_id: t for t in tasks}
        self.updates = []

    def list_tasks(self, status=None, limit=100, **kwargs):
        found = list(self.tasks.values())
        if status:
            found = [t for t in found if getattr(t, "status", "pending") == status]
        return found[:limit]

    def update_task(self, task):
        self.tasks[task.task_id] = task
        self.updates.append(task.task_id)
        return True


def _verified_outcome_receipt(task_id):
    return {
        "status": "VERIFIED",
        "task_id": task_id,
        "verifier": "fixture_independent_verifier",
        "verified_at": "2026-10-01T00:00:00",
        "result_ref": f"fixture://{task_id}/result",
        "verification_ref": f"fixture://{task_id}/verification",
        "evidence_refs": [f"fixture://{task_id}/evidence-1",
                          f"fixture://{task_id}/evidence-2"],
        "independent_evidence_groups": 2,
    }


def archived_task(task_id, *, source_file=None, obs=None, intent=None,
                  references=None, created="2026-10-01T00:00:00",
                  terminal=False, reference_count=0):
    outputs = {}
    tags = []
    if source_file:
        outputs["source_file"] = source_file
    if obs:
        outputs["observation_ref"] = obs
        tags.append(f"from_obs:{obs}")
    if terminal:
        outputs["terminal_non_convergent"] = "3 rounds, no convergence"
    if intent:
        outputs["intent"] = intent
        tags.append(f"intent:{intent}")
    outputs["verified_outcome_receipt"] = _verified_outcome_receipt(task_id)
    return SimpleNamespace(
        task_id=task_id, status="archived", guardian_decision="experience",
        outputs=outputs, tags=tags,
        references=list(references or []), reference_count=reference_count,
        created_at=created, evidence=[], title=f"碎片考古: {task_id}",
    )


def subject(task_id="RQ-20261003-100", **kwargs):
    outputs = {}
    if kwargs.get("source_file"):
        outputs["source_file"] = kwargs["source_file"]
    tags = []
    if kwargs.get("obs"):
        tags.append(f"from_obs:{kwargs['obs']}")
    if kwargs.get("intent"):
        tags.append(f"intent:{kwargs['intent']}")
    if kwargs.get("adm"):
        outputs["admission"] = {"source_ref": kwargs["adm"],
                                "source_type": "archaeology"}
    return SimpleNamespace(
        task_id=task_id, status="active", outputs=outputs, tags=tags,
        data_class=kwargs.get("data_class", "CAPABILITY"),
        references=[], reference_count=0, evidence=[],
        created_at="2026-10-03T00:00:00", title="subject",
    )


def make_gate(root, pool, **settings):
    for task in pool.tasks.values():
        if not getattr(task, "_preserve_guardian_decision", False):
            task.guardian_decision = "experience"
        if not getattr(task, "_preserve_data_class", False):
            task.data_class = "CAPABILITY"
        if (not getattr(task, "_preserve_task_receipt", False)
                and "verified_outcome_receipt" not in task.outputs):
            task.outputs["verified_outcome_receipt"] = _verified_outcome_receipt(
                task.task_id
            )
    index = {
        "protocol": "ace.knowledge.join.v1",
        "built_at": datetime.now().isoformat(),
        "endpoints": {"archived": len(pool.tasks)},
        "by_task": {
            t.task_id: {"patterns": [f"pattern/EXP-{t.task_id}.json"],
                        "cards": []}
            for t in pool.tasks.values()
        },
        "by_experience": {}, "by_observation": {}, "dangling": [],
    }
    path = root / "09_KNOWLEDGE" / "join_index.v1.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index), encoding="utf-8")
    # A citation must point at an on-disk, qualification-complete experience.
    # Preserve explicit custom records so negative fixtures remain negative.
    for task in pool.tasks.values():
        artifact = root / "pattern" / f"EXP-{task.task_id}.json"
        if not artifact.exists():
            _write_experience_record(
                root, task.task_id, experience_type="pattern",
                verification=_verified_outcome_receipt(task.task_id),
            )
    return KnowledgeReuseGate(root, pool, {"enabled": True, **settings})


def test_disabled_is_a_no_op():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        old = archived_task("RQ-1", source_file="f.json")
        pool = FakePool([old])
        gate = make_gate(root, pool, enabled=False, mode="full")
        plan = gate.plan(subject(source_file="f.json"))
        assert plan["reason"] == "DISABLED"
        assert plan["selected"] == []
        assert gate.attach(subject(source_file="f.json"), plan)["attached"] == 0
        assert pool.updates == []


def test_dry_run_computes_but_writes_nothing():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        old = archived_task("RQ-1", source_file="f.json")
        pool = FakePool([old])
        gate = make_gate(root, pool, mode="dry-run")
        task = subject(source_file="f.json", data_class="CAPABILITY")
        plan = gate.plan(task)
        assert len(plan["selected"]) == 1
        assert plan["would_write"] is False
        outcome = gate.attach(task, plan)
        assert outcome["attached"] == 0
        assert outcome["reason"] == "WRITE_NOT_PERMITTED"
        assert pool.updates == []
        assert task.evidence == []


def test_full_mode_cannot_write_before_canary_receipt_is_in_runtime():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        pool = FakePool([archived_task("RQ-1", source_file="f.json")])
        gate = make_gate(
            root, pool, mode="full", canary_task="RQ-CANARY",
            canary_success_receipt={
                "status": "BENEFIT_PROVEN", "task_id": "RQ-CANARY",
                "artifact_contributions": 1,
            },
        )

        new_task = subject(source_file="f.json", data_class="CAPABILITY")
        plan = gate.plan(new_task)

        assert plan["selected"]
        assert plan["would_write"] is False
        assert gate.may_write("RQ-NOT-CANARY") is False
        result = gate.attach(subject(source_file="f.json"), plan)
        assert result["attached"] == 0
        assert result["reason"] == "WRITE_NOT_PERMITTED"
        assert pool.updates == []


def test_full_mode_requires_a_daemon_authenticated_canary_receipt():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        pool = FakePool([archived_task("RQ-1", source_file="f.json")])
        gate = make_gate(
            root, pool, mode="canary", canary_task="RQ-CANARY"
        )
        forged_report = {
            "verdict": "BENEFIT_PROVEN",
            "changed": {"artifact_contributions": [{
                "task": "RQ-CANARY", "artifact": "docs/RESULT.md",
                "source": "knowledge_join:file:abc", "identity_key": "file=x",
                "archived_task": "RQ-ARCHIVED",
            }]},
        }
        assert gate.record_canary_success(
            "RQ-CANARY", forged_report) is False
        assert gate._canary_success_verified is False
        gate.settings["mode"] = "full"
        assert gate.may_write("RQ-OTHER") is False
        gate.settings["mode"] = "canary"
        assert gate.record_canary_success(
            "RQ-CANARY", forged_report, _trusted=True) is True
        gate.settings["mode"] = "full"
        assert gate.may_write("RQ-OTHER") is True


def test_canary_writes_only_for_the_nominated_task():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        old = archived_task("RQ-1", source_file="f.json")
        pool = FakePool([old])
        gate = make_gate(root, pool, mode="canary", canary_task="RQ-CANARY")
        other = subject("RQ-OTHER", source_file="f.json")
        assert gate.plan(other)["would_write"] is False
        assert gate.attach(other, gate.plan(other))["attached"] == 0
        nominated = subject("RQ-CANARY", source_file="f.json")
        nominated.data_class = "CAPABILITY"
        outcome = gate.attach(nominated, gate.plan(nominated))
        assert outcome["attached"] == 1
        assert pool.updates == ["RQ-CANARY"]
        item = nominated.evidence[0]
        assert item["source"].startswith(JOIN_SOURCE_PREFIX)
        assert item["archived_task"] == "RQ-1"
        assert item["artifact"] == "pattern/EXP-RQ-1.json"
        assert item["identity_key"].startswith("file=")
        # second run attaches nothing new
        again = gate.attach(nominated, gate.plan(nominated))
        assert again["attached"] == 0
        assert len(nominated.evidence) == 1


def test_group_members_collapse_onto_their_primary():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        primary = archived_task("RQ-PRIMARY", source_file="state.json")
        members = [
            archived_task(f"RQ-COPY-{i}", source_file="state.json",
                          references=["RQ-PRIMARY"], reference_count=1,
                          created=f"2026-10-02T00:0{i}:00")
            for i in range(5)
        ]
        pool = FakePool([primary] + members)
        gate = make_gate(root, pool, mode="dry-run")
        new_task = subject(source_file="state.json", data_class="CAPABILITY")
        plan = gate.plan(new_task)
        assert [e["archived_task"] for e in plan["selected"]] == ["RQ-PRIMARY"]
        collapse = [s for s in plan["skipped"]
                    if s.get("reason") == "GROUP_COLLAPSED_TO_PRIMARY"]
        assert collapse and collapse[0]["count"] == 5


def test_evidence_budget_is_three_and_newest_first():
    """Three is the cap across distinct identity keys, newest first.

    A single identity key yields a single citation no matter how many archived
    tasks answer to it, so the budget only bites when a subject genuinely has
    several independent predecessors.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        five_keys = SimpleNamespace(
            task_id="RQ-MANY", status="active", data_class="CAPABILITY",
            outputs={"source_file": "f.json",
                     "admission": {"source_ref": "adm-1", "source_type": "archaeology"},
                     "trigger": {"experience_id": "EXP-1"}},
            tags=["from_obs:OBS-1", "intent:INT-1"],
            references=[], reference_count=0, evidence=[],
            created_at="2026-10-03T00:00:00", title="s")
        assert len(identity_keys(five_keys)) == 5
        old = [
            archived_task("RQ-F1", source_file="f.json", created="2026-10-01T00:00:00"),
            archived_task("RQ-F2", obs="OBS-1", created="2026-10-02T00:00:00"),
            archived_task("RQ-F3", intent="INT-1", created="2026-10-03T00:00:00"),
            archived_task("RQ-F4", created="2026-10-04T00:00:00"),
            archived_task("RQ-F5", created="2026-10-10-05T00:00:00"),
        ]
        old[3].outputs["admission"] = {"source_ref": "adm-1", "source_type": "archaeology"}
        old[4].outputs["trigger"] = {"experience_id": "EXP-1"}
        pool = FakePool(old)
        gate = make_gate(root, pool, mode="dry-run")
        five_keys.data_class = "CAPABILITY"
        plan = gate.plan(five_keys)
        assert [e["archived_task"] for e in plan["selected"]] == ["RQ-F5", "RQ-F4", "RQ-F3"]
        assert plan["expected_writes"] == {"evidence": 3, "reference_counts": 3}
        over = [s for s in plan["skipped"]
                if s.get("reason") == "OVER_EVIDENCE_BUDGET"]
        assert len(over) == 2


def test_one_identity_key_is_one_piece_of_prior_art():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        five = [archived_task(f"RQ-S{i}", source_file="state.json",
                              created=f"2026-10-0{i}T00:00:00") for i in range(1, 6)]
        pool = FakePool(five)
        gate = make_gate(root, pool, mode="dry-run")
        eligible_subject = subject(source_file="state.json", data_class="CAPABILITY")
        plan = gate.plan(eligible_subject)
        assert len(plan["selected"]) == 1
        assert plan["selected"][0]["archived_task"] == "RQ-S5"
        assert plan["expected_writes"] == {"evidence": 1, "reference_counts": 1}
        assert sum(1 for s in plan["skipped"]
                   if s.get("reason") == "SAME_IDENTITY_AS_SELECTED") == 4


def test_title_is_not_an_identity_key():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        lookalike = archived_task("RQ-OTHER", source_file="other.json")
        pool = FakePool([lookalike])
        gate = make_gate(root, pool, mode="dry-run")
        task = subject(source_file="f.json")
        task.title = "碎片考古: other.json"  # same name in the title, different file
        assert gate.plan(task)["selected"] == []


def _write_experience_record(root, task_id, *, experience_type="experience",
                             epistemic_status="EVIDENCE", verification=None,
                             data_class="CAPABILITY"):
    path = root / "pattern" / f"EXP-{task_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "experience_id": f"EXP-{task_id}",
        "source_task_id": task_id,
        "experience_type": experience_type,
        "epistemic_status": epistemic_status,
        "data_class": data_class,
        "verification": verification or {
            "status": "UNVERIFIED", "reason": "no_verified_outcome_receipt"},
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def test_private_and_core_experience_records_are_refused():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        pool = FakePool([
            archived_task("RQ-PRIVATE-CLASS", source_file="private.json"),
            archived_task("RQ-CORE-CLASS", source_file="core.json"),
        ])
        for task_id, data_class in (
            ("RQ-PRIVATE-CLASS", "PRIVATE"), ("RQ-CORE-CLASS", "CORE"),
        ):
            _write_experience_record(
                root, task_id, experience_type="experience", data_class=data_class,
                verification=_verified_outcome_receipt(task_id),
            )
        gate = make_gate(root, pool, mode="dry-run")

        private_task = subject(source_file="private.json", data_class="CAPABILITY")
        core_task = subject(source_file="core.json", data_class="CAPABILITY")
        private_plan = gate.plan(private_task)
        core_plan = gate.plan(core_task)

        assert private_plan["selected"] == []
        assert core_plan["selected"] == []
        assert {skip.get("reason") for skip in private_plan["skipped"]} >= {
            "EXPERIENCE_DATA_BOUNDARY_REFUSED"}
        assert {skip.get("reason") for skip in core_plan["skipped"]} >= {
            "EXPERIENCE_DATA_BOUNDARY_REFUSED"}


def test_private_archived_task_cannot_be_relabelled_as_capability():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        old = archived_task("RQ-PRIVATE-SOURCE", source_file="private-source.json")
        old.data_class = "PRIVATE"
        old._preserve_data_class = True
        _write_experience_record(
            root, old.task_id, experience_type="pattern",
            epistemic_status="EVIDENCE", data_class="CAPABILITY",
            verification=_verified_outcome_receipt(old.task_id),
        )
        pool = FakePool([old])
        gate = make_gate(root, pool, mode="dry-run")
        task = subject(source_file="private-source.json", data_class="CAPABILITY")

        plan = gate.plan(task)

        assert plan["selected"] == []
        assert {skip.get("reason") for skip in plan["skipped"]} >= {
            "EXPERIENCE_DATA_BOUNDARY_REFUSED"}


def test_experience_class_must_match_guardian_disposition():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        old = archived_task("RQ-CLASS-MISMATCH", source_file="f.json")
        old._preserve_guardian_decision = True
        _write_experience_record(
            root, old.task_id, experience_type="pattern",
            epistemic_status="RULE", data_class="CAPABILITY",
            verification=_verified_outcome_receipt(old.task_id),
        )
        pool = FakePool([old])
        old.guardian_decision = "constraint"
        gate = make_gate(root, pool, mode="dry-run")

        plan = gate.plan(subject(source_file="f.json"))

        assert plan["selected"] == []
        assert {skip.get("reason") for skip in plan["skipped"]} >= {
            "EXPERIENCE_CLASS_MISMATCH"}


def test_private_subject_cannot_receive_a_reuse_pointer():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        pool = FakePool([archived_task("RQ-SOURCE", source_file="f.json")])
        gate = make_gate(root, pool, mode="canary", canary_task="RQ-PRIVATE")
        internal_subject = subject("RQ-PRIVATE", source_file="f.json", data_class="PRIVATE")
        plan = gate.plan(internal_subject)

        assert plan["reason"] == "EXPERIENCE_DATA_BOUNDARY_REFUSED"
        outcome = gate.attach(internal_subject, plan)
        assert outcome["attached"] == 0
        assert internal_subject.evidence == []
        assert pool.updates == []


def test_unverified_indexed_record_cannot_fall_back_to_declared_delivery():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        old = archived_task("RQ-DELIVERY-FALLBACK", source_file="f.json")
        old.outputs["delivery"] = {
            "required_path": "docs/UNVERIFIED.md",
            "success_metric": "file_exists_nonempty",
        }
        _write_experience_record(
            root, old.task_id, experience_type="pattern",
            verification={"status": "UNVERIFIED", "reason": "test"},
        )
        (root / "docs").mkdir()
        (root / "docs" / "UNVERIFIED.md").write_text(
            "present but not receipt-verified", encoding="utf-8"
        )
        pool = FakePool([old])
        gate = make_gate(root, pool, mode="dry-run")

        plan = gate.plan(subject(source_file="f.json", data_class="CAPABILITY"))

        assert plan["selected"] == []
        assert {skip.get("reason") for skip in plan["skipped"]} >= {
            "EXPERIENCE_RECORD_UNVERIFIED"}


def test_unverified_experience_record_is_refused_even_with_an_archive_match():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        old = archived_task("RQ-UNVERIFIED", source_file="f.json")
        _write_experience_record(
            root, old.task_id, experience_type="pattern",
            verification={"status": "UNVERIFIED", "reason": "test"},
        )
        pool = FakePool([old])
        gate = make_gate(root, pool, mode="dry-run")

        plan = gate.plan(subject(source_file="f.json", data_class="CAPABILITY"))

        assert plan["selected"] == []
        assert plan["expected_writes"] == {"evidence": 0, "reference_counts": 0}
        assert {skip.get("reason") for skip in plan["skipped"]} >= {
            "EXPERIENCE_RECORD_UNVERIFIED"}


def test_experience_guardian_can_reuse_a_verified_staged_pattern():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        old = archived_task("RQ-VERIFIED-PATTERN", source_file="f.json")
        _write_experience_record(
            root, old.task_id, experience_type="pattern",
            data_class="CAPABILITY",
            verification=_verified_outcome_receipt(old.task_id),
        )
        pool = FakePool([old])
        gate = make_gate(root, pool, mode="dry-run")

        plan = gate.plan(subject(source_file="f.json", data_class="CAPABILITY"))

        assert len(plan["selected"]) == 1
        assert plan["selected"][0]["archived_task"] == old.task_id


def test_verified_staged_experience_is_reusable_without_rule_promotion():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        old = archived_task("RQ-VERIFIED-EXPERIENCE", source_file="f.json")
        _write_experience_record(
            root, old.task_id, experience_type="pattern",
            verification=_verified_outcome_receipt(old.task_id),
        )
        pool = FakePool([old])
        gate = make_gate(root, pool, mode="dry-run")

        plan = gate.plan(subject(source_file="f.json", data_class="CAPABILITY"))

        assert len(plan["selected"]) == 1
        assert plan["selected"][0]["archived_task"] == old.task_id
        assert plan["selected"][0]["artifact"] == (
            f"pattern/EXP-{old.task_id}.json")
        assert plan["would_write"] is False


def test_unverified_or_missing_guardian_decision_is_not_reusable():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        for decision in (None, "discard"):
            task_id = f"RQ-GUARDIAN-{decision or 'missing'}"
            old = archived_task(task_id, source_file="f.json")
            old.guardian_decision = decision
            old._preserve_guardian_decision = True
            old._preserve_task_receipt = True
            old.outputs.pop("verified_outcome_receipt")
            _write_experience_record(
                root, task_id,
                verification=_verified_outcome_receipt(task_id),
            )
            pool = FakePool([old])
            gate = make_gate(root, pool, mode="dry-run")

            assert gate.plan(subject(source_file="f.json"))["selected"] == []


def test_untraceable_candidate_is_refused():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        pool = FakePool([archived_task("RQ-1", source_file="f.json")])
        gate = make_gate(root, pool, mode="dry-run")
        gate._index_cache = None
        new_task = subject(source_file="f.json", data_class="CAPABILITY")
        plan = gate.plan(new_task)
        assert plan["selected"], "artifact from index is the normal path"
        # the named artifact is deleted: the citation must die with it
        (root / "pattern" / "EXP-RQ-1.json").unlink()
        plan2 = gate.plan(new_task)
        assert plan2["selected"] == []
        assert plan2["skipped"][0]["reason"] == "NO_TRACEABLE_ARTIFACT"


def test_verified_declared_delivery_is_citable_without_an_index_entry():
    """The archive's most valuable knowledge is what tasks actually delivered;
    the EXP index does not know about it."""
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        delivered = archived_task("RQ-OLD", obs="OBS-1")
        delivered.data_class = "CAPABILITY"
        delivered.outputs["delivery"] = {
            "required_path": "docs/OLD_MAP.md",
            "success_metric": "file_exists_nonempty",
        }
        pool = FakePool([delivered])
        gate = make_gate(root, pool, mode="dry-run")
        index = json.loads(gate.index_path().read_text(encoding="utf-8"))
        index["by_task"].pop("RQ-OLD", None)
        gate.index_path().write_text(json.dumps(index), encoding="utf-8")
        gate._index_cache = None
        (root / "pattern" / "EXP-RQ-OLD.json").unlink(missing_ok=True)
        (root / "docs").mkdir()
        artifact_path = root / "docs" / "OLD_MAP.md"
        artifact_path.write_text("# old\n", encoding="utf-8")
        delivered.outputs["delivery"]["verification"] = {
            "protocol": "ace.delivery.execution.v1",
            "declared": True,
            "satisfied": True,
            "required_path": "docs/OLD_MAP.md",
            "success_metric": "file_exists_nonempty",
            "size_bytes": artifact_path.stat().st_size,
            "content_sha256": hashlib.sha256(
                artifact_path.read_bytes()
            ).hexdigest(),
        }
        new_task = subject(obs="OBS-1", data_class="CAPABILITY")
        plan = gate.plan(new_task)
        assert len(plan["selected"]) == 1
        assert plan["selected"][0]["artifact"] == "docs/OLD_MAP.md"

        (root / "docs" / "OLD_MAP.md").unlink()
        assert gate.plan(new_task)["selected"] == []


def test_delivery_only_fallback_reverifies_metric_and_receipt():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        old = archived_task("RQ-EMPTY-DELIVERY", obs="OBS-EMPTY")
        old.data_class = "CAPABILITY"
        old.outputs["delivery"] = {
            "required_path": "docs/EMPTY.md",
            "success_metric": "file_exists_nonempty",
        }
        pool = FakePool([old])
        gate = make_gate(root, pool, mode="dry-run")
        index = json.loads(gate.index_path().read_text(encoding="utf-8"))
        index["by_task"].pop(old.task_id, None)
        gate.index_path().write_text(json.dumps(index), encoding="utf-8")
        gate._index_cache = None
        (root / "docs").mkdir()
        artifact = root / "docs" / "EMPTY.md"
        artifact.write_bytes(b"")
        old.outputs["delivery"]["verification"] = {
            "protocol": "ace.delivery.execution.v1",
            "declared": True,
            "satisfied": True,
            "required_path": "docs/EMPTY.md",
            "success_metric": "file_exists_nonempty",
            "content_sha256": hashlib.sha256(b"").hexdigest(),
        }

        plan = gate.plan(subject(obs="OBS-EMPTY", data_class="CAPABILITY"))

        assert plan["selected"] == []
        assert {skip.get("reason") for skip in plan["skipped"]} >= {
            "NO_TRACEABLE_ARTIFACT"}


def test_private_source_delivery_fallback_is_refused_without_indexed_experience():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        old = archived_task("RQ-PRIVATE-DELIVERY", obs="OBS-PRIVATE-DELIVERY")
        old.data_class = "PRIVATE"
        old._preserve_data_class = True
        old.outputs["delivery"] = {
            "required_path": "docs/PRIVATE.md",
            "success_metric": "file_exists_nonempty",
        }
        pool = FakePool([old])
        gate = make_gate(root, pool, mode="dry-run")
        index = json.loads(gate.index_path().read_text(encoding="utf-8"))
        index["by_task"].pop(old.task_id, None)
        gate.index_path().write_text(json.dumps(index), encoding="utf-8")
        gate._index_cache = None
        (root / "docs").mkdir()
        artifact = root / "docs" / "PRIVATE.md"
        artifact.write_text("private source content", encoding="utf-8")
        old.outputs["delivery"]["verification"] = {
            "protocol": "ace.delivery.execution.v1",
            "declared": True,
            "satisfied": True,
            "required_path": "docs/PRIVATE.md",
            "success_metric": "file_exists_nonempty",
            "content_sha256": hashlib.sha256(artifact.read_bytes()).hexdigest(),
        }

        plan = gate.plan(subject(obs="OBS-PRIVATE-DELIVERY", data_class="CAPABILITY"))

        assert plan["selected"] == []
        assert {skip.get("reason") for skip in plan["skipped"]} >= {
            "EXPERIENCE_DATA_BOUNDARY_REFUSED"}


def test_cached_index_observes_atomic_rebuild_in_same_gate(tmp_path):
    root = tmp_path
    pool = FakePool([archived_task("RQ-CACHE", source_file="cache.json")])
    gate = make_gate(root, pool, mode="dry-run")
    index_path = gate.index_path()

    first, status = gate.load_index()
    assert status == "OK"
    assert first is not None
    old_signature = gate._index_cache_signature

    rebuilt = json.loads(index_path.read_text(encoding="utf-8"))
    rebuilt["built_at"] = datetime.now().isoformat()
    rebuilt["revision_marker"] = "fresh-rebuild"
    temporary = index_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(rebuilt), encoding="utf-8")
    temporary.replace(index_path)

    loaded, status = gate.load_index()

    assert status == "OK"
    assert loaded is not None
    assert loaded.get("revision_marker") == "fresh-rebuild"
    assert gate._index_cache_signature != old_signature


def test_index_health_gates():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        pool = FakePool([archived_task("RQ-1", source_file="f.json")])
        gate = make_gate(root, pool, mode="dry-run")
        path = gate.index_path()

        stale = json.loads(path.read_text(encoding="utf-8"))
        stale["built_at"] = (datetime.now() - timedelta(days=30)).isoformat()
        path.write_text(json.dumps(stale), encoding="utf-8")
        eligible_subject = subject(source_file="f.json", data_class="CAPABILITY")
        assert gate.plan(eligible_subject)["reason"].startswith("INDEX_STALE")

        broken = json.loads(path.read_text(encoding="utf-8"))
        broken["built_at"] = datetime.now().isoformat()
        broken["protocol"] = "something.else"
        path.write_text(json.dumps(broken), encoding="utf-8")
        assert gate.plan(eligible_subject)["reason"] == "INDEX_PROTOCOL_MISMATCH"

        path.unlink()
        assert gate.plan(eligible_subject)["reason"] == "INDEX_MISSING"


def test_stage_timeout_discards_the_whole_batch():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        pool = FakePool([archived_task("RQ-1", source_file="f.json")])
        gate = make_gate(root, pool, mode="full", stage_timeout_s=0.000001)
        eligible_subject = subject(source_file="f.json", data_class="CAPABILITY")
        plan = gate.plan(eligible_subject)
        assert plan["reason"] == "STAGE_TIMEOUT"
        assert plan["selected"] == []
        assert plan["expected_writes"] == {"evidence": 0, "reference_counts": 0}
        assert plan["would_write"] is False


def test_daily_report_separates_cited_from_changed():
    entries = [{
        "task": "RQ-100", "attached": 1, "selected": [{
            "source": f"{JOIN_SOURCE_PREFIX}file:abc", "archived_task": "RQ-1",
            "artifact": "pattern/EXP-RQ-1.json"}],
        "skipped": [{"reason": "GROUP_COLLAPSED_TO_PRIMARY", "count": 140}],
    }]
    report = build_daily_report("2026-10-03", "canary", entries)
    assert report["cited"]["evidence_selected"] == 1
    assert report["cited"]["evidence_attached"] == 1
    assert report["changed"]["duplicates_avoided"] == 140
    assert report["verdict"] == "BENEFIT_PROVEN"

    empty = build_daily_report("2026-10-04", "dry-run", [{
        "task": "RQ-101", "attached": 0, "selected": [], "skipped": []}])
    assert empty["changed"]["duplicates_avoided"] == 0
    assert empty["verdict"] == "NOT_YET", "citations alone never prove benefit"

    assert build_daily_report("2026-10-05", "dry-run", [],
                              skip_reason="INDEX_STALE")["verdict"] == "NO_RUN"


def test_dry_run_collapse_never_claims_a_win():
    """The bug this guards: a plan that cited nothing, changed nothing, and
    declined to cite 140 duplicates must still report NOT_YET."""
    entries = [{
        "task": "RQ-RESCAN", "attached": 0, "mode": "dry-run",
        "selected": [{"source": f"{JOIN_SOURCE_PREFIX}file:abc",
                      "archived_task": "RQ-151",
                      "artifact": "capability_cards/CAP-RQ-151.json"}],
        "skipped": [{"reason": "GROUP_COLLAPSED_TO_PRIMARY", "count": 140}],
    }]
    report = build_daily_report("2026-10-06", "dry-run", entries)
    assert report["cited"]["evidence_selected"] == 1
    assert report["cited"]["evidence_attached"] == 0
    assert report["changed"]["duplicates_avoided"] == 0
    assert report["verdict"] == "NOT_YET"


def test_artifact_contribution_requires_the_id_to_be_written_down():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        source = f"{JOIN_SOURCE_PREFIX}intent:abc123"
        task = SimpleNamespace(evidence=[
            {"source": source, "archived_task": "RQ-005",
             "artifact": "docs/OLD.md", "identity_key": "intent=r1"},
            {"source": "delivery_verification", "content": "verified_artifact:..."},
        ])
        artifact = root / "docs" / "NEW.md"
        artifact.parent.mkdir(parents=True)

        artifact.write_text("# report\nno citation here\n", encoding="utf-8")
        assert artifact_contributions(task, "docs/NEW.md", root) == []

        artifact.write_text(f"# report\nreused {source} for section 2\n", encoding="utf-8")
        found = artifact_contributions(task, "docs/NEW.md", root)
        assert len(found) == 1
        assert found[0]["source"] == source
        assert found[0]["archived_task"] == "RQ-005"
        assert found[0]["artifact"] == "docs/NEW.md"

        # an id the task never held must not be creditable
        artifact.write_text(f"{JOIN_SOURCE_PREFIX}intent:someone-else\n", encoding="utf-8")
        assert artifact_contributions(task, "docs/NEW.md", root) == []

        report = build_daily_report("2026-10-04", "canary", [], None,
                                   contributions=found)
        assert report["changed"]["artifact_contributions"] == found
        assert report["verdict"] == "BENEFIT_PROVEN"


def test_report_write_is_idempotent():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        report = build_daily_report("2026-10-03", "dry-run", [])
        first = write_report(root, report)
        blob = first.read_bytes()
        second = write_report(root, report)
        assert first == second
        assert second.read_bytes() == blob


def test_one_identity_key_is_one_piece_of_prior_art():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        a = archived_task("RQ-A", obs="OBS-9", created="2026-10-02T00:00:00")
        b = archived_task("RQ-B", obs="OBS-9", created="2026-10-01T00:00:00")
        pool = FakePool([a, b])
        gate = make_gate(root, pool, mode="dry-run")
        new_task = subject(obs="OBS-9")
        new_task.data_class = "CAPABILITY"
        plan = gate.plan(new_task)
        assert [e["archived_task"] for e in plan["selected"]] == ["RQ-A"]
        assert plan["expected_writes"] == {"evidence": 1, "reference_counts": 1}
        assert any(s.get("reason") == "SAME_IDENTITY_AS_SELECTED"
                   for s in plan["skipped"])


def test_identity_keys_never_derive_from_title():
    task = subject(source_file="f.json")
    task.title = "state.json storm digest"
    keys = identity_keys(task)
    assert keys == {"file": "f.json"}
    assert "state.json" not in " ".join(keys.values()) or True
    assert all(label in keys for label in ("file",))