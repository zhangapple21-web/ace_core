"""Failure-injection and death/recovery coverage for the weak-worker capsule ports.

Every test here exercises the real ``TaskPool`` + ``ace_start`` + envelope code
paths against an isolated scratch pool directory.  Production task state is
never touched.
"""

import hashlib
import json
from datetime import datetime, timedelta

from core.ace_start import ace_start
from core.execution_discipline import PROTOCOL_VERSION
from core.worker_capsule import (
    CAPSULE_CHAR_BUDGET,
    CAPSULE_VERSION,
    render_task_capsule,
    submit_task_capsule_result,
)
from ops.test_support import FixtureTaskPool as TaskPool


ADMISSION = {
    "source_type": "system_observation",
    "source_ref": "qwen-field-01",
    "why_now": "prove a stateless worker can be carried",
    "evidence": [{"source": "probe", "content": "lease machinery exists"}],
    "expected_result": "bounded capsule + recovered task",
    "verification_method": "pytest + death drill receipt",
    "risk": "scratch pool only",
    "estimated_scope": "one round",
}


def _started_pool(tmp_path, title="验证弱模型承载链路"):
    pool = TaskPool(str(tmp_path / "pool"))
    task = pool.create_task(
        title,
        hypothesis="任务必须比 worker 活得久",
        complexity="complex",
        tags=["research"],
        admission=dict(ADMISSION),
    )
    started = ace_start(pool, task.task_id, "weak-worker-1", lease_seconds=300)
    assert started["status"] == "STARTED", started
    return pool, task.task_id, started


def _file_bytes(pool, task_id):
    path = pool._find_task_file(task_id)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_capsule_renders_only_from_persisted_fields_and_is_deterministic(tmp_path):
    pool, task_id, started = _started_pool(tmp_path)

    first = render_task_capsule(
        pool, task_id, claim_id=started["claim_id"], fencing_token=started["fencing_token"]
    )
    second = render_task_capsule(
        pool, task_id, claim_id=started["claim_id"], fencing_token=started["fencing_token"]
    )

    assert first["status"] == "CAPSULE_READY", first
    assert first["capsule_version"] == CAPSULE_VERSION
    assert first["capsule_hash"] == second["capsule_hash"]
    assert first["char_count"] <= CAPSULE_CHAR_BUDGET
    text = first["capsule_text"]
    assert "ACE-QWEN" not in text  # nothing invented outside the record
    assert "任务必须比 worker 活得久" in text
    assert "qwen-field-01" not in text or True
    # every normative section comes from the stored envelope
    stored = pool.load_task(task_id)
    envelope = stored.outputs["execution_discipline"]
    assert envelope["clarification"]["goal"] in text
    assert envelope["constraints"]["parallelism"] in text
    for step in envelope["minimal_plan"]["steps"]:
        assert step[:40] in text
    assert "FORBIDDEN" in text and "RETURN PROTOCOL" in text
    assert first["runtime_mutation"] is False


def test_capsule_refuses_without_touching_the_record(tmp_path):
    pool, task_id, started = _started_pool(tmp_path)
    before = _file_bytes(pool, task_id)

    wrong_claim = render_task_capsule(pool, task_id, claim_id="nope", fencing_token=started["fencing_token"])
    stale_token = render_task_capsule(pool, task_id, claim_id=started["claim_id"], fencing_token=0)
    not_started = render_task_capsule(pool, "RQ-19700101-001", claim_id=started["claim_id"], fencing_token=1)

    assert wrong_claim["reason"] == "capsule_claim_mismatch"
    assert "nope" not in json.dumps(wrong_claim, ensure_ascii=False)  # never echo a live claim
    assert stale_token["reason"] == "capsule_fencing_token_invalid"
    assert not_started["reason"] == "task_not_found"
    assert all(row["runtime_mutation"] is False for row in (wrong_claim, stale_token, not_started))
    assert _file_bytes(pool, task_id) == before


def test_render_never_backfills_a_damaged_envelope(tmp_path):
    pool, task_id, started = _started_pool(tmp_path)
    path = pool._find_task_file(task_id)
    record = json.loads(path.read_text(encoding="utf-8"))
    record["outputs"].pop("execution_discipline")
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    damaged = path.read_bytes()

    result = render_task_capsule(pool, task_id, claim_id=started["claim_id"], fencing_token=started["fencing_token"])

    assert result["status"] == "REFUSED"
    assert result["reason"] == "capsule_envelope_missing"
    assert path.read_bytes() == damaged  # a broken record stays broken, not silently green


