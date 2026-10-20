"""The delivery stage must run where the reduced instructions are, not in the
repository root.

The regression is a change in where the model is pointed. The repository root
holds the PRIVATE runtime manual, so a delivery run rooted there is refused by
the egress gate -- correctly. The stage therefore stages a reduced instruction
file in a scratch directory, lets the model write there, and copies the declared
artifact back for verification.

These pin the three things that could silently break that: a blocked reduction
must produce no worker at all, a refused call must not place an artifact, and
only the declared path may be copied back.
"""

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ace_daemon import AceDaemon
from core.delivery_execution import DeliveryExecutor


class StubWorker:
    """Stands in for OpenCodeWorker; the executable check only needs a path."""

    executable = r"C:\nonexistent\opencode.exe"

    @staticmethod
    def models():
        return {}


def _daemon(tmp_path, repo):
    d = AceDaemon.__new__(AceDaemon)
    d.base_dir = repo
    d._delivery_runner_cache = None
    d.worker_router = None
    d._log_error = lambda *a, **k: None
    # _delivery_worker_runner rebuilds the router from the worker registry,
    # which would replace any router a test installs. Neutralise it so a
    # scripted router survives to the point where routing actually happens.
    d._ensure_worker_router = lambda worker: None
    # _reuse_hint_for reads the task pool; these tests exercise the staging
    # contract, not archive reuse.
    d.task_pool = None
    d._reuse_hint_for = lambda task_id, workspace: ""
    return d


def _task(required_path):
    return SimpleNamespace(
        task_id="probe",
        title="produce a note",
        hypothesis="it can be written",
        outputs={"delivery": {
            "required_path": required_path,
            "success_metric": "file_exists_nonempty",
        }},
    )


def test_a_blocked_reduction_yields_no_worker_at_all(tmp_path):
    """No usable reduction must not degrade into calling the model."""
    repo = tmp_path / "repo"
    (repo / "model_instructions").mkdir(parents=True)
    (repo / "AGENTS.md").write_text("private\n", encoding="utf-8")

    from core.instruction_boundary import REGISTRY_RELATIVE
    (repo / REGISTRY_RELATIVE.parent).mkdir(parents=True, exist_ok=True)
    (repo / REGISTRY_RELATIVE).write_text(
        '{"entries": [{"match": "repo/AGENTS.md", "data_class": "PRIVATE"}]}',
        encoding="utf-8",
    )

    daemon = _daemon(tmp_path, repo)
    # The reduction directory holds no AGENTS.md at all, so the gate has nothing
    # compliant to work with and the worker must not be built.
    assert daemon._delivery_instruction_dir() is None


def _reduction_repo(tmp_path, body="reduced\n"):
    """A repository whose reduced instruction file is covered by a receipt.

    The reduction is judged where it will actually be staged -- outside the
    repository -- so a receipt binding the reduction must be hash-based rather
    than tied to the path it happened to be written to.
    """
    import hashlib
    import json

    repo = tmp_path / "repo"
    reduced = repo / "model_instructions"
    reduced.mkdir(parents=True)
    (reduced / "AGENTS.md").write_text(body, encoding="utf-8")

    source = tmp_path / "source" / "AGENTS.md"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text("private original with a passphrase: hunter2\n", encoding="utf-8")

    from core.instruction_boundary import REGISTRY_RELATIVE
    (repo / REGISTRY_RELATIVE.parent).mkdir(parents=True, exist_ok=True)
    (repo / REGISTRY_RELATIVE).write_text(json.dumps({"entries": [
        {"match": "source/AGENTS.md", "data_class": "PRIVATE"},
    ]}), encoding="utf-8")
    (repo / REGISTRY_RELATIVE.parent / "sanitizer_receipts.jsonl").write_text(
        json.dumps({
            "receipt_id": "R-TEST-RED",
            "acceptance": "ACCEPTANCE_VERIFIED",
            "path": str(reduced / "AGENTS.md"),
            "source_path": str(source),
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "artifact_sha256": hashlib.sha256((reduced / "AGENTS.md").read_bytes()).hexdigest(),
            "data_class": "PUBLIC",
        }) + "\n",
        encoding="utf-8",
    )
    return repo, reduced


def test_a_valid_reduction_is_accepted_as_the_instruction_dir(tmp_path):
    repo, reduced = _reduction_repo(tmp_path)
    daemon = _daemon(tmp_path, repo)
    assert daemon._delivery_instruction_dir() == reduced


