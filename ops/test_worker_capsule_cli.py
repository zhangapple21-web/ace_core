"""Shell-level contract for the worker capsule CLI (real subprocesses, real exit codes).

A weak worker must be able to use ACE without writing Python: one command, one
JSON line, and an exit code a shell can branch on.  These tests drive the CLI
as a subprocess against a scratch pool only.
"""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Windows defaults child/parent stdio to the ANSI codepage, which mangles the
# Chinese text this capsule renders.  Pin UTF-8 on both sides of the pipe.
CHILD_ENV = dict(os.environ, PYTHONIOENCODING="utf-8")

ADMISSION = {
    "source_type": "evidence",
    "source_ref": "cli-test",
    "why_now": "prove the shell port works",
    "evidence": [{"source": "field-scan", "content": "core/worker_capsule.py exists"}],
    "expected_result": "single-line JSON per command",
    "verification_method": "subprocess exit codes",
    "risk": "scratch pool only",
    "estimated_scope": "one test",
}


def _run(pool_dir, *argv, payload=None):
    command = [sys.executable, "-m", "ops.worker_capsule_cli", "--pool", str(pool_dir), *argv]
    result = subprocess.run(
        command,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        env=CHILD_ENV,
    )
    return result, command


def _seed_task(pool_dir, title="CLI 承载演练", ref=None):
    sys.path.insert(0, str(REPO_ROOT))
    from core.task import TaskPool

    pool = TaskPool(str(pool_dir))
    admission = dict(ADMISSION)
    # Admission dedup is real: two cards with the same admission return the SAME
    # task (found while seeding three tasks for the reclaim arms), so multi-task
    # tests must vary source_ref.
    admission["source_ref"] = ref or f"{title}-{len(title)}-{time.time_ns()}"
    return pool.create_task(
        title,
        hypothesis="shell worker 可以完成任务",
        creator="cli",
        complexity="complex",
        tags=["research"],
        admission=admission,
    )


def _one_json_line(result):
    assert result.returncode in (0, 3, 4), (result.returncode, result.stderr[-800:])
    lines = [line for line in result.stdout.strip().splitlines() if line.strip()]
    assert len(lines) == 1, lines
    return json.loads(lines[0])


