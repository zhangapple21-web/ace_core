"""Regression: instruction staging is opt-in, and every call's real instruction
set is classified before a model is touched.

The CLI is the only OpenCode invocation face ACE has, so what a run is handed as
standing guidance has to be provable from the receipt. Two independent things
are pinned here:

1. Staging is opt-in and exact. Default is unchanged; a staged file is
   byte-identical to its source and hashed from the source, not the copy.
2. The egress gate covers the *effective* instruction set. OpenCode merges every
   AGENTS.md it can reach, so a gate that only looked at an explicitly staged
   file would miss the delivery stage, whose instructions arrive by ambient
   discovery with its cwd on the repository root.

Blocked calls start no subprocess and return a verdict naming the file, its
class, and the rule that refused. Unclassified is a refusal, not a shrug.
"""

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("ONEAPI_KEY", "test-key-for-routing-only")
os.environ.setdefault("ONEAPI_BASE_URL", "http://localhost:3000/v1")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from core.opencode_worker import OpenCodeWorker

MODEL = "opencode/mimo-v2.6-flash-free"

PROBE = r'''
import json, pathlib, sys

observed = pathlib.Path(sys.argv[1])
args = sys.argv[2:]

if "--version" in args:
    print("opencode v0.0.0-probe")
    raise SystemExit(0)

if any("failplease" in arg for arg in args):
    print("probe refused", flush=True)
    raise SystemExit(3)

cwd = pathlib.Path.cwd()
target = cwd / "AGENTS.md"
observed.mkdir(parents=True, exist_ok=True)
(observed / "observation.json").write_text(
    json.dumps({
        "cwd": str(cwd),
        "files": sorted(entry.name for entry in cwd.iterdir()),
        "agents_md": target.read_text(encoding="utf-8") if target.is_file() else None,
    }),
    encoding="utf-8",
)
print("probe ok")
'''


class Probe:
    """A stand-in CLI that records its working directory, outside the workspace.

    Also owns a fixture governance root, because classification now lives in a
    governed record rather than in a caller-supplied argument.
    """

    def __init__(self):
        self.root = Path(tempfile.mkdtemp(prefix="instruction_probe_"))
        self.workspace = self.root / "work"
        self.workspace.mkdir()
        self.observed = self.root / "observed"
        self.ace_root = self.root / "governance"
        (self.ace_root / "08_GOVERNANCE").mkdir(parents=True)
        script = self.root / "probe.py"
        script.write_text(PROBE, encoding="utf-8")
        launcher = self.root / "probe_cli.bat"
        launcher.write_text(
            f'@echo off\r\n"{sys.executable}" "{script}" "{self.observed}" %*\r\n',
            encoding="utf-8",
        )
        self.executable = str(launcher)

    # --- governance fixture ---
    def classify(self, *entries, receipts=()):
        gov = self.ace_root / "08_GOVERNANCE"
        (gov / "instruction_data_classes.json").write_text(
            json.dumps(
                {"version": "instruction-data-classes.v1", "entries": list(entries)}
            ),
            encoding="utf-8",
        )
        (gov / "sanitizer_receipts.jsonl").write_text(
            "".join(json.dumps(receipt) + "\n" for receipt in receipts),
            encoding="utf-8",
        )
        return self.ace_root

    @staticmethod
    def entry_for(path, data_class):
        return {
            "match": path.as_posix(),
            "data_class": data_class,
            "decided_by": "test",
            "decided_at": "2026-10-09",
        }

    def receipt_for(self, path, payload, data_class="PUBLIC"):
        # A sanitizer receipt asserts the *reduced* artifact, so the class it
        # carries must itself be egressable. Declaring the original
        # conditional class would re-trip the very rule the receipt exists to
        # satisfy.
        return {
            "receipt_id": "R-TEST-1",
            "acceptance": "ACCEPTANCE_VERIFIED",
            "path": path.as_posix(),
            "artifact_sha256": hashlib.sha256(payload).hexdigest(),
            "data_class": data_class,
            "sanitizer": "test",
            "issued_at": "2026-10-09",
        }

    def worker(self, **kwargs):
        kwargs.setdefault("ace_root", self.ace_root)
        return OpenCodeWorker(
            executable=self.executable, timeout_seconds=60, **kwargs
        )

    def observation(self):
        path = self.observed / "observation.json"
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def instruction_file(self):
        target = self.workspace / "AGENTS.md"
        return target.read_bytes() if target.is_file() else None

    def staged_path(self):
        return self.workspace / "AGENTS.md"