def test_a_refused_call_places_no_artifact(tmp_path):
    """The gate blocks, so nothing is copied back and nothing is fabricated."""
    repo = tmp_path / "repo"
    reduced = repo / "model_instructions"
    reduced.mkdir(parents=True)
    (reduced / "AGENTS.md").write_text("reduced\n", encoding="utf-8")

    from core.instruction_boundary import REGISTRY_RELATIVE
    (repo / REGISTRY_RELATIVE.parent).mkdir(parents=True, exist_ok=True)
    (repo / REGISTRY_RELATIVE).write_text(
        '{"entries": [{"match": "model_instructions/AGENTS.md", '
        '"data_class": "PUBLIC"}]}',
        encoding="utf-8",
    )

    daemon = _daemon(tmp_path, repo)
    called = {}

    def fake_router_run(capability, worker, **kwargs):
        called.update(kwargs)
        return {
            "success": False,
            "error": "opencode_instruction_gate_blocked",
            "instruction_gate": "BLOCKED",
            "instruction_gate_blocked": ["local_only_class:x:PRIVATE"],
        }

    daemon.worker_router = SimpleNamespace(run=fake_router_run)

    receipt = daemon._deliver_with_reduced_instructions(
        StubWorker(), reduced, required_path="docs/NOTE.md",
        title="t", hypothesis="h", task_id="probe",
    )

    assert receipt["success"] is False
    assert receipt["delivery_staging"]["artifact_placed"] is False
    assert not (repo / "docs" / "NOTE.md").exists()
    assert not Path(called["workspace"]).exists(), "staging dir must be removed"
    # The failure travelled through intact rather than becoming "no worker".
    assert receipt["instruction_gate"] == "BLOCKED"


def test_a_produced_artifact_is_copied_back_to_the_declared_path(tmp_path):
    repo, reduced = _reduction_repo(tmp_path)
    daemon = _daemon(tmp_path, repo)
    seen = {}

    def fake_router_run(capability, worker, **kwargs):
        # Write the deliverable inside the staging workspace, plus a stray file
        # that must not be copied back.
        staging = Path(kwargs["workspace"])
        (staging / "docs").mkdir(parents=True, exist_ok=True)
        (staging / "docs" / "NOTE.md").write_text("delivered\n", encoding="utf-8")
        (staging / "docs" / "STRAY.md").write_text("unrequested\n", encoding="utf-8")
        seen.update(kwargs)
        return {"success": True, "raw_output": "{}", "instruction_context_sha256": "x" * 64}

    daemon.worker_router = SimpleNamespace(run=fake_router_run)

    receipt = daemon._deliver_with_reduced_instructions(
        StubWorker(), reduced, required_path="docs/NOTE.md",
        title="t", hypothesis="h", task_id="probe",
    )

    assert (repo / "docs" / "NOTE.md").read_text(encoding="utf-8") == "delivered\n"
    assert not (repo / "docs" / "STRAY.md").exists(), "only the declared path may be copied"
    assert receipt["delivery_staging"]["artifact_placed"] is True
    assert not Path(seen["workspace"]).exists()


def test_a_workspace_escaping_path_is_refused(tmp_path):
    repo = tmp_path / "repo"
    reduced = repo / "model_instructions"
    reduced.mkdir(parents=True)
    (reduced / "AGENTS.md").write_text("reduced\n", encoding="utf-8")

    daemon = _daemon(tmp_path, repo)
    daemon.worker_router = SimpleNamespace(
        run=lambda *a, **k: pytest.fail("must not call the model for an escaping path"),
    )

    receipt = daemon._deliver_with_reduced_instructions(
        StubWorker(), reduced, required_path="../escape.md",
        title="t", hypothesis="h", task_id="probe",
    )

    assert receipt["success"] is False
    assert receipt["error"] == "delivery_path_escapes_workspace"


def test_the_executor_still_verifies_against_the_repository(tmp_path):
    """Placing the artifact is not delivery; verification must still find it."""
    repo, reduced = _reduction_repo(tmp_path)
    daemon = _daemon(tmp_path, repo)

    def fake_router_run(capability, worker, **kwargs):
        staging = Path(kwargs["workspace"])
        (staging / "docs").mkdir(parents=True, exist_ok=True)
        (staging / "docs" / "NOTE.md").write_text("delivered\n", encoding="utf-8")
        return {"success": True, "raw_output": "{}", "instruction_context_sha256": "x" * 64}

    daemon.worker_router = SimpleNamespace(run=fake_router_run)
    runner = daemon._delivery_worker_runner()
    assert callable(runner)

    outcome = DeliveryExecutor(repo, worker_runner=runner).execute(
        _task("docs/NOTE.md"),
    )

    assert outcome["status"] == "DELIVERED"
    assert outcome["verification"]["satisfied"] is True