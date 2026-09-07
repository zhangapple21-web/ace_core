from ace_daemon import AceDaemon
from core.outcome_receipt import OutcomeReceiptRecorder
from core.policy_feedback import PolicyCardStore
from core.task import Task, TaskPool
from core.task_roles import Researcher


def _task():
    return Task(
        task_id="RQ-POLICY-1",
        title="Provider recovery verification",
        hypothesis="Retrying the provider after a bounded outage restores service.",
        tags=["provider", "recovery"],
        evidence=[
            {"source": "fixture://source-a"},
            {"source": "fixture://source-b"},
        ],
        result={"finding": "recovery confirmed"},
    )


def _verify(task):
    return OutcomeReceiptRecorder().verify(
        task,
        result_ref="fixture://result",
        verification_ref="fixture://verification",
        evidence_refs=["fixture://source-a", "fixture://source-b"],
        independent_evidence_groups=2,
        verifier="independent_rechecker",
        verified_at="2026-09-03T12:00:00",
    )


def test_projects_verified_outcome_into_idempotent_policy_card(tmp_path):
    task = _task()
    _verify(task)
    store = PolicyCardStore(tmp_path)

    first = store.project(task)
    second = store.project(task)

    assert first["status"] == "active"
    assert first["source_receipt"] == "RQ-POLICY-1"
    assert first["action"] == "research:provider recovery verification"
    assert first["evidence_refs"] == ["fixture://source-a", "fixture://source-b"]
    assert second["card_id"] == first["card_id"]
    assert len(store.list_cards()) == 1


def test_rejects_pending_or_incomplete_receipts(tmp_path):
    task = _task()
    store = PolicyCardStore(tmp_path)

    assert store.project(task) is None

    task.outputs["verified_outcome_receipt"] = {
        "status": "VERIFIED",
        "evidence_refs": ["fixture://source-a"],
        "independent_evidence_groups": 1,
    }

    assert store.project(task) is None
    assert store.list_cards() == []


def test_rejects_receipt_bound_to_a_different_task(tmp_path):
    task = _task()
    _verify(task)
    task.outputs["verified_outcome_receipt"]["task_id"] = "RQ-OTHER"
    store = PolicyCardStore(tmp_path)

    assert store.project(task) is None
    assert store.list_cards() == []


def test_ranks_matching_candidates_with_policy_provenance(tmp_path):
    source_task = _task()
    _verify(source_task)
    store = PolicyCardStore(tmp_path)
    card = store.project(source_task)
    target_task = Task(
        task_id="RQ-POLICY-2",
        title="Provider recovery follow-up",
        hypothesis="Check provider recovery behavior.",
        tags=["provider", "recovery"],
    )
    candidates = [
        {"candidate_id": "A", "hypothesis": "Provider recovery investigation", "keywords": ["provider"], "confidence": 0.8},
        {"candidate_id": "B", "hypothesis": "Lexicon expansion", "keywords": ["lexicon"], "confidence": 0.9},
    ]

    ranked = store.rank_candidates(target_task, candidates)

    assert [candidate["candidate_id"] for candidate in ranked] == ["A", "B"]
    assert ranked[0]["policy_feedback"][0]["card_id"] == card["card_id"]
    assert ranked[0]["confidence"] == 0.9
    assert "policy_feedback" not in ranked[1]


def test_ranks_chinese_context_with_policy_provenance(tmp_path):
    source_task = Task(
        task_id="RQ-POLICY-CN-1",
        title="供应商恢复验证",
        hypothesis="受限中断后重试供应商可恢复服务。",
        tags=["供应商", "恢复"],
        result={"finding": "恢复确认"},
    )
    _verify(source_task)
    store = PolicyCardStore(tmp_path)
    card = store.project(source_task)
    target_task = Task(
        task_id="RQ-POLICY-CN-2",
        title="供应商恢复跟进",
        hypothesis="检查供应商恢复行为。",
        tags=["供应商", "恢复"],
    )

    ranked = store.rank_candidates(
        target_task,
        [
            {"candidate_id": "A", "hypothesis": "供应商恢复调查", "keywords": ["供应商"], "confidence": 0.8},
            {"candidate_id": "B", "hypothesis": "词库扩展", "keywords": ["词库"], "confidence": 0.9},
        ],
    )

    assert [candidate["candidate_id"] for candidate in ranked] == ["A", "B"]
    assert ranked[0]["policy_feedback"][0]["card_id"] == card["card_id"]


def test_researcher_applies_policy_ranking_after_candidate_generation(tmp_path):
    source_task = _task()
    _verify(source_task)
    store = PolicyCardStore(tmp_path)
    card = store.project(source_task)
    target_task = Task(
        task_id="RQ-POLICY-3",
        title="Provider recovery follow-up",
        hypothesis="Check provider recovery behavior.",
        tags=["provider", "recovery"],
    )
    researcher = Researcher(TaskPool(str(tmp_path / "tasks")), policy_card_store=store)

    candidates = researcher.generate_candidates(target_task)

    assert candidates[0]["candidate_id"] == "A"
    assert candidates[0]["policy_feedback"][0]["card_id"] == card["card_id"]


def test_daemon_projects_only_verified_task_receipts(tmp_path):
    daemon = AceDaemon.__new__(AceDaemon)
    daemon.task_pool = TaskPool(str(tmp_path / "tasks"))
    daemon.policy_card_store = PolicyCardStore(tmp_path / "policy")
    verified_task = _task()
    pending_task = _task()
    pending_task.task_id = "RQ-POLICY-PENDING"
    _verify(verified_task)
    daemon.task_pool._save_task(verified_task)
    daemon.task_pool._save_task(pending_task)

    projected = daemon._project_verified_policy_cards()

    assert projected == 1
    assert len(daemon.policy_card_store.list_cards()) == 1
    assert daemon._project_verified_policy_cards() == 0