def _source(text="ACE-DEFAULT-INSTRUCTION-TEXT\n"):
    path = Path(tempfile.mkdtemp(prefix="instruction_source_")) / "AGENTS.md"
    path.write_text(text, encoding="utf-8")
    return path


# --- staging -----------------------------------------------------------------


def test_no_instruction_files_is_allowed():
    """The chat route's shape: isolated temp workspace, nothing to classify."""
    probe = Probe()
    receipt = probe.worker().run(
        task="ping", workspace=str(probe.workspace), model_order=[MODEL],
    )

    assert receipt["instruction_gate"] == "ALLOWED"
    assert receipt["instruction_context_state"] == "none"
    assert receipt["success"] is True


def test_default_mode_is_off_and_writes_nothing():
    probe = Probe()
    receipt = probe.worker().run(
        task="ping", workspace=str(probe.workspace), model_order=[MODEL],
    )

    assert receipt["success"] is True
    assert receipt["instruction_mode"] == "off"
    assert receipt["instruction_staged"] is False
    assert "instruction_source" not in receipt
    assert "instruction_sha256" not in receipt
    assert probe.instruction_file() is None
    assert probe.observation()["agents_md"] is None


def test_workspace_mode_hands_the_exact_source_text_to_the_cli():
    probe = Probe()
    nonce = "ACE-STAGED-INSTRUCTION-3F2A"
    source = _source(f"# runtime memory\nnonce: {nonce}\n")
    probe.classify(probe.entry_for(probe.staged_path(), "PUBLIC"))

    receipt = probe.worker(
        instruction_mode="workspace", instruction_source=str(source),
    ).run(task="ping", workspace=str(probe.workspace), model_order=[MODEL])

    assert receipt["success"] is True
    assert receipt["instruction_mode"] == "workspace"
    assert receipt["instruction_staged"] is True
    assert receipt["instruction_source"] == str(source)
    # Hash of the source bytes, so a truncated or altered copy cannot pass.
    assert receipt["instruction_sha256"] == hashlib.sha256(
        source.read_bytes()
    ).hexdigest()
    assert receipt["instruction_bytes"] == source.stat().st_size
    assert receipt["opencode_version"] == "opencode v0.0.0-probe"
    assert probe.instruction_file() == source.read_bytes()
    # The call surface really saw it, which is the whole point of staging.
    assert nonce in probe.observation()["agents_md"]


def test_workspace_mode_without_a_source_refuses_at_construction():
    with pytest.raises(ValueError, match="opencode_instruction_source_required"):
        OpenCodeWorker(instruction_mode="workspace")


def test_unknown_mode_and_source_without_mode_are_refused():
    with pytest.raises(ValueError, match="opencode_instruction_mode_unknown"):
        OpenCodeWorker(instruction_mode="always")
    with pytest.raises(ValueError, match="opencode_instruction_source_without_mode"):
        OpenCodeWorker(instruction_source=str(_source()))


def test_missing_source_refuses_before_any_subprocess():
    probe = Probe()
    missing = probe.root / "absent" / "AGENTS.md"

    with pytest.raises(ValueError, match="opencode_instruction_source_missing"):
        probe.worker(
            instruction_mode="workspace", instruction_source=str(missing),
        ).run(task="ping", workspace=str(probe.workspace), model_order=[MODEL])

    # No observation means the probe never ran: the refusal is not "the CLI
    # failed", it is "we did not call".
    assert probe.observation() is None


def test_staging_is_not_reported_as_work_the_model_did():
    probe = Probe()
    source = _source()
    probe.classify(probe.entry_for(probe.staged_path(), "PUBLIC"))

    receipt = probe.worker(
        instruction_mode="workspace", instruction_source=str(source),
    ).run(task="ping", workspace=str(probe.workspace), model_order=[MODEL])

    assert receipt["instruction_staged"] is True
    assert (probe.workspace / "AGENTS.md").is_file()
    assert receipt["changed"] is False


