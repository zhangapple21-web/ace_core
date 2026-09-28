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


def _seed_task(pool_dir, title="CLI 承载演练"):
    sys.path.insert(0, str(REPO_ROOT))
    from core.task import TaskPool

    pool = TaskPool(str(pool_dir))
    return pool.create_task(
        title,
        hypothesis="shell worker 可以完成任务",
        creator="cli",
        complexity="complex",
        tags=["research"],
        admission=dict(ADMISSION),
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
