"""The receipt has to separate three kinds of fact, and it has to keep the kinds apart.

The temptation with an identity receipt is to let it imply more than it can check:
"here is the code" sliding into "here is the code the process is running". The
tests below exist mostly to keep that slide from happening silently, and one of
them enforces the property this file was written to protect - recording identity
must not change the git status it is reporting.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from ops.runtime_identity_receipt import (  # noqa: E402
    LIFECYCLE_FILES,
    RECEIPT_RELPATH,
    build_receipt,
    write_receipt,
)

EMPTY_ANCHORS = {"anchor_set_sha256": None, "reason_codes": []}


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True,
    ).stdout


def _commit(root: Path, message: str = "base") -> None:
    _git(root, "-c", "user.email=t@t", "-c", "user.name=t",
         "commit", "-qm", message)


def _root(tmp_path: Path, *, gitignore: str | None = None) -> Path:
    root = tmp_path / "repo"
    (root / "core").mkdir(parents=True)
    for relative in LIFECYCLE_FILES:
        (root / relative).write_text("x = 1\n", encoding="utf-8")
    if gitignore is not None:
        (root / ".gitignore").write_text(gitignore, encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)
    _git(root, "add", "-A")
    _commit(root)
    return root


def _process(pid: int, *, started: float | None = 1000.0) -> dict:
    return {
        "pid": pid,
        "session_id": 0,
        "executable": r"C:\...\pythonw.exe",
        "command_line": r'pythonw.exe "C:\tmp\ace_core\ace.py" daemon --serve',
        "creation_time_raw": "ignored-in-test",
        "creation_time_epoch": started,
    }


def _receipt(root: Path, *, processes, task=None, anchors=None) -> dict:
    return build_receipt(
        root,
        processes=processes,
        task_definition=task if task is not None else {"available": False},
        anchors=anchors if anchors is not None else EMPTY_ANCHORS,
    )


def test_the_receipt_records_disk_facts_live_observation_and_its_own_limits(tmp_path):
    root = _root(tmp_path)
    receipt = _receipt(
        root,
        processes=[_process(4242)],
        task={"available": True, "task": "ACE_Daemon_Boot",
              "command": r"C:\...\pythonw.exe",
              "arguments": r'"C:\tmp\ace_core\ace.py" daemon --serve',
              "working_directory": r"C:\tmp\ace_core", "logon_type": "S4U",
              "user_id": "Administrator", "run_level": "Limited"},
    )

    # persisted facts about the disk
    assert len(receipt["code"]["git"]["head"] or "") == 40
    assert receipt["code"]["git"]["dirty"] is False
    for relative in LIFECYCLE_FILES:
        facts = receipt["code"]["lifecycle_files"][relative]
        assert facts["worktree_matches_head"] is True, relative
        assert len(facts["worktree_git_blob"]) == 40, relative

    # live observation of the process and of the registered intent
    assert receipt["process"]["observed"] is True
    assert receipt["process"]["session_id"] == 0
    assert receipt["definition"]["logon_type"] == "S4U"
    assert receipt["definition_matches_live_command_line"] is True

    # and the limits travel with the receipt rather than being left unsaid
    limits = " ".join(receipt["unproven"])
    assert "imported" in limits
    assert "the process was started by the named task" in limits


def test_an_uncommitted_edit_is_a_blob_mismatch_and_a_separate_mtime_flag(tmp_path):
    """Two different facts, deliberately not collapsed into one field.

    The blob comparison is about the file versus HEAD. `changed_after_process_start`
    is about the file versus a clock. Neither one says what the running process
    imported, which is why the unproven list has to name that.
    """
    root = _root(tmp_path)
    (root / "core" / "observation.py").write_text("x = 2\n", encoding="utf-8")

    receipt = _receipt(root, processes=[_process(4242, started=1000.0)])
    facts = receipt["code"]["lifecycle_files"]["core/observation.py"]

    assert facts["worktree_matches_head"] is False
    assert receipt["code"]["git"]["dirty"] is True
    assert any("core/observation.py" in entry
               for entry in receipt["code"]["git"]["tracked_modified"])
    assert facts["changed_after_process_start"] is True

    # the file that did not change stays clean, so the fields are not sticky
    other = receipt["code"]["lifecycle_files"]["core/observation_to_task.py"]
    assert other["worktree_matches_head"] is True


def test_no_running_process_is_recorded_as_an_absence_not_guessed(tmp_path):
    root = _root(tmp_path)
    receipt = _receipt(root, processes=[])

    assert receipt["process"]["observed"] is False
    assert receipt["process"]["pid"] is None
    assert receipt["process"]["instance_count"] == 0
    assert receipt["join"]["pids_agree"] is False
    # no process start to compare against -> the question is left unanswered
    assert receipt["code"]["lifecycle_files"]["core/observation.py"][
        "changed_after_process_start"] is None
    assert receipt["definition_matches_live_command_line"] is None


def test_a_pid_that_disagrees_with_the_lock_is_not_reported_as_agreement(tmp_path):
    """The join is the point: a receipt that cannot disagree proves nothing."""
    root = _root(tmp_path)
    memory = root / "06_RUNTIME" / "ace" / "data" / "memory"
    memory.mkdir(parents=True)
    (memory / ".daemon.lock").write_text(
        json.dumps({"pid": 111, "run_id": "r1", "token": "111:1", "created_at": 1.0}),
        encoding="utf-8")
    (memory / "heartbeat.json").write_text(
        json.dumps({"pid": 222, "run_id": "r2", "last_beat": "2026-01-01T00:00:00",
                    "status": "alive"}), encoding="utf-8")

    receipt = _receipt(root, processes=[_process(333)])
    assert receipt["process"]["pid"] == 333
    assert receipt["join"]["lock_pid"] == 111
    assert receipt["join"]["heartbeat_pid"] == 222
    assert receipt["join"]["pids_agree"] is False


def test_a_matching_pid_family_is_reported_as_agreement(tmp_path):
    root = _root(tmp_path)
    memory = root / "06_RUNTIME" / "ace" / "data" / "memory"
    memory.mkdir(parents=True)
    (memory / ".daemon.lock").write_text(
        json.dumps({"pid": 555, "run_id": "r1", "token": "555:1", "created_at": 1.0}),
        encoding="utf-8")
    (memory / "heartbeat.json").write_text(
        json.dumps({"pid": 555, "run_id": "r1", "last_beat": "2026-01-01T00:00:00",
                    "status": "alive"}), encoding="utf-8")
    (memory / "daemon_state.json").write_text(
        json.dumps({"pid": 555, "run_id": "r1", "run_started_at": "2026-01-01T00:00:00",
                    "loaded_anchor_set_sha256": "a" * 64}), encoding="utf-8")

    receipt = _receipt(root, processes=[_process(555)],
                       anchors={"anchor_set_sha256": "a" * 64, "reason_codes": []})
    assert receipt["join"]["pids_agree"] is True
    assert receipt["join"]["anchors_agree"] is True


def test_an_anchor_mismatch_is_recorded_as_disagreement(tmp_path):
    """The daemon's self-report versus a fresh read of the same anchors.

    This is the join to post-start disk changes: if they differ, the motherplate
    changed after the process loaded it, whatever the file mtimes say.
    """
    root = _root(tmp_path)
    memory = root / "06_RUNTIME" / "ace" / "data" / "memory"
    memory.mkdir(parents=True)
    (memory / "daemon_state.json").write_text(
        json.dumps({"pid": 555, "loaded_anchor_set_sha256": "a" * 64}), encoding="utf-8")

    receipt = _receipt(root, processes=[_process(555)],
                       anchors={"anchor_set_sha256": "b" * 64, "reason_codes": []})
    assert receipt["join"]["loaded_anchor_set_sha256"] == "a" * 64
    assert receipt["join"]["current_anchor_set_sha256"] == "b" * 64
    assert receipt["join"]["anchors_agree"] is False


def test_writing_the_receipt_does_not_change_the_git_status_it_reports(tmp_path):
    """The property this file was written to protect, stated as a test.

    The receipt reports the dirty flag. If it landed in a tracked path it would
    turn every later receipt dirty and destroy the signal it just recorded, so it
    goes to a git-ignored runtime path and this test holds that in place.
    """
    root = _root(tmp_path, gitignore="06_RUNTIME/ace/\n")
    before = _git(root, "status", "--porcelain")

    receipt = _receipt(root, processes=[_process(4242)])
    path = write_receipt(root, receipt)

    assert path == root / RECEIPT_RELPATH
    assert path.is_file()
    assert _git(root, "status", "--porcelain") == before, (
        "recording identity changed the identity it reports"
    )
    assert json.loads(path.read_text(encoding="utf-8"))["schema"] == (
        "ace.runtime_identity_receipt.v1")


def test_the_registered_invocation_writes_the_snapshot(tmp_path, capsys, monkeypatch):
    """The tick runs every entry as `--root <root> --json`, then judges the entry's
    snapshot by age.

    This test exists because the first version of this file failed it in production:
    --json meant "print instead of writing", so the hourly tick ran the entry, saw
    rc=0, and judged a receipt that had never been rewritten. The measured symptom
    was a snapshot still 3.4 minutes old and bearing the previous manual run's
    timestamp. Green, silent, and producing nothing - which is the failure this
    repository keeps having to name. An entry asked to run produces its artifact;
    printing is extra.
    """
    import ops.runtime_identity_receipt as receipt_module

    root = _root(tmp_path)
    path = root / RECEIPT_RELPATH
    assert not path.is_file()

    monkeypatch.setattr(receipt_module, "observe_processes", lambda: [])
    monkeypatch.setattr(receipt_module, "observe_task_definition",
                        lambda task_name=receipt_module.DAEMON_TASK: {"available": False})

    assert receipt_module.main(["--root", str(root), "--json"]) == 0
    assert path.is_file(), "the tick's own invocation must produce the snapshot"
    printed = json.loads(capsys.readouterr().out)
    assert printed["schema"] == "ace.runtime_identity_receipt.v1"


def test_print_only_reads_without_recording(tmp_path, capsys, monkeypatch):
    """Reading the receipt must not be the same act as recording one."""
    import ops.runtime_identity_receipt as receipt_module

    root = _root(tmp_path)
    path = root / RECEIPT_RELPATH

    monkeypatch.setattr(receipt_module, "observe_processes", lambda: [])
    monkeypatch.setattr(receipt_module, "observe_task_definition",
                        lambda task_name=receipt_module.DAEMON_TASK: {"available": False})

    assert receipt_module.main(["--root", str(root), "--print-only"]) == 0
    assert not path.is_file()
    assert json.loads(capsys.readouterr().out)["schema"] == "ace.runtime_identity_receipt.v1"