def test_instruction_provenance_survives_a_failed_call():
    probe = Probe()
    source = _source()
    probe.classify(probe.entry_for(probe.staged_path(), "PUBLIC"))

    receipt = probe.worker(
        instruction_mode="workspace", instruction_source=str(source),
    ).run(task="failplease", workspace=str(probe.workspace), model_order=[MODEL])

    assert receipt["success"] is False
    assert receipt["error"] == "opencode_all_models_failed"
    assert receipt["instruction_staged"] is True
    assert receipt["instruction_sha256"] == hashlib.sha256(
        source.read_bytes()
    ).hexdigest()


def test_staging_onto_itself_is_reuse_not_a_rewrite():
    """Source == workspace AGENTS.md is the delivery shape, not a copy job."""
    probe = Probe()
    live = probe.staged_path()
    body = "# production instructions\n"
    live.write_text(body, encoding="utf-8")
    probe.classify(probe.entry_for(live, "PUBLIC"))

    receipt = probe.worker(
        instruction_mode="workspace", instruction_source=str(live),
    ).run(task="ping", workspace=str(probe.workspace), model_order=[MODEL])

    assert receipt["instruction_reuse"] == "already_in_workspace"
    assert receipt["instruction_staged"] is False
    assert live.read_text(encoding="utf-8") == body


# --- egress gate -------------------------------------------------------------


def test_unclassified_instruction_file_blocks_before_any_subprocess():
    probe = Probe()
    (probe.workspace / "AGENTS.md").write_text("# found by discovery\n", encoding="utf-8")

    receipt = probe.worker().run(
        task="ping", workspace=str(probe.workspace), model_order=[MODEL],
    )

    assert receipt["success"] is False
    assert receipt["error"] == "opencode_instruction_gate_blocked"
    assert receipt["instruction_gate"] == "BLOCKED"
    assert any("unclassified" in reason for reason in receipt["instruction_gate_blocked"])
    assert probe.observation() is None


def test_local_only_classes_block_with_a_named_reason():
    probe = Probe()
    for data_class in ("PRIVATE", "CORE"):
        (probe.workspace / "AGENTS.md").write_text("text\n", encoding="utf-8")
        probe.classify(probe.entry_for(probe.staged_path(), data_class))

        receipt = probe.worker().run(
            task="ping", workspace=str(probe.workspace), model_order=[MODEL],
        )

        assert receipt["instruction_gate"] == "BLOCKED"
        assert any(
            data_class in reason for reason in receipt["instruction_gate_blocked"]
        )
    assert probe.observation() is None


def test_conditional_classes_need_a_live_sanitizer_receipt():
    probe = Probe()
    for data_class in ("CAPABILITY", "STRUCTURE"):
        (probe.workspace / "AGENTS.md").write_text("text\n", encoding="utf-8")
        probe.classify(probe.entry_for(probe.staged_path(), data_class))

        receipt = probe.worker().run(
            task="ping", workspace=str(probe.workspace), model_order=[MODEL],
        )

        assert receipt["instruction_gate"] == "BLOCKED"
        assert any(
            "sanitizer_receipt_required" in reason
            for reason in receipt["instruction_gate_blocked"]
        )
    assert probe.observation() is None


def test_a_valid_sanitizer_receipt_allows_a_conditional_class():
    probe = Probe()
    body = "reduced instruction text\n"
    (probe.workspace / "AGENTS.md").write_text(body, encoding="utf-8")
    probe.classify(
        receipts=[probe.receipt_for(probe.staged_path(), probe.staged_path().read_bytes())],
    )

    receipt = probe.worker().run(
        task="ping", workspace=str(probe.workspace), model_order=[MODEL],
    )

    assert receipt["instruction_gate"] == "ALLOWED"
    assert receipt["success"] is True
    basis = receipt["instruction_classes"][0]["basis"]
    assert basis == "sanitizer_receipt"


def test_sanitizer_receipt_goes_stale_when_the_file_changes():
    probe = Probe()
    target = probe.workspace / "AGENTS.md"
    target.write_text("version one\n", encoding="utf-8")
    probe.classify(
        receipts=[probe.receipt_for(target, target.read_bytes())],
    )

    target.write_text("version two, edited after the receipt\n", encoding="utf-8")

    receipt = probe.worker().run(
        task="ping", workspace=str(probe.workspace), model_order=[MODEL],
    )

    assert receipt["instruction_gate"] == "BLOCKED"
    assert any(
        "unclassified" in reason for reason in receipt["instruction_gate_blocked"]
    )
    assert probe.observation() is None