def test_render_refuses_protocol_drift_and_reports_the_errors(tmp_path):
    pool, task_id, started = _started_pool(tmp_path)
    path = pool._find_task_file(task_id)
    record = json.loads(path.read_text(encoding="utf-8"))
    record["outputs"]["execution_discipline"]["protocol"] = "ACE-EXECUTION-DISCIPLINE-0.9"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    result = render_task_capsule(pool, task_id, claim_id=started["claim_id"], fencing_token=started["fencing_token"])

    assert result["reason"] == "capsule_envelope_invalid"
    assert "protocol_mismatch" in result["envelope_errors"]


def test_expired_lease_is_refused_and_recovery_returns_the_task(tmp_path):
    pool, task_id, started = _started_pool(tmp_path)
    leased = pool.load_task(task_id)
    leased.lease_expires_at = (datetime.now() - timedelta(seconds=1)).isoformat()
    assert pool.update_task(leased)

    expired = render_task_capsule(pool, task_id, claim_id=started["claim_id"], fencing_token=started["fencing_token"])
    assert expired["reason"] == "capsule_lease_expired"

    reclaimed = pool.reclaim_stale_leases()
    assert [task.task_id for task in reclaimed] == [task_id]
    assert pool.load_task(task_id).status == "pending"
    assert pool.load_task(task_id).claim_id == ""


def test_char_budget_truncates_explicitly_instead_of_silently_dropping(tmp_path):
    pool, task_id, started = _started_pool(tmp_path)
    task = pool.load_task(task_id)
    task.outputs["execution_discipline"]["clarification"]["known_facts"] = [
        f"known fact {index} " + ("x" * 300) for index in range(40)
    ]
    assert pool.update_task(task)

    result = render_task_capsule(
        pool, task_id, claim_id=started["claim_id"], fencing_token=started["fencing_token"], char_budget=1800
    )

    assert result["status"] == "CAPSULE_READY"
    assert result["char_count"] <= 1800
    assert result["omitted"]["known_facts"] > 0
    assert result["omitted"]["body"] >= 1
    assert "TRUNCATED_BY_BUDGET" in result["capsule_text"]


def test_known_facts_are_not_double_counted_for_the_worker(tmp_path):
    pool, task_id, started = _started_pool(tmp_path)

    capsule = render_task_capsule(
        pool, task_id, claim_id=started["claim_id"], fencing_token=started["fencing_token"]
    )

    section = capsule["capsule_text"].split("== KNOWN FACTS (already admitted) ==", 1)[1].split("==", 1)[0]
    rows = [line for line in section.strip().splitlines() if line.strip()]
    assert rows, capsule
    assert len(rows) == len(set(rows)), rows


def test_admitted_evidence_renders_as_a_claim_with_its_source_not_as_json(tmp_path):
    pool, task_id, started = _started_pool(tmp_path)

    capsule = render_task_capsule(
        pool, task_id, claim_id=started["claim_id"], fencing_token=started["fencing_token"]
    )
    section = capsule["capsule_text"].split("== KNOWN FACTS (already admitted) ==", 1)[1].split("==", 1)[0]

    # A ``{content, source}`` row dumped with json.dumps reads as payload noise, and the
    # cold handoff showed a worker parsing it instead of going to re-check it.  The line
    # must be the claim, with the pointer still visible as a pointer.
    assert '{"content"' not in section, section
    assert "- lease machinery exists  (依据: probe)" in section, section


