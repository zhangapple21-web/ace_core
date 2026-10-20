"""A staged delivery worker must be able to read the repository it documents.

Staging the reduced instructions into a scratch directory fixed the egress
problem and introduced this one: the working directory held nothing but
AGENTS.md, so a delivery worker sent to document the provider registry globbed
an empty room until its budget ran out and produced nothing.

The fix is a permission grant written into the staging directory, scoped to one
path -- read allowed, edit denied -- because the model writes into its own
working directory and nowhere else. These tests pin the six properties that
have to hold, including that the scope names the repository and nothing else.
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ace_daemon import AceDaemon

REPO = Path(__file__).resolve().parents[1]
DELIVERABLE = "docs/READ_ACCESS_PROOF.md"


def _daemon_and_capture(tmp_path):
    """A daemon whose router records the staging directory it was handed."""
    daemon = AceDaemon.__new__(AceDaemon)
    daemon.base_dir = tmp_path
    daemon.task_pool = None
    daemon._reuse_hint_for = lambda *a, **k: ""
    captured = {}

    def fake_run(capability, worker, **kwargs):
        staging = Path(kwargs["workspace"])
        captured["staging"] = staging
        captured["task"] = kwargs.get("task", "")
        captured["config"] = json.loads(
            (staging / "opencode.json").read_text(encoding="utf-8"))
        (staging / "docs").mkdir(parents=True, exist_ok=True)
        (staging / DELIVERABLE).write_text(
            "# read access proof\n\nThe provider registry lives in core/miner_pool.\n",
            encoding="utf-8",
        )
        return {"success": True, "raw_output": "{}",
                "instruction_context_sha256": "x" * 64}

    daemon.worker_router = SimpleNamespace(run=fake_run)
    return daemon, captured


def _reduction(tmp_path):
    reduced = tmp_path / "model_instructions"
    reduced.mkdir(parents=True, exist_ok=True)
    (reduced / "AGENTS.md").write_text("reduced\n", encoding="utf-8")
    return reduced


def test_a_produced_artifact_lands_at_the_declared_path(tmp_path):
    daemon, _ = _daemon_and_capture(tmp_path)

    receipt = daemon._deliver_with_reduced_instructions(
        object(), _reduction(tmp_path), required_path=DELIVERABLE,
        title="t", hypothesis="h", task_id="probe",
    )

    placed = tmp_path / DELIVERABLE
    assert placed.is_file()
    assert "provider registry" in placed.read_text(encoding="utf-8")
    assert receipt["delivery_staging"]["artifact_placed"] is True


def test_the_repository_is_readable_and_not_writable(tmp_path):
    daemon, captured = _daemon_and_capture(tmp_path)

    daemon._deliver_with_reduced_instructions(
        object(), _reduction(tmp_path), required_path=DELIVERABLE,
        title="t", hypothesis="h", task_id="probe",
    )

    rules = {rule["action"]: rule for rule in captured["config"]["permissions"]}
    assert rules["external_directory"]["effect"] == "allow"
    assert rules["read"]["effect"] == "allow"
    assert rules["edit"]["effect"] == "deny"


def test_the_grant_names_only_the_repository(tmp_path):
    daemon, captured = _daemon_and_capture(tmp_path)

    daemon._deliver_with_reduced_instructions(
        object(), _reduction(tmp_path), required_path=DELIVERABLE,
        title="t", hypothesis="h", task_id="probe",
    )

    repo_posix = str(tmp_path).replace("\\", "/").rstrip("/")
    resources = [rule["resource"] for rule in captured["config"]["permissions"]]
    assert resources, "no permission was written at all"
    for resource in resources:
        # The grant is the repository path and nothing wider: not the drive
        # root, not the parent, not a leading wildcard.
        assert resource.startswith(repo_posix), resource
        assert resource[len(repo_posix):] == "/*", resource
        assert not repo_posix.startswith("*")


def test_the_task_tells_the_model_where_the_code_is(tmp_path):
    daemon, captured = _daemon_and_capture(tmp_path)

    daemon._deliver_with_reduced_instructions(
        object(), _reduction(tmp_path), required_path=DELIVERABLE,
        title="t", hypothesis="h", task_id="probe",
    )

    assert "readable at" in captured["task"]
    # Production interpolates the repository path as-is here, backslashes and
    # all, unlike the permission resource which it normalises.
    assert str(tmp_path) in captured["task"]


def test_the_staging_directory_does_not_outlive_the_attempt(tmp_path):
    daemon, captured = _daemon_and_capture(tmp_path)

    daemon._deliver_with_reduced_instructions(
        object(), _reduction(tmp_path), required_path=DELIVERABLE,
        title="t", hypothesis="h", task_id="probe",
    )

    assert not captured["staging"].exists()


def test_a_refused_call_still_leaves_no_staging_directory(tmp_path):
    daemon = AceDaemon.__new__(AceDaemon)
    daemon.base_dir = tmp_path
    daemon.task_pool = None
    daemon._reuse_hint_for = lambda *a, **k: ""
    seen = {}

    def blocking_run(capability, worker, **kwargs):
        seen["staging"] = Path(kwargs["workspace"])
        return {"success": False, "error": "opencode_instruction_gate_blocked",
                "instruction_gate": "BLOCKED"}

    daemon.worker_router = SimpleNamespace(run=blocking_run)

    receipt = daemon._deliver_with_reduced_instructions(
        object(), _reduction(tmp_path), required_path=DELIVERABLE,
        title="t", hypothesis="h", task_id="probe",
    )

    assert receipt["success"] is False
    assert receipt["delivery_staging"]["artifact_placed"] is False
    assert not (tmp_path / DELIVERABLE).exists()
    assert not seen["staging"].exists()