def test_public_label_does_not_excuse_credential_shaped_content():
    probe = Probe()
    (probe.workspace / "AGENTS.md").write_text(
        'api_key = "abcdefghijklmnopqrstuvwxyz012345"\n', encoding="utf-8",
    )
    probe.classify(probe.entry_for(probe.staged_path(), "PUBLIC"))

    receipt = probe.worker().run(
        task="ping", workspace=str(probe.workspace), model_order=[MODEL],
    )

    assert receipt["instruction_gate"] == "BLOCKED"
    assert any(
        "content_not_egressable" in reason
        for reason in receipt["instruction_gate_blocked"]
    )
    assert probe.observation() is None


def test_off_mode_still_records_the_instruction_set():
    """Delivery shape: cwd already carries AGENTS.md, mode is off, still proved."""
    probe = Probe()
    body = "# Runtime memory\n\nalready here\n"
    (probe.workspace / "AGENTS.md").write_text(body, encoding="utf-8")
    probe.classify(probe.entry_for(probe.staged_path(), "PUBLIC"))

    receipt = probe.worker().run(
        task="ping", workspace=str(probe.workspace), model_order=[MODEL],
    )

    assert receipt["instruction_staged"] is False
    assert receipt["instruction_context_state"] == "present"
    paths = [entry["path"] for entry in receipt["instruction_context_sources"]]
    assert str(probe.staged_path()) in paths
    entry = next(
        item for item in receipt["instruction_context_sources"]
        if item["path"] == str(probe.staged_path())
    )
    assert entry["sha256"] == hashlib.sha256(
        probe.staged_path().read_bytes()
    ).hexdigest()
    assert entry["origin"] == "workspace"


def test_context_never_reports_a_file_the_workspace_does_not_have():
    probe = Probe()
    receipt = probe.worker().run(
        task="ping", workspace=str(probe.workspace), model_order=[MODEL],
    )

    paths = [entry["path"] for entry in receipt["instruction_context_sources"]]
    assert str(probe.staged_path()) not in paths
    # Every reported path is either the global file or an ancestor-or-self of
    # the workspace: no unrelated file can join a prompt unnoticed.
    for path in paths:
        candidate = Path(path)
        assert candidate == probe.workspace or candidate in probe.workspace.parents or (
            candidate.parent == Path.home() / ".config" / "opencode"
        )


def test_context_hash_tracks_instruction_drift():
    """Two runs, one edited file: the receipt has to tell them apart."""
    probe = Probe()
    instruction = probe.staged_path()
    instruction.write_text("v1\n", encoding="utf-8")
    probe.classify(probe.entry_for(instruction, "PUBLIC"))

    first = probe.worker().run(
        task="ping", workspace=str(probe.workspace), model_order=[MODEL],
    )
    instruction.write_text("v2 revised\n", encoding="utf-8")
    second = probe.worker().run(
        task="ping", workspace=str(probe.workspace), model_order=[MODEL],
    )

    assert (
        first["instruction_context_sha256"] != second["instruction_context_sha256"]
    )


def test_miner_pool_route_stays_off(monkeypatch):
    """The chat route decided not to inject; keep that decision in code."""
    from core.miner_pool.providers.opencode_cli import OpenCodeCliProvider

    recorded = {}

    class FakeWorker:
        def __init__(self, **kwargs):
            recorded.update(kwargs)

        def run(self, **kwargs):
            return {
                "success": True,
                "attempts": [],
                "raw_output": json.dumps({"type": "text", "part": {"text": "pong"}}),
            }

    import core.opencode_worker as worker_module

    monkeypatch.setattr(worker_module, "OpenCodeWorker", FakeWorker)

    result = OpenCodeCliProvider().chat(
        messages=[{"role": "user", "content": "Reply pong."}],
        model="oneapi_free:mimo-v2.6-flash-free",
        timeout=30,
        data_boundary={"data_class": "PUBLIC"},
    )

    assert result["success"] is True, result
    assert recorded["instruction_mode"] == "off"


