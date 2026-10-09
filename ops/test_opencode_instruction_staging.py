"""Regression: instruction staging is opt-in, exact, and fail-closed.

The CLI is the only OpenCode invocation face ACE has, so whatever a run is
handed as standing guidance has to be provable from the receipt. These tests
pin four things:

1. default stays "off" -- existing callers keep their exact behaviour;
2. workspace mode stages byte-identical source text, and the hash in the
   receipt is over those bytes, not over the copy;
3. a workspace-mode run with no readable source refuses *before* any subprocess
   starts, rather than quietly calling without guidance;
4. the staged file is ours, so it is never reported as work the model did.

The probe CLI reports what it actually found in its working directory, so a
passing test is evidence the real call surface sees the file -- not evidence
that we wrote it somewhere.
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
    """A stand-in CLI that records its working directory, outside the workspace."""

    def __init__(self):
        self.root = Path(tempfile.mkdtemp(prefix="instruction_probe_"))
        self.workspace = self.root / "work"
        self.workspace.mkdir()
        self.observed = self.root / "observed"
        script = self.root / "probe.py"
        script.write_text(PROBE, encoding="utf-8")
        launcher = self.root / "probe_cli.bat"
        launcher.write_text(
            f'@echo off\r\n"{sys.executable}" "{script}" "{self.observed}" %*\r\n',
            encoding="utf-8",
        )
        self.executable = str(launcher)

    def worker(self, **kwargs):
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


def _source(text="ACE-DEFAULT-INSTRUCTION-TEXT\n"):
    path = Path(tempfile.mkdtemp(prefix="instruction_source_")) / "AGENTS.md"
    path.write_text(text, encoding="utf-8")
    return path


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

    receipt = probe.worker(
        instruction_mode="workspace", instruction_source=str(source),
    ).run(task="ping", workspace=str(probe.workspace), model_order=[MODEL])

    assert receipt["instruction_staged"] is True
    assert (probe.workspace / "AGENTS.md").is_file()
    assert receipt["changed"] is False


def test_instruction_provenance_survives_a_failed_call():
    probe = Probe()
    source = _source()

    receipt = probe.worker(
        instruction_mode="workspace", instruction_source=str(source),
    ).run(task="failplease", workspace=str(probe.workspace), model_order=[MODEL])

    assert receipt["success"] is False
    assert receipt["error"] == "opencode_all_models_failed"
    assert receipt["instruction_staged"] is True
    assert receipt["instruction_sha256"] == hashlib.sha256(
        source.read_bytes()
    ).hexdigest()


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