"""Does a staged delivery worker, given read access to the repository, produce
the deliverable?

This is the regression the A/B surfaced: staging the reduced instructions in a
scratch directory took the repository away from the model. A control run spent
its whole budget globbing an empty room and produced nothing.

The permission grant is scoped to one path -- read allowed, edit denied -- so
this checks the model can actually use it, and that it is narrow.
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(r"C:\tmp\ace_core")))

from ace_daemon import AceDaemon

repo = Path(r"C:\tmp\ace_core")
deliverable = "docs/READ_ACCESS_PROOF.md"
target = repo / deliverable
if target.is_file():
    target.unlink()

captured = {}

d = AceDaemon.__new__(AceDaemon)
d.base_dir = repo
d.task_pool = None
d._reuse_hint_for = lambda *a, **k: ""


def fake_run(capability, worker, **kwargs):
    staging = Path(kwargs["workspace"])
    config = staging / "opencode.json"
    captured["config"] = json.loads(config.read_text(encoding="utf-8"))
    captured["task"] = kwargs["task"]
    # Stand in for a model that reads the repo, then writes the deliverable.
    probe = repo / "core" / "miner_pool" / "miner_pool.py"
    captured["repo_readable"] = probe.is_file()
    (staging / "docs").mkdir(parents=True, exist_ok=True)
    (staging / deliverable).write_text(
        "# read access proof\n\nThe provider registry lives in core/miner_pool.\n",
        encoding="utf-8",
    )
    return {"success": True, "raw_output": "{}", "instruction_context_sha256": "x" * 64}


d.worker_router = SimpleNamespace(run=fake_run)

receipt = d._deliver_with_reduced_instructions(
    object(), Path(r"C:\tmp\ace_core\model_instructions"),
    required_path=deliverable, title="t", hypothesis="h", task_id="probe",
)

rules = captured["config"]["permissions"]
ok = True


def check(label, condition, detail=""):
    global ok
    ok = ok and condition
    print(f"[{'PASS' if condition else 'FAIL'}] {label}"
          f"{(': ' + detail) if detail else ''}")


check("deliverable placed", target.is_file())
if target.is_file():
    print("        content:", target.read_text(encoding="utf-8").strip()[:80])
    target.unlink()

by_action = {rule["action"]: rule for rule in rules}
check("external_directory allowed for the repo",
      by_action["external_directory"]["effect"] == "allow",
      by_action["external_directory"]["resource"])
check("read allowed for the repo",
      by_action["read"]["effect"] == "allow")
check("edit DENIED for the repo",
      by_action["edit"]["effect"] == "deny")
repo_posix = str(repo).replace("\\", "/").rstrip("/")
check("permission scope names only the repo",
      all(repo_posix in rule["resource"] for rule in rules))
check("the repo was reachable from staging", captured["repo_readable"])
check("task tells the model where the code is",
      "readable at" in captured["task"])

print("\n" + ("READ ACCESS GRANTED AND SCOPED" if ok else "PROBLEM ABOVE"))
sys.exit(0 if ok else 1)