# --- a refusal has to stay readable through the production call chain ---------
# The gate is decided by the instruction set, so a block is not a flaky model
# and not an empty answer. These pin that it survives each layer that used to
# reduce it into an unexplained failure.


def _blocked_receipt():
    return {
        "success": False,
        "error": "opencode_instruction_gate_blocked",
        "attempts": [],
        "instruction_gate": "BLOCKED",
        "instruction_gate_blocked": ["local_only_class:/repo/AGENTS.md:PRIVATE"],
        "instruction_classes": [
            {
                "path": "/repo/AGENTS.md",
                "data_class": "PRIVATE",
                "basis": "registry",
            }
        ],
        "instruction_context_sources": [],
        "instruction_context_sha256": "0" * 64,
        "instruction_context_state": "present",
        "instruction_mode": "off",
        "instruction_staged": False,
    }


def test_gate_block_survives_the_delivery_verdict():
    from core.delivery_execution import worker_verdict

    verdict = worker_verdict(_blocked_receipt())

    assert verdict["ok"] is False
    assert verdict["error"] == "opencode_instruction_gate_blocked"
    # Reduced to ok/error this refusal would be unactionable: the receipt would
    # say a worker failed and not which file was refused or under which class.
    assert verdict["instruction_gate"] == "BLOCKED"
    assert verdict["instruction_gate_blocked"]
    assert verdict["instruction_classes"][0]["data_class"] == "PRIVATE"


def test_router_stops_at_a_gate_block_instead_of_falling_through():
    from core.opencode_worker import OPENCODE_MODELS
    from core.worker_router import WorkerCapability, WorkerRouter

    models = list(OPENCODE_MODELS.values())[:3]
    router = WorkerRouter([
        WorkerCapability(
            worker_id=f"w{index}", runtime="cli",
            capabilities=frozenset({"structured_readonly"}),
            metadata={"model": model, "fallback_rank": str(index)},
        )
        for index, model in enumerate(models)
    ])

    class BlockedWorker:
        calls = 0

        def run(self, **kwargs):
            BlockedWorker.calls += 1
            return dict(_blocked_receipt())

    result = router.run(
        "structured_readonly", BlockedWorker(),
        task="ping", workspace="unused",
    )

    assert result["instruction_gate"] == "BLOCKED"
    # One governance refusal, not three model failures wearing its name.
    assert BlockedWorker.calls == 1
    assert len(result["router_attempts"]) == 1
    assert result["failure_class"] == "instruction_gate_blocked"


def test_router_still_falls_through_for_an_ordinary_failure():
    from core.opencode_worker import OPENCODE_MODELS
    from core.worker_router import WorkerCapability, WorkerRouter

    models = list(OPENCODE_MODELS.values())[:2]
    router = WorkerRouter([
        WorkerCapability(
            worker_id=f"w{index}", runtime="cli",
            capabilities=frozenset({"structured_readonly"}),
            metadata={"model": model, "fallback_rank": str(index)},
        )
        for index, model in enumerate(models)
    ])

    class FailingWorker:
        calls = 0

        def run(self, **kwargs):
            FailingWorker.calls += 1
            return {"success": False, "error": "opencode_nonzero_exit", "attempts": []}

    router.run("structured_readonly", FailingWorker(), task="ping", workspace="unused")

    assert FailingWorker.calls == len(models)


def test_chat_route_reports_a_gate_block_with_its_verdict(monkeypatch):
    from core.miner_pool.providers.opencode_cli import OpenCodeCliProvider

    class BlockedWorker:
        def __init__(self, **kwargs):
            pass

        def run(self, **kwargs):
            return _blocked_receipt()

    import core.opencode_worker as worker_module

    monkeypatch.setattr(worker_module, "OpenCodeWorker", BlockedWorker)

    result = OpenCodeCliProvider().chat(
        messages=[{"role": "user", "content": "Reply pong."}],
        model="oneapi_free:mimo-v2.6-flash-free",
        timeout=30,
        data_boundary={"data_class": "PUBLIC"},
    )

    assert result["success"] is False
    assert result["error"] == "opencode_instruction_gate_blocked"
    # Not "opencode_empty_reply": an empty reply is what a blocked call looks
    # like from the outside, so the verdict is the only thing telling them apart.
    assert result["instruction_gate"] == "BLOCKED"
    assert result["instruction_gate_blocked"]