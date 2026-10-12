"""Tests for the free-zone external reviewer.

The point under test is not "do the models answer" — it is the boundary. These
tasks are blocked waiting for *external* evidence, so the only thing that matters
is whether ACE has built a path where an unrelated model can say something
without ACE treating it as a fact.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.free_zone_external_reviewer import (  # noqa: E402
    CONTRACT_VERSION,
    EXTERNAL_EVIDENCE_MARKER,
    REVIEWERS,
    FreeZoneExternalReviewer,
)


def _blocked_task(tmp_path, task_id="RQ-TEST-001", waiting=True):
    directory = tmp_path / "task_pool" / "blocked"
    directory.mkdir(parents=True, exist_ok=True)
    reason = (
        "相同证据集重复验证达到上限，" + EXTERNAL_EVIDENCE_MARKER
        if waiting else "blocked for another reason entirely"
    )
    (directory / f"{task_id}.json").write_text(json.dumps({
        "task_id": task_id,
        "title": "验证一个无法自行收敛的命题",
        "hypothesis": "The widening of allowed providers needs an owner ruling.",
        "status": "blocked",
        "blocked_reason": reason,
        "evidence": [
            {"source": "runtime_observation:OBS-1", "content": "first evidence record"},
            {"source": "archivist:abc123", "content": "second evidence record"},
        ],
        "counter_examples": [{"content": "only two evidence items, insufficient", "source": "validator"}],
    }, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "sandbox").mkdir(parents=True, exist_ok=True)
    return directory


# Providers a reviewer seat may sit on. Every one is free; none is a paid route.
# Two vendors on purpose - a single-vendor roster fails as a unit whenever that
# one provider rate-limits.
FREE_PROVIDERS = {"opencode_cli", "amd_radeon"}


class ScriptedPool:
    def __init__(self, reply="INDEPENDENT: the evidence supports only a narrower claim.\nGAP: nobody checked the baseline.\nVERDICT: CANNOT_ASSESS"):
        self.reply = reply
        self.calls = []

    def chat(self, task_type="", messages=None, system_prompt="",
             selected_spec=None, max_retries=1, max_tokens=0,
             data_boundary=None, **kwargs):
        self.calls.append({
            "model": selected_spec,
            "boundary": data_boundary,
            "retries": max_retries,
            "user": (messages or [{}])[0].get("content", ""),
        })
        return {"success": True, "content": self.reply, "error": "",
                "provider": "amd_radeon", "model": str(selected_spec)}
        return {"success": True, "content": self.reply, "error": "",
                "provider": "amd_radeon", "model": str(selected_spec)}


def test_only_tasks_waiting_for_external_evidence_are_picked_up(tmp_path):
    _blocked_task(tmp_path, "RQ-TEST-001", waiting=True)
    _blocked_task(tmp_path, "RQ-TEST-002", waiting=False)
    reviewer = FreeZoneExternalReviewer(tmp_path, tmp_path / "sandbox", ScriptedPool())
    result = reviewer.run_once(force=True, limit=5)
    assert result["status"] == "EXTERNAL_REVIEW_RECORDED"
    assert result["tasks_reviewed"] == 1, "a task blocked for another reason is not this job"


def test_reviewers_are_pinned_and_cannot_fall_back_to_a_paid_route(tmp_path):
    _blocked_task(tmp_path)
    pool = ScriptedPool()
    reviewer = FreeZoneExternalReviewer(tmp_path, tmp_path / "sandbox", pool)
    reviewer.run_once(force=True, limit=1)
    assert pool.calls, "no model calls were made"
    for call in pool.calls:
        spec = call["model"]
        assert call["retries"] == 1
        assert call["boundary"] == {"data_class": "PUBLIC"}
        assert spec.provider in FREE_PROVIDERS, f"seat escaped its provider: {spec}"
        assert spec.production_eligible is False
    # every reviewer is a different model, so the reads are not interchangeable
    models = {c["model"].full_id for c in pool.calls}
    assert len(models) == len(REVIEWERS)


def test_reviewer_roster_spans_more_than_one_vendor():
    """An all-AMD roster fails whenever AMD rate-limits.

    The first live sweep of this job produced UNAVAILABLE for the only reviewer
    that mattered and DEGENERATE for another; both were on one vendor. ``不能只靠
    AMD`` is not a preference here, it is the reason the roster is split.
    """
    vendors = {m["model"].split(":", 1)[0] for m in REVIEWERS}
    assert len(vendors) > 1, f"reviewer roster is single-vendor: {vendors}"


def test_no_waiting_task_is_named_not_crashed(tmp_path):
    (tmp_path / "task_pool" / "blocked").mkdir(parents=True)
    reviewer = FreeZoneExternalReviewer(tmp_path, tmp_path / "sandbox", ScriptedPool())
    result = reviewer.run_once(force=True, limit=3)
    assert result["status"] == "NO_TASK_WAITING"
    assert result["reviews_written"] == 0


def test_unavailable_reviewer_does_not_sink_the_sweep(tmp_path):
    _blocked_task(tmp_path)

    class DeadPool:
        def chat(self, **kwargs):
            return {"success": False, "content": "", "error": "429"}

    reviewer = FreeZoneExternalReviewer(tmp_path, tmp_path / "sandbox", DeadPool())
    result = reviewer.run_once(force=True, limit=1)
    assert result["status"] == "EXTERNAL_REVIEW_RECORDED"
    assert result["verdict_histogram"].get("UNAVAILABLE", 0) == len(REVIEWERS)
    assert result["production_integration"] is False


def test_degenerate_reply_is_named_not_filed_as_a_review(tmp_path):
    """Live fire: one AMD seat answered with hundreds of '/' and nothing else.

    Filing that as REVIEWED would hand the steward filler to judge, so the
    status has to separate filler from a real answer and from an outage.
    """
    _blocked_task(tmp_path)
    reviewer = FreeZoneExternalReviewer(
        tmp_path, tmp_path / "sandbox", ScriptedPool(reply="/" * 400)
    )
    result = reviewer.run_once(force=True, limit=1)
    assert result["verdict_histogram"].get("DEGENERATE", 0) == len(REVIEWERS)
    assert result["verdict_histogram"].get("REVIEWED_WITHOUT_VERDICT", 0) == 0
    receipt = json.loads(
        (tmp_path / "sandbox" / "reports" / "external_review"
         / f"{result['experiment_id']}.json").read_text(encoding="utf-8")
    )
    assert all(r["status"] == "DEGENERATE" for r in receipt["reviews"])


def test_a_real_review_still_lands_with_its_verdict(tmp_path):
    _blocked_task(tmp_path)
    reviewer = FreeZoneExternalReviewer(tmp_path, tmp_path / "sandbox", ScriptedPool())
    result = reviewer.run_once(force=True, limit=1)
    assert result["verdict_histogram"].get("CANNOT_ASSESS", 0) == len(REVIEWERS)
    assert result["reviews_written"] == len(REVIEWERS)


def test_a_review_never_lands_in_the_task_pool(tmp_path):
    directory = _blocked_task(tmp_path)
    before = (directory / "RQ-TEST-001.json").read_text(encoding="utf-8")
    reviewer = FreeZoneExternalReviewer(tmp_path, tmp_path / "sandbox", ScriptedPool())
    reviewer.run_once(force=True, limit=1)
    after = (directory / "RQ-TEST-001.json").read_text(encoding="utf-8")
    assert before == after, "the reviewer is read-only over TaskPool"


def test_receipt_is_written_into_the_free_zone_not_governance(tmp_path):
    _blocked_task(tmp_path)
    reviewer = FreeZoneExternalReviewer(tmp_path, tmp_path / "sandbox", ScriptedPool())
    result = reviewer.run_once(force=True, limit=1)
    receipt = tmp_path / "sandbox" / "reports" / "external_review" / f"{result['experiment_id']}.json"
    assert receipt.exists(), "no receipt written"
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["contract_version"] == CONTRACT_VERSION
    assert payload["production_integration"] is False
    assert payload["tasks"] == ["RQ-TEST-001"]
    assert len(payload["reviews"]) == len(REVIEWERS)
    # the receipt must not drift into a governance directory
    assert not list(tmp_path.glob("08_GOVERNANCE/**/external_review*"))


def test_already_reviewed_tasks_are_not_reviewed_again_without_force(tmp_path):
    _blocked_task(tmp_path)
    reviewer = FreeZoneExternalReviewer(tmp_path, tmp_path / "sandbox", ScriptedPool())
    first = reviewer.run_once(force=True, limit=1)
    assert first["reviews_written"] == len(REVIEWERS)
    second = reviewer.run_once(limit=1)
    assert second["status"] == "NO_TASK_WAITING", "a repeated review is not new evidence"


def test_a_second_sweep_of_the_same_task_does_not_collide(tmp_path):
    """The sandbox refuses a duplicate experiment id; experiments are append-only.

    An id derived from the task ids alone collides on any re-run, so sweeping the
    same task again crashed instead of recording. Retrying an independent read is
    how the sweep is supposed to work.
    """
    _blocked_task(tmp_path)
    reviewer = FreeZoneExternalReviewer(tmp_path, tmp_path / "sandbox", ScriptedPool())
    first = reviewer.run_once(force=True, limit=1)
    assert first["status"] == "EXTERNAL_REVIEW_RECORDED"

    # fresh reviewer: the in-memory "already reviewed" filter resets, but the
    # sandbox does not. The second sweep must still record.
    again = FreeZoneExternalReviewer(tmp_path, tmp_path / "sandbox", ScriptedPool())
    second = again.run_once(force=True, limit=1)
    assert second["status"] == "EXTERNAL_REVIEW_RECORDED"
    assert second["experiment_id"] != first["experiment_id"], (
        "a re-run of the same tasks must be a new experiment, not a collision"
    )
    experiments = list((tmp_path / "sandbox" / "experiments").glob("*.json"))
    assert len(experiments) == 2, "both sweeps are kept; append-only means kept"


def test_experiment_is_recorded_as_inconclusive(tmp_path):
    _blocked_task(tmp_path)
    reviewer = FreeZoneExternalReviewer(tmp_path, tmp_path / "sandbox", ScriptedPool())
    result = reviewer.run_once(force=True, limit=1)
    experiment = tmp_path / "sandbox" / "experiments" / f"{result['experiment_id']}.json"
    assert experiment.exists()
    payload = json.loads(experiment.read_text(encoding="utf-8"))
    assert payload["outcome"] == "INCONCLUSIVE"
    assert payload["metadata"]["source_kind"] == "free_zone_external_review"
    assert payload["metadata"]["taskpool_read_only"] is True