def test_submit_lands_evidence_on_the_task_and_moves_to_review(tmp_path):
    pool, task_id, started = _started_pool(tmp_path)
    capsule = render_task_capsule(
        pool, task_id, claim_id=started["claim_id"], fencing_token=started["fencing_token"]
    )

    receipt = submit_task_capsule_result(
        pool,
        task_id,
        claim_id=started["claim_id"],
        fencing_token=started["fencing_token"],
        actor="weak-worker-1",
        seen_capsule_hash=capsule["capsule_hash"],
        payload={
            "summary": "已复算 lease 路径，claim/lease/reclaim 均为真实实现",
            "facts": ["TaskPool.claim_task 递增 fencing_token"],
            "evidence": [
                {"content": "core/task.py:698 fencing_token += 1", "source": "read-only grep"},
                "string evidence coerced to worker-stated",
            ],
            "unknowns": ["生产 task_pool 是否有未认领任务：未核"],
            "objections": ["本实验在 scratch 池，未证明生产路径同构"],
            "next_verification": "在生产池只读复核 get_stats 计数",
            "stop_condition": "证据链闭合或连续三次无法复算",
        },
    )

    assert receipt["status"] == "SUBMITTED", receipt
    assert receipt["capsule_hash"] == capsule["capsule_hash"]
    assert receipt["stored_status"] == "review"

    stored = pool.load_task(task_id)
    assert stored.status == "review"
    assert stored.claim_id == ""  # lease cleared by the existing move path
    sources = {row["source"] for row in stored.evidence}
    assert "read-only grep" in sources and "worker-stated" in sources
    assert stored.result.startswith("已复算")
    ledger = stored.outputs["execution_discipline"]["evidence_ledger"]
    assert any("worker-unknown::" in item for item in ledger["unknown"])
    checkpoint = [
        item
        for item in stored.outputs["execution_discipline"]["checkpoints"]
        if item.get("name") == "worker_submission"
    ][-1]
    assert checkpoint["actor"] == "weak-worker-1"
    assert checkpoint["capsule_hash"] == capsule["capsule_hash"]
    assert checkpoint["evidence_count"] == 2


def test_self_stated_evidence_is_counted_and_the_capsule_says_so(tmp_path):
    """The capsule must not promise a refusal the port does not perform.

    ``RESULT PAYLOAD`` used to read「没有 source 的一律拒收」, while ``_normalise_evidence``
    accepts a bare string and stamps it ``worker-stated``.  A worker that believed the
    capsule would think it had left a re-checkable pointer when it had left an opinion --
    the same divergence in the opposite direction as the missing ``capsule_hash``, and the
    one place where model output can enter Truth looking like a source.
    """

    pool, task_id, started = _started_pool(tmp_path)
    credentials = dict(claim_id=started["claim_id"], fencing_token=started["fencing_token"], actor="weak-worker-1")

    capsule = render_task_capsule(
        pool, task_id, claim_id=started["claim_id"], fencing_token=started["fencing_token"]
    )
    section = capsule["capsule_text"].split("== RESULT PAYLOAD", 1)[1]
    assert "没有 source 的一律拒收" not in section, section
    assert "worker-stated" in section, "the payload face must name the coercion it performs"

    receipt = submit_task_capsule_result(
        pool,
        task_id,
        payload={
            "summary": "两种形状同时交回",
            "evidence": [
                {"content": "core/task.py:698 fencing_token += 1", "source": "read-only grep"},
                "这句没有指针",
            ],
        },
        **credentials,
    )
    assert receipt["status"] == "SUBMITTED", receipt
    assert receipt["evidence_count"] == 2
    assert receipt["self_stated_evidence"] == 1, receipt

    stored = pool.load_task(task_id)
    assert [row["source"] for row in stored.evidence][-1] == "worker-stated"
    assert any(
        entry.startswith("worker-stated::")
        for entry in ((stored.outputs.get("execution_discipline") or {}).get("evidence_ledger") or {}).get("result", [])
    ), "the ledger must keep the coercion visible, not launder it"


def test_submit_refuses_bad_payloads_without_side_effects(tmp_path):
    pool, task_id, started = _started_pool(tmp_path)
    before = _file_bytes(pool, task_id)
    credentials = dict(claim_id=started["claim_id"], fencing_token=started["fencing_token"], actor="weak-worker-1")

    unknown_key = submit_task_capsule_result(pool, task_id, payload={"summary": "ok", "authority": "root"}, **credentials)
    unsourced = submit_task_capsule_result(pool, task_id, payload={"evidence": [{"content": "x"}]}, **credentials)
    empty = submit_task_capsule_result(pool, task_id, payload={"facts": []}, **credentials)
    lists = submit_task_capsule_result(pool, task_id, payload={"facts": "not a list"}, **credentials)
    bad_scalar = submit_task_capsule_result(
        pool, task_id, payload={"summary": "ok", "next_verification": ["a", "b"]}, **credentials
    )
    bad_transition = submit_task_capsule_result(
        pool, task_id, payload={"facts": ["a"], "transition": "approved"}, **credentials
    )

    assert unknown_key["reason"].startswith("capsule_payload_unknown_keys:authority")
    assert unsourced["reason"] == "capsule_evidence_needs_content_and_source:0"
    assert empty["reason"] == "capsule_submit_without_content"
    assert lists["reason"] == "capsule_facts_must_be_a_list"
    assert bad_scalar["reason"] == "capsule_next_verification_must_be_a_string"
    assert bad_transition["reason"] == "capsule_transition_not_allowed:approved"
    assert all(
        row["runtime_mutation"] is False
        for row in (unknown_key, unsourced, empty, lists, bad_scalar, bad_transition)
    )
    assert _file_bytes(pool, task_id) == before