def test_cli_list_start_render_submit_round_trip(tmp_path):
    pool_dir = tmp_path / "pool"
    task = _seed_task(pool_dir)

    listed = _one_json_line(_run(pool_dir, "list-pending")[0])
    assert listed["status"] == "LISTED"
    assert listed["pending"][0]["task_id"] == task.task_id
    assert listed["pending"][0]["complexity"] == "complex"

    started = _one_json_line(_run(pool_dir, "start", "--task-id", task.task_id, "--owner", "shell-w1", "--lease", "120")[0])
    assert started["status"] == "STARTED", started

    rendered = _one_json_line(
        _run(pool_dir, "render", "--task-id", task.task_id, "--claim", started["claim_id"], "--token", str(started["fencing_token"]))[0]
    )
    assert rendered["status"] == "CAPSULE_READY"
    assert "[ACE_TASK_CAPSULE" in rendered["capsule_text"]

    payload_path = tmp_path / "payload.json"
    payload_path.write_text(
        json.dumps(
            {
                "summary": "shell worker 完成",
                "facts": ["CLI 单行 JSON 输出"],
                "evidence": [{"content": "subprocess exit 0", "source": "test_cli"}],
                "transition": "review",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    submitted = _run(
        pool_dir,
        "submit",
        "--task-id",
        task.task_id,
        "--claim",
        started["claim_id"],
        "--token",
        str(started["fencing_token"]),
        "--actor",
        "shell-w1",
        "--payload-file",
        str(payload_path),
        "--capsule-hash",
        rendered["capsule_hash"],
    )[0]
    receipt = _one_json_line(submitted)
    assert submitted.returncode == 0, receipt
    assert receipt["status"] == "SUBMITTED" and receipt["stored_status"] == "review"

    after = _one_json_line(_run(pool_dir, "list-pending")[0])
    assert after["count"] == 0


def test_cli_refusals_use_exit_code_three_and_write_nothing(tmp_path):
    pool_dir = tmp_path / "pool"
    task = _seed_task(pool_dir)
    started = _one_json_line(_run(pool_dir, "start", "--task-id", task.task_id, "--owner", "shell-w1")[0])

    bad_claim = _run(pool_dir, "render", "--task-id", task.task_id, "--claim", "wrong", "--token", "1")[0]
    assert bad_claim.returncode == 3
    assert _one_json_line(bad_claim)["reason"] == "capsule_claim_mismatch"

    # quoting-hostile payload inline: no file, wrong key
    hostile = _run(
        pool_dir,
        "submit",
        "--task-id",
        task.task_id,
        "--claim",
        started["claim_id"],
        "--token",
        str(started["fencing_token"]),
        "--actor",
        "shell-w1",
        "--payload",
        '{"summary": "ok", "sudo": true}',
    )[0]
    assert hostile.returncode == 3
    assert _one_json_line(hostile)["reason"].startswith("capsule_payload_unknown_keys")

    unreadable = _run(
        pool_dir,
        "submit",
        "--task-id",
        task.task_id,
        "--claim",
        started["claim_id"],
        "--token",
        str(started["fencing_token"]),
        "--actor",
        "shell-w1",
        "--payload-file",
        str(tmp_path / "missing.json"),
    )[0]
    assert unreadable.returncode == 3
    refusal = _one_json_line(unreadable)
    assert refusal["reason"].startswith("payload_unreadable")

    # A broken byte inside an otherwise good file must be pointed at, not just
    # reported as "invalid json" -- this is the failure a weak worker cannot
    # self-diagnose (found while dogfooding the CLI from a shell).
    broken = tmp_path / "broken.json"
    broken.write_text('{"summary": "ok",\n"facts": ["a"]\n"transition": "review"}\n', encoding="utf-8")
    malformed = _run(
        pool_dir,
        "submit",
        "--task-id",
        task.task_id,
        "--claim",
        started["claim_id"],
        "--token",
        str(started["fencing_token"]),
        "--actor",
        "shell-w1",
        "--payload-file",
        str(broken),
    )[0]
    assert malformed.returncode == 3
    detail = _one_json_line(malformed)["detail"]
    assert detail["error_type"] == "JSONDecodeError"
    assert detail["line"] >= 1 and detail["character_offset"] >= 0
    assert "fix_hint" in detail and "offending_line" in detail

    not_object = _run(
        pool_dir,
        "submit",
        "--task-id",
        task.task_id,
        "--claim",
        started["claim_id"],
        "--token",
        str(started["fencing_token"]),
        "--actor",
        "shell-w1",
        "--payload",
        '["a", "b"]',
    )[0]
    assert not_object.returncode == 3
    assert _one_json_line(not_object)["reason"] == "payload_must_be_json_object_not_list"

    still_active = _one_json_line(
        _run(pool_dir, "render", "--task-id", task.task_id, "--claim", started["claim_id"], "--token", str(started["fencing_token"]))[0]
    )
    assert still_active["status"] == "CAPSULE_READY"
    ledger_line = (
        still_active["capsule_text"]
        .split("== EVIDENCE LEDGER (counts) ==", 1)[1]
        .strip()
        .splitlines()[0]
    )
    counts = json.loads(ledger_line[2:])
    assert {key: counts[key] for key in ("result", "review", "source", "runtime")} == {
        "result": 0,
        "review": 0,
        "source": 0,
        "runtime": 0,
    }, counts


def test_cli_fail_command_classifies_and_releases_the_lease(tmp_path):
    pool_dir = tmp_path / "pool"
    task = _seed_task(pool_dir)
    started = _one_json_line(_run(pool_dir, "start", "--task-id", task.task_id, "--owner", "shell-w1")[0])

    failed = _run(
        pool_dir,
        "fail",
        "--task-id",
        task.task_id,
        "--claim",
        started["claim_id"],
        "--token",
        str(started["fencing_token"]),
        "--actor",
        "shell-w1",
        "--reason",
        "外部依赖未就绪",
        "--type",
        "external_condition",
    )[0]
    result = _one_json_line(failed)
    assert failed.returncode == 0, result
    assert result["status"] == "FAILED_RECORDED"
    assert result["stored_status"] == "blocked"

    requeued = _one_json_line(_run(pool_dir, "start", "--task-id", task.task_id, "--owner", "shell-w2")[0])
    assert requeued["status"] == "REJECTED"
    assert requeued["reason"] == "taskpool_claim_rejected"


def test_cli_refuses_a_made_up_failure_type_instead_of_retrying_it(tmp_path):
    """``fail_task`` has no vocabulary check, so this port must have one.

    Measured on a scratch pool at 2026-09-28T17:42:38: failure_type="permnnent",
    "typos_are_silent" and "" all stored the task back to *pending* with a retry
    delay, while the bogus word still went into the ledger as ``failure:permnnent``.
    A worker that means "this cannot be done" must not be able to write "do it
    again later" by typing one letter wrong.
    """

    pool_dir = tmp_path / "pool"
    task = _seed_task(pool_dir)
    started = _one_json_line(_run(pool_dir, "start", "--task-id", task.task_id, "--owner", "shell-w1")[0])

    for bogus in ("permnnent", "RETRYABLE", ""):
        refused = _run(
            pool_dir,
            "fail",
            "--task-id",
            task.task_id,
            "--claim",
            started["claim_id"],
            "--token",
            str(started["fencing_token"]),
            "--actor",
            "shell-w1",
            "--reason",
            "外部依赖未就绪",
            "--type",
            bogus,
        )[0]
        assert refused.returncode == 3, (bogus, refused.stdout, refused.stderr[-300:])
        row = _one_json_line(refused)
        assert row["status"] == "REFUSED" and row["reason"].startswith("capsule_failure_type_unknown")
        assert row["allowed_failure_types"] == ["retryable", "permanent", "manual_gate", "external_condition"]
        assert row["runtime_mutation"] is False

    # Still active, still leased, retry_count untouched -- the refusal wrote nothing.
    alive = _one_json_line(
        _run(
            pool_dir,
            "render",
            "--task-id",
            task.task_id,
            "--claim",
            started["claim_id"],
            "--token",
            str(started["fencing_token"]),
        )[0]
    )
    assert alive["status"] == "CAPSULE_READY"
    sys.path.insert(0, str(REPO_ROOT))
    from core.task import TaskPool

    stored = TaskPool(str(pool_dir)).load_task(task.task_id)
    assert stored.status == "active" and stored.retry_count == 0 and stored.retry_after in ("", None)

    # The real types still work, including the one that must not re-queue.
    permanent = _run(
        pool_dir,
        "fail",
        "--task-id",
        task.task_id,
        "--claim",
        started["claim_id"],
        "--token",
        str(started["fencing_token"]),
        "--actor",
        "shell-w1",
        "--reason",
        "机制上不可行",
        "--type",
        "permanent",
    )[0]
    row = _one_json_line(permanent)
    assert permanent.returncode == 0, row
    assert row["stored_status"] == "graveyard"


def test_cli_fail_refuses_a_stale_claim_that_the_pool_would_have_honoured(tmp_path):
    """The pool's ``fail_task`` takes a task id and no claim, so it is unfenced.

    Without this gate a zombie worker (its claim superseded by a reclaim) can
    still move a task its successor is holding.
    """

    pool_dir = tmp_path / "pool"
    task = _seed_task(pool_dir)
    first = _one_json_line(_run(pool_dir, "start", "--task-id", task.task_id, "--owner", "zombie", "--lease", "1")[0])

    time.sleep(1.5)
    sys.path.insert(0, str(REPO_ROOT))
    from core.task import TaskPool

    pool = TaskPool(str(pool_dir))
    assert [item.task_id for item in pool.reclaim_stale_leases()] == [task.task_id]
    second = _one_json_line(_run(pool_dir, "start", "--task-id", task.task_id, "--owner", "live", "--lease", "300")[0])
    assert second["status"] == "STARTED" and second["fencing_token"] == first["fencing_token"] + 1

    zombie = _run(
        pool_dir,
        "fail",
        "--task-id",
        task.task_id,
        "--claim",
        first["claim_id"],
        "--token",
        str(first["fencing_token"]),
        "--actor",
        "zombie",
        "--reason",
        "僵尸想改写现任的结果",
        "--type",
        "retryable",
    )[0]
    assert zombie.returncode == 3, zombie.stdout
    row = _one_json_line(zombie)
    assert row["status"] == "REFUSED"
    assert row["reason"] in {"capsule_claim_mismatch", "capsule_fencing_token_stale"}
    assert row["runtime_mutation"] is False

    still = TaskPool(str(pool_dir)).load_task(task.task_id)
    assert still.status == "active" and still.claim_id == second["claim_id"] and still.retry_count == 0


def test_cli_refuses_to_open_a_pool_that_is_not_this_runtime_s_face(tmp_path):
    """``--pool`` may name the production pool or a temp scratch pool, nothing else.

    Any other directory would quietly become a second TaskPool on the first
    write, which is exactly what this task forbids.
    """

    elsewhere = REPO_ROOT / "not_a_pool_face"
    refused = _run(elsewhere, "list-pending")[0]
    assert refused.returncode == 3, refused.stdout
    row = _one_json_line(refused)
    assert row["status"] == "REFUSED" and row["reason"] == "capsule_pool_face_unknown"
    assert row["allowed_faces"]["production"].endswith("task_pool")
    assert not elsewhere.exists(), "the refusal must not create the pool directory"

    # The two allowed faces still work: production read-only, scratch read-write.
    production = _run(REPO_ROOT / "task_pool", "list-pending")[0]
    assert production.returncode == 0, production.stdout
    assert _one_json_line(production)["status"] == "LISTED"
    assert _one_json_line(_run(tmp_path / "pool", "list-pending")[0])["status"] == "LISTED"



def _run_drill(*argv):
    result = subprocess.run(
        [sys.executable, "-m", "ops.worker_capsule_death_drill", *argv],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        env=CHILD_ENV,
    )
    return result


def test_drill_reports_unresumable_run_as_one_readable_row(tmp_path):
    """Re-running 'resume' must not hand a weak worker a stack trace.

    The first version of the drill assumed the second process would always get a
    claim and raised ``KeyError: 'claim_id'`` when the task had already moved on --
    indistinguishable, to a shell-only worker, from the recovery gate being broken.
    """

    missing_state = _run_drill("resume", "--pool-dir", str(tmp_path / "pool"), "--state", str(tmp_path / "gone.json"))
    assert missing_state.returncode == 2, missing_state.stderr[-500:]
    row = json.loads(missing_state.stdout.strip())
    assert row["status"] == "NOT_RESUMABLE" and row["reason"] == "state_file_missing"
    assert "recovery_hint" in row and row["runtime_mutation"] is False
    assert "Traceback" not in missing_state.stderr

    # Already-finished task: claim is refused by the pool, drill says so plainly.
    sys.path.insert(0, str(REPO_ROOT))
    from core.ace_start import ace_start
    from core.task import TaskPool

    pool_dir = tmp_path / "pool"
    pool = TaskPool(str(pool_dir))
    task = pool.create_task(
        "已完成的演练任务",
        hypothesis="不可再接力",
        creator="cli",
        complexity="simple",
        tags=["research"],
        admission=dict(ADMISSION),
    )
    claimed = ace_start(pool, task.task_id, "cli", lease_seconds=60)
    moved = pool.move_task(task.task_id, "review", actor="cli", reason="done", claim_id=claimed["claim_id"])
    assert moved is not None and moved.status == "review", moved.status if moved else None

    state_path = tmp_path / "state.json"
    state_path.write_text(
        json.dumps(
            {
                "task_id": task.task_id,
                "a_claim_id": claimed["claim_id"],
                "a_fencing_token": claimed["fencing_token"],
                "a_capsule_hash": "0" * 64,
                "a_pid": os.getpid(),
                "a_submit": "SUBMITTED",
            }
        ),
        encoding="utf-8",
    )

    finished = _run_drill(
        "resume",
        "--pool-dir",
        str(pool_dir),
        "--state",
        str(state_path),
        "--receipt",
        str(tmp_path / "receipt.json"),
    )
    assert finished.returncode == 2, (finished.stdout[-400:], finished.stderr[-600:])
    row = json.loads(finished.stdout.strip())
    assert row["status"] == "NOT_RESUMABLE"
    assert row["reason"] == "taskpool_claim_rejected"
    assert row["current_status"] == "review"
    assert "Traceback" not in finished.stderr
    assert not (tmp_path / "receipt.json").exists()


def test_drill_scratch_reset_refuses_any_pool_it_does_not_own(tmp_path):
    from ops.worker_capsule_death_drill import _reset_scratch_pool

    keep = tmp_path / "production_like"
    keep.mkdir()
    victim = keep / "task.json"
    victim.write_text('{"task_id": "must-survive"}', encoding="utf-8")

    refused = None
    try:
        _reset_scratch_pool(keep)
    except SystemExit as error:
        refused = str(error)
    assert refused is not None, "purge was allowed outside the drill scratch dir"
    assert "pool_dir_is_not_the_scratch_pool" in refused
    assert victim.exists() and json.loads(victim.read_text(encoding="utf-8")) == {"task_id": "must-survive"}


def test_recover_hands_the_credentials_back_to_a_worker_that_lost_its_context(tmp_path):
    """The cold-restart path, each step in its own process: start -> forget -> recover -> render.

    Ability 8 (recover after interruption) is worthless if it only works for a
    worker that still remembers its claim id -- the thing a context loss deletes
    first.
    """

    pool_dir = tmp_path / "pool"
    task = _seed_task(pool_dir)
    started = _one_json_line(_run(pool_dir, "start", "--task-id", task.task_id, "--owner", "shell-cold", "--lease", "300")[0])
    assert started["status"] == "STARTED"

    # A worker with an empty context cannot re-enter through a credential port.
    blind = _one_json_line(_run(pool_dir, "render", "--task-id", task.task_id, "--claim", "", "--token", "0")[0])
    assert blind["status"] == "REFUSED"

    found = _run(pool_dir, "recover", "--owner", "shell-cold")[0]
    leases = _one_json_line(found)
    assert found.returncode == 0, leases
    assert leases["status"] == "LEASES_FOUND" and leases["count"] == 1
    row = leases["leases"][0]
    assert row["task_id"] == task.task_id
    assert row["claim_id"] == started["claim_id"] and row["fencing_token"] == started["fencing_token"]
    assert row["lease_seconds_remaining"] and row["lease_seconds_remaining"] > 0
    assert leases["runtime_mutation"] is False
    assert task.task_id in row["next_command"] and row["claim_id"] in row["next_command"]

    # The recovered credentials must actually open the capsule in a fresh process.
    rendered = _one_json_line(
        _run(pool_dir, "render", "--task-id", task.task_id, "--claim", row["claim_id"], "--token", str(row["fencing_token"]))[0]
    )
    assert rendered["status"] == "CAPSULE_READY", rendered
    assert "[ACE_TASK_CAPSULE" in rendered["capsule_text"]


def test_recover_never_leases_a_task_to_someone_else_and_never_to_a_dead_owner(tmp_path):
    pool_dir = tmp_path / "pool"
    task = _seed_task(pool_dir)
    started = _one_json_line(_run(pool_dir, "start", "--task-id", task.task_id, "--owner", "shell-holder", "--lease", "1")[0])
    live_claim = started["claim_id"]

    # Another owner asks: the answer is empty and leaks no credential.
    stranger = _run(pool_dir, "recover", "--owner", "shell-thief")[0]
    stranger_row = _one_json_line(stranger)
    assert stranger.returncode == 0
    assert stranger_row["status"] == "NO_LIVE_LEASE" and stranger_row["count"] == 0
    assert live_claim not in stranger.stdout, "recover echoed another worker's claim id"

    # Right owner, expired lease: the task is named, the credential is not.
    time.sleep(1.5)
    expired = _one_json_line(_run(pool_dir, "recover", "--owner", "shell-holder")[0])
    assert expired["status"] == "NO_LIVE_LEASE"
    assert [row["task_id"] for row in expired["expired_claims"]] == [task.task_id]
    assert expired["expired_claims"][0]["lease_state"] == "expired"
    assert "claim_id" not in expired["expired_claims"][0], "an expired lease was handed back as if it were live"
    assert "reclaim" in expired["hint"]

    sys.path.insert(0, str(REPO_ROOT))
    from core.task import TaskPool

    stored = TaskPool(str(pool_dir)).load_task(task.task_id)
    assert stored.status == "active" and stored.claim_id == live_claim and stored.retry_count == 0


def test_recover_leaves_the_pool_byte_identical(tmp_path):
    pool_dir = tmp_path / "pool"
    task = _seed_task(pool_dir)
    _one_json_line(_run(pool_dir, "start", "--task-id", task.task_id, "--owner", "shell-readonly")[0])

    before = {str(p): p.read_bytes() for p in pool_dir.rglob("*.json")}
    assert before, "the scratch pool holds no json files to compare against"
    receipt = _one_json_line(_run(pool_dir, "recover", "--owner", "shell-readonly")[0])
    assert receipt["count"] == 1
    after = {str(p): p.read_bytes() for p in pool_dir.rglob("*.json")}
    assert after == before, "recover mutated the pool while claiming to be read-only"


def test_reclaim_refuses_a_live_lease_and_a_foreign_one_but_reopens_its_own(tmp_path):
    """One task moves, and only its own owner may move it after the lease dies.

    This is the difference between a worker port and a scheduler: the pool's
    ``reclaim_stale_leases`` sweeps every expired lease in the runtime, which is not
    a right to hand a task worker.
    """

    pool_dir = tmp_path / "pool"
    live_task = _seed_task(pool_dir, title="仍在租期内")
    mine = _seed_task(pool_dir, title="我的过期租约")
    theirs = _seed_task(pool_dir, title="别人过期的租约")

    sys.path.insert(0, str(REPO_ROOT))
    from core.task import TaskPool

    live_start = _one_json_line(_run(pool_dir, "start", "--task-id", live_task.task_id, "--owner", "shell-mine", "--lease", "300")[0])
    live = _run(pool_dir, "reclaim", "--task-id", live_task.task_id, "--actor", "shell-mine")[0]
    assert live.returncode == 3, live.stdout
    row = _one_json_line(live)
    assert row["reason"] == "capsule_lease_still_live" and row["runtime_mutation"] is False
    held = TaskPool(str(pool_dir)).load_task(live_task.task_id)
    assert held.status == "active" and held.claim_id == live_start["claim_id"]

    # A foreign worker cannot touch it either, and is not told the holder's credential.
    thief = _run(pool_dir, "reclaim", "--task-id", live_task.task_id, "--actor", "shell-other")[0]
    assert thief.returncode == 3
    assert _one_json_line(thief)["reason"] == "capsule_not_lease_owner"
    assert live_start["claim_id"] not in thief.stdout

    # Now let two leases die: only the caller's own task may be re-opened.
    first = _one_json_line(_run(pool_dir, "start", "--task-id", mine.task_id, "--owner", "shell-mine", "--lease", "1")[0])
    other = _one_json_line(_run(pool_dir, "start", "--task-id", theirs.task_id, "--owner", "shell-theirs", "--lease", "1")[0])
    time.sleep(1.5)

    done = _run(pool_dir, "reclaim", "--task-id", mine.task_id, "--actor", "shell-mine")[0]
    assert done.returncode == 0, done.stdout
    result = _one_json_line(done)
    assert result["status"] == "LEASE_RECLAIMED" and result["stored_status"] == "pending"
    assert result["runtime_mutation"] is True
    assert result["previous_fencing_token"] == first["fencing_token"]

    untouched = TaskPool(str(pool_dir)).load_task(theirs.task_id)
    assert untouched.status == "active" and untouched.claim_id == other["claim_id"], (
        "a single-task reclaim swept another worker's expired lease"
    )

    # The task is claimable again, with a strictly higher fencing token.
    again = _one_json_line(_run(pool_dir, "start", "--task-id", mine.task_id, "--owner", "shell-mine", "--lease", "60")[0])
    assert again["status"] == "STARTED" and again["fencing_token"] == first["fencing_token"] + 1
    rendered = _one_json_line(
        _run(pool_dir, "render", "--task-id", mine.task_id, "--claim", again["claim_id"], "--token", str(again["fencing_token"]))[0]
    )
    assert rendered["status"] == "CAPSULE_READY"


def test_reclaim_points_the_worker_at_recover_and_recover_points_back_at_reclaim(tmp_path):
    """The two verbs must form a closed loop with no Python required in the middle."""

    pool_dir = tmp_path / "pool"
    task = _seed_task(pool_dir)
    _one_json_line(_run(pool_dir, "start", "--task-id", task.task_id, "--owner", "shell-loop", "--lease", "1")[0])
    time.sleep(1.5)

    found = _one_json_line(_run(pool_dir, "recover", "--owner", "shell-loop")[0])
    assert found["status"] == "NO_LIVE_LEASE"
    assert "reclaim" in found["hint"] and task.task_id in [row["task_id"] for row in found["expired_claims"]]

    reclaimed = _one_json_line(_run(pool_dir, "reclaim", "--task-id", task.task_id, "--actor", "shell-loop")[0])
    assert reclaimed["status"] == "LEASE_RECLAIMED"
    assert "start" in reclaimed["next_command"] and task.task_id in reclaimed["next_command"]


def test_drill_refuses_to_run_the_ghost_step_while_the_lease_is_still_live(tmp_path):
    """'resume' seconds after 'first' must stop and write nothing, not ghost-write legally.

    Found by running the drill back-to-back: with a live lease the ghost holds
    genuinely valid credentials, its submit succeeded, and the task moved to
    review -- the death scenario was consumed by a legitimate write and the run
    could never report the gate it exists to test.
    """

    pool_dir = tmp_path / "pool"
    state_path = tmp_path / "state.json"
    first = _run_drill("first", "--pool-dir", str(pool_dir), "--state", str(state_path))
    assert first.returncode == 0, (first.stdout[-300:], first.stderr[-400:])

    early = _run_drill(
        "resume",
        "--pool-dir",
        str(pool_dir),
        "--state",
        str(state_path),
        "--receipt",
        str(tmp_path / "receipt.json"),
    )
    assert early.returncode == 2, (early.stdout[-400:], early.stderr[-400:])
    row = json.loads(early.stdout.strip())
    assert row["status"] == "NOT_RESUMABLE"
    assert row["reason"] == "lease_still_live_ghost_would_be_legal"
    assert row["runtime_mutation"] is False
    assert row["lease_seconds_remaining"] and row["lease_seconds_remaining"] > 0
    assert not (tmp_path / "receipt.json").exists()

    sys.path.insert(0, str(REPO_ROOT))
    from core.task import TaskPool

    state = json.loads(state_path.read_text(encoding="utf-8"))
    held = TaskPool(str(pool_dir)).load_task(state["task_id"])
    assert held.status == "active" and held.claim_id == state["a_claim_id"]
    assert len(held.evidence) == 1, "the ghost write landed while the real lease was still live"

    # The same scratch pool then still completes once the lease has actually died.
    time.sleep(state.get("lease_seconds", 4) + 2)
    late = _run_drill(
        "resume",
        "--pool-dir",
        str(pool_dir),
        "--state",
        str(state_path),
        "--receipt",
        str(tmp_path / "receipt.json"),
    )
    assert late.returncode == 0, (late.stdout[-500:], late.stderr[-500:])
    done = json.loads(late.stdout.strip())
    assert done["status"] == "PASS" and done["final"]["status"] == "review"
    assert (tmp_path / "receipt.json").exists()


def _run_literal(command_line):
    """Run a command string exactly as the receipt handed it over (cmd.exe on Windows).

    The point is to test the *text*, not a re-assembled argv: if the capsule or a
    receipt ever emits a line a shell cannot execute, this is where it shows up.
    """

    import shutil

    if shutil.which("py") is None:  # pragma: no cover - host without the py launcher
        return None
    return subprocess.run(
        command_line,
        shell=True,
        # Started from outside the repo on purpose: the pasted line has to carry
        # its own cd, or the capsule's prefix is decoration.
        cwd=str(Path(os.environ.get("TEMP", ".")).resolve()),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        env=CHILD_ENV,
    )


def test_cli_start_receipt_hands_over_one_command_the_worker_can_paste(tmp_path):
    """Capability 2/11: after claiming, the next line comes from the receipt.

    A shell-only worker that must invent the render command itself is a worker
    that will get the quoting wrong; ``next_step`` is therefore the fully formed
    command, and this fixture runs it literally rather than parsing it.
    """

    pool_dir = tmp_path / "pool"
    task = _seed_task(pool_dir)
    started = _one_json_line(_run(pool_dir, "start", "--task-id", task.task_id, "--owner", "paste-w1", "--lease", "300")[0])
    assert started["status"] == "STARTED" and "next_step" in started

    assert f"--task-id {task.task_id}" in started["next_step"]
    assert f"--claim {started['claim_id']}" in started["next_step"]

    ran = _run_literal(started["next_step"])
    if ran is None:
        return
    assert ran.returncode == 0, (ran.stdout[-300:], ran.stderr[-500:])
    row = _one_json_line(ran)
    assert row["status"] == "CAPSULE_READY" and row["task_id"] == task.task_id
    # the pasted capsule really is the shell-port brief, not a Python recipe
    assert "ops.worker_capsule_cli" in row["capsule_text"] and "TaskPool.renew_lease" not in row["capsule_text"]


def test_cli_submit_receipt_points_at_the_next_task_without_claiming_it(tmp_path):
    """Capability 11: handing back must also say where the next job is.

    A worker that finishes and then waits has died, from ACE's point of view.
    The continuation is read off the same TaskPool and must not sweep leases,
    re-queue anything, or hand out credentials for a task it did not claim.
    """

    pool_dir = tmp_path / "pool"
    first = _seed_task(pool_dir, title="交回后要接着找的第一件", ref="continuation-first")
    second = _seed_task(pool_dir, title="交回后仍留在池里的第二件", ref="continuation-second")

    pending_before = _one_json_line(_run(pool_dir, "list-pending")[0])
    assert {row["task_id"] for row in pending_before["pending"]} == {first.task_id, second.task_id}

    started = _one_json_line(_run(pool_dir, "start", "--task-id", first.task_id, "--owner", "loop-w1", "--lease", "300")[0])

    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps({"summary": "第一件做完", "facts": ["可复算"], "transition": ""}), encoding="utf-8")
    submitted = _one_json_line(
        _run(
            pool_dir,
            "submit",
            "--task-id",
            first.task_id,
            "--claim",
            started["claim_id"],
            "--token",
            str(started["fencing_token"]),
            "--actor",
            "loop-w1",
            "--payload-file",
            str(payload_path),
        )[0]
    )
    assert submitted["status"] == "SUBMITTED", submitted

    continuation = submitted["continuation"]
    assert first.task_id not in continuation["next_ids"], continuation
    assert second.task_id in continuation["next_ids"], continuation
    # `first` is active now, so the pending face lost exactly that one row
    assert continuation["pending_now"] == pending_before["count"] - 1 == 1, continuation
    assert continuation["next_commands"][0].startswith("cd ") and "list-pending" in continuation["next_commands"][0]

    pending_after = _one_json_line(_run(pool_dir, "list-pending")[0])
    assert {row["task_id"] for row in pending_after["pending"]} == {second.task_id}
    assert "read_error" not in continuation or continuation["read_error"] is None

    sys.path.insert(0, str(REPO_ROOT))
    from core.task import TaskPool

    stored = TaskPool(str(pool_dir)).load_task(first.task_id)
    # an empty transition keeps it active under the same claim: the courtesy read
    # in the receipt must not have swept or re-issued anybody's lease
    assert stored is not None and stored.status == "active" and stored.claim_id == started["claim_id"]

    ran = _run_literal(continuation["next_commands"][0])
    if ran is None:
        return
    assert ran.returncode == 0, (ran.stdout[-300:], ran.stderr[-500:])
    assert _one_json_line(ran)["status"] == "LISTED"


def test_capsule_port_lines_survive_a_windows_cmd_paste(tmp_path):
    """Every command in the port face is pasted literally here, and must run.

    Two failures this fixture exists for, both found by running the real shell
    rather than by reading the text: ``<占位>`` is cmd input redirection (the first
    continuation dogfood exited 1 with no JSON, indistinguishable from a refusal),
    and prose sharing a line with a command gets pasted along with it -- the
    ``recover`` line once carried「（只读，……）」and argparse received
    「claim/token 一起还给你）」.  So: no shell metacharacters, holes are 【...】, and
    each command sits alone on its own indented line already carrying the prefix.
    """

    pool_dir = tmp_path / "pool"
    task = _seed_task(pool_dir)
    started = _one_json_line(
        _run(pool_dir, "start", "--task-id", task.task_id, "--owner", "paste-safe-w1", "--lease", "60")[0]
    )
    rendered = _one_json_line(
        _run(
            pool_dir,
            "render",
            "--task-id",
            task.task_id,
            "--claim",
            started["claim_id"],
            "--token",
            str(started["fencing_token"]),
        )[0]
    )
    text = rendered["capsule_text"]
    assert "== STOP ==" in text, "the port face must be inside the default budget, not past the cut"

    # cut at the next section header, whatever the port face's internal order is
    section = text.split("== RETURN PROTOCOL", 1)[1].split("\n== ", 1)[0]
    for noise in ("<", ">", "|", "`", "%"):
        assert noise not in section, noise
    assert "【" in section, "unfilled holes must be visible as 【...】"

    commands = [line.strip() for line in section.splitlines() if line.startswith("    ") and line.strip()]
    assert len(commands) == 6, commands
    holes = [line for line in commands if "【" in line]
    assert len(holes) == 2, holes  # submit and fail: only a file path and one choice are left to the worker
    # a command the worker can paste is a command that carries its own cd and pool
    assert all(line.startswith("cd ") and "--pool " in line for line in commands), commands

    ran = _run_literal(commands[0])  # 找下一件活 -- read-only, needs nothing filled in
    if ran is None:  # pragma: no cover - host without the py launcher
        return
    assert ran.returncode == 0, (ran.stdout[-300:], ran.stderr[-500:])
    assert _one_json_line(ran)["status"] == "LISTED"

    renewed = _run_literal(commands[1])  # 续租, credentials filled from the record
    assert renewed.returncode == 0, (renewed.stdout[-300:], renewed.stderr[-500:])
    row = _one_json_line(renewed)
    assert row["status"] == "RENEWED" and row["claim_id"] == started["claim_id"]

    found = _run_literal(commands[4])  # 忘了凭证
    assert found.returncode == 0, (found.stdout[-300:], found.stderr[-500:])
    leases = _one_json_line(found)
    assert leases["status"] == "LEASES_FOUND" and leases["leases"][0]["task_id"] == task.task_id
    assert leases["leases"][0]["next_command"].startswith("cd ") and "【" not in leases["leases"][0]["next_command"]

    # reclaim is fully filled too, and the lease is still live: the pasted line has
    # to reach the port and come back refused, instead of dying inside the shell
    stale = _run_literal(commands[5])
    assert stale.returncode == 3, (stale.stdout[-300:], stale.stderr[-500:])
    refused = _one_json_line(stale)
    assert refused["status"] == "REFUSED" and refused["reason"] == "capsule_lease_still_live"
    assert refused["runtime_mutation"] is False