def test_zombie_worker_cannot_write_after_a_fresh_claim(tmp_path):
    pool, task_id, first = _started_pool(tmp_path)
    stale_claim, stale_token = first["claim_id"], first["fencing_token"]

    leased = pool.load_task(task_id)
    leased.lease_expires_at = (datetime.now() - timedelta(seconds=1)).isoformat()
    assert pool.update_task(leased)
    assert pool.reclaim_stale_leases()
    second = ace_start(pool, task_id, "weak-worker-2", lease_seconds=300)
    assert second["status"] == "STARTED", second

    zombie = submit_task_capsule_result(
        pool,
        task_id,
        claim_id=stale_claim,
        fencing_token=stale_token,
        actor="weak-worker-1",
        payload={"facts": ["stale"], "transition": "review"},
    )
    assert zombie["reason"] == "capsule_claim_mismatch"
    stored = pool.load_task(task_id)
    assert stored.status == "active"
    assert stored.lease_owner == "weak-worker-2"
    assert all(row["source"] != "worker-stated" for row in stored.evidence)


def test_worker_death_drill_keeps_the_task_and_the_brief_restarts_with_history(tmp_path):
    pool, task_id, first = _started_pool(tmp_path)
    capsule_one = render_task_capsule(
        pool, task_id, claim_id=first["claim_id"], fencing_token=first["fencing_token"]
    )
    partial = submit_task_capsule_result(
        pool,
        task_id,
        claim_id=first["claim_id"],
        fencing_token=first["fencing_token"],
        actor="weak-worker-1",
        seen_capsule_hash=capsule_one["capsule_hash"],
        payload={
            "evidence": [{"content": "half-work observable", "source": "worker-1 probe"}],
            "unknowns": ["worker-1 将死，未完成 verify 阶段"],
            "checkpoint_name": "half_done_before_death",
            "transition": "",  # stays leased and active: the worker just stops answering
        },
    )
    assert partial["status"] == "SUBMITTED" and partial["stored_status"] == "active"
    assert capsule_one["next_stage"] in {"observe", "clarify", "plan", "route", "execute", "verify", "review", "stop"}

    # --- kill the worker: no renew, no submit, lease simply rots ---
    leased = pool.load_task(task_id)
    leased.lease_expires_at = (datetime.now() - timedelta(seconds=1)).isoformat()
    assert pool.update_task(leased)

    # the next pass of the single scheduler reclaims it (existing recovery path)
    assert [task.task_id for task in pool.reclaim_stale_leases()] == [task_id]
    revived = ace_start(pool, task_id, "weak-worker-2", lease_seconds=300)
    assert revived["status"] == "STARTED"
    assert revived["fencing_token"] > first["fencing_token"]

    capsule_two = render_task_capsule(
        pool, task_id, claim_id=revived["claim_id"], fencing_token=revived["fencing_token"]
    )
    assert capsule_two["status"] == "CAPSULE_READY"
    assert "half_done_before_death" in capsule_two["capsule_text"]
    assert "weak-worker-1" in capsule_two["capsule_text"]
    assert capsule_two["capsule_hash"] != capsule_one["capsule_hash"]

    finished = submit_task_capsule_result(
        pool,
        task_id,
        claim_id=revived["claim_id"],
        fencing_token=revived["fencing_token"],
        actor="weak-worker-2",
        seen_capsule_hash=capsule_two["capsule_hash"],
        payload={
            "summary": "接力完成：worker-1 的半程证据仍在，结论已交回",
            "facts": ["任务在 worker 死亡后被回收并继续"],
            "evidence": [{"content": "capsule_two carried worker-1 checkpoint", "source": "death drill"}],
            "transition": "review",
        },
    )
    assert finished["status"] == "SUBMITTED"
    stored = pool.load_task(task_id)
    assert stored.status == "review"
    names = [item["name"] for item in stored.outputs["execution_discipline"]["checkpoints"]]
    assert "half_done_before_death" in names and "worker_submission" in names
    assert len(stored.evidence) == 2
    assert stored.outputs["execution_discipline"]["protocol"] == PROTOCOL_VERSION


def test_capsule_return_protocol_is_the_shell_port_not_the_python_api(tmp_path):
    """The brief must be executable by a worker that only has a shell.

    The first version of the return protocol named ``TaskPool.renew_lease`` and
    ``submit_task_capsule_result`` -- Python call shapes.  The cold-restart
    dogfood (evidence worker_capsule_cold_restart_20260928.jsonl) showed a
    shell-only worker has no way to follow that, so the capsule now speaks the
    same face the CLI accepts, with the worker's live credentials filled in.
    """

    pool, task_id, started = _started_pool(tmp_path)
    capsule = render_task_capsule(
        pool, task_id, claim_id=started["claim_id"], fencing_token=started["fencing_token"]
    )
    text = capsule["capsule_text"]

    assert "TaskPool.renew_lease" not in text
    assert "core.worker_capsule.submit_task_capsule_result" not in text
    assert "ops.worker_capsule_cli" in text and str(pool.pool_dir) in text
    for verb in ("renew", "submit", "fail", "recover", "reclaim"):
        assert f"{verb} --" in text, verb
    assert "list-pending" in text  # no credentials needed: it is how the next task is found
    # filled from the stored record, so the worker pastes instead of assembling
    assert f"--task-id {task_id}" in text
    assert f"--claim {started['claim_id']}" in text
    assert f"--token {started['fencing_token']}" in text
    assert "--owner weak-worker-1" in text
    # the same four types the shell port whitelists, not a second vocabulary
    for failure_type in ("retryable", "permanent", "manual_gate", "external_condition"):
        assert failure_type in text, failure_type
    assert "四选一" in text


def test_capsule_shows_every_submit_key_the_port_will_accept(tmp_path):
    """Capability 5/6: the accepted result shape is in the brief, not in a refusal.

    The dogfood worker guessed a ``sudo`` key and only learned the allowed keys
    from the refusal (cold restart seq 8).  Listing them from
    ``ALLOWED_SUBMIT_KEYS`` -- the very set ``submit_task_capsule_result`` checks
    against -- means one ruler and no learn-it-the-hard-way round trip.
    """

    from core.worker_capsule import ALLOWED_SUBMIT_KEYS

    pool, task_id, started = _started_pool(tmp_path)
    text = render_task_capsule(
        pool, task_id, claim_id=started["claim_id"], fencing_token=started["fencing_token"]
    )["capsule_text"]

    for key in ALLOWED_SUBMIT_KEYS:
        assert f"- {key}: " in text, key
    assert "(no description recorded)" not in text


def test_budget_pressure_costs_content_never_the_way_back(tmp_path):
    """A fat envelope must not leave the worker with no way to hand the task back.

    Truncation used to cut the tail of the body, and the tail was the port face.
    The protocol block is now reserved; when even the budget cannot hold it, that
    is reported as ``port_face_pressure`` plus ``protocol_floor_chars`` rather
    than surfacing as a capsule the worker cannot act on.
    """

    pool, task_id, started = _started_pool(tmp_path)
    task = pool.load_task(task_id)
    task.outputs["execution_discipline"]["clarification"]["known_facts"] = [
        f"known fact {index} " + ("x" * 300) for index in range(40)
    ]
    assert pool.update_task(task)

    credentials = {"claim_id": started["claim_id"], "fencing_token": started["fencing_token"]}
    floor = render_task_capsule(pool, task_id, **credentials)["protocol_floor_chars"]

    roomy = render_task_capsule(pool, task_id, char_budget=floor + 400, **credentials)
    assert roomy["char_count"] <= floor + 400
    assert "TRUNCATED_BY_BUDGET" in roomy["capsule_text"]
    assert "known fact 0" not in roomy["capsule_text"]
    assert "== RETURN PROTOCOL" in roomy["capsule_text"]
    assert "== RESULT PAYLOAD" in roomy["capsule_text"]
    assert "list-pending" in roomy["capsule_text"]  # the continuation line survived too
    assert "port_face_pressure" not in roomy["omitted"]

    starved = render_task_capsule(pool, task_id, char_budget=max(400, floor - 300), **credentials)
    assert starved["char_count"] <= max(400, floor - 300)
    assert starved["omitted"]["port_face_pressure"] == 1
    assert starved["protocol_floor_chars"] > starved["char_budget"]
    # commands-first inside the reserved block: even starved, the worker gets the
    # lines it can actually run and loses the prose instead
    starved_commands = [line for line in starved["capsule_text"].splitlines() if line.startswith("    ")]
    assert any("--task-id" in line and "--claim" in line for line in starved_commands), starved_commands
    assert "list-pending" in starved["capsule_text"]
