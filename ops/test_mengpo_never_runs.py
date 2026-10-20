"""Pin the Mengpo probe boundary and the unsafe production-runtime diagnosis.

The daemon currently runs only its isolated, legacy ``MengpoMemoryDecay``
archive probe. The destructive ``MengpoRuntime`` path is deliberately unwired.
These tests keep that distinction explicit:

1. ``MengpoAutoTrigger`` still has zero production call sites.
2. The legacy probe's ``MengpoMemoryDecay.forget()`` writes a graveyard
   tombstone but does not remove source memory; its empty ``affected_items`` is
   not proof of production forgetting.
3. ``MengpoRuntime`` adds a substitution check and is covered by isolated tests,
   but is not production-ready: it has no authorized canonical-store deletion
   owner and has not passed independent recovery, governance, or daemon-evidence
   review. Do not wire it into the daemon until those gates are satisfied.

The tests intentionally preserve the legacy liveness probe without granting the
new runtime production deletion authority.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from core.governance.mengpo import MengpoMemoryDecay

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ------------------------------------------------------------------ finding 1

def test_the_auto_trigger_has_no_call_sites():
    """MengpoAutoTrigger was written and never wired into anything.

    The check is for invocation syntax, not for a mention: a docstring
    explaining what the trigger is good evidence *about* the finding without
    being an invocation, and a grep that counts prose as a call site would
    report a live component the moment anyone wrote about it.
    """
    import re
    import subprocess

    repo = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        ["git", "-C", str(repo), "grep", "-n", "MengpoAutoTrigger", "--", "*.py"],
        capture_output=True, text=True, cwd=str(repo), check=False,
    )
    invocations = []
    for line in result.stdout.splitlines():
        if "class MengpoAutoTrigger" in line:
            continue  # the definition itself
        path, _, body = line.partition(":")
        lineno, _, body = body.partition(":")
        body = body.strip()
        # an import, a constructor call, or a subclass reference
        if re.search(r"\bMengpoAutoTrigger\s*\(", body) or \
                re.search(r"\bfrom\s+[\w.]+\s+import\s+.*MengpoAutoTrigger", body) or \
                re.search(r"\bimport\s+.*MengpoAutoTrigger", body):
            invocations.append(f"{path}:{lineno}: {body}")
    assert not invocations, f"the trigger is invoked from: {invocations}"


# ------------------------------------------------------------------ finding 2

def test_forget_writes_a_tombstone_but_leaves_the_body(tmp_path):
    """The live record: 2837 forgets, 2837 with affected_items empty.

    Pinned here rather than asserted from that file, so the defect is a property
    of the code and not of whatever one audit happened to see.
    """
    mengpo = MengpoMemoryDecay(
        graveyard_path=str(tmp_path / "graveyard"),
        lines_path=str(tmp_path / "lines.jsonl"),
        records_path=str(tmp_path / "records.jsonl"),
    )
    from core.governance.mengpo import ForgettingCandidate

    mengpo.forget(ForgettingCandidate(
        id="art-1", artifact="a noisy concept", artifact_type="concept",
        reason="noise", pollution_score=0.9, age_days=3, references=0),
        reason="noise")

    tombstone = tmp_path / "graveyard" / "concept_art-1.json"
    assert tombstone.exists(), "a tombstone is written"

    # the record carries affected_items, and it is empty: nothing was affected
    line = (tmp_path / "records.jsonl").read_text(encoding="utf-8").strip()
    record = json.loads(line)
    assert record["action"] == "forget"
    assert list(record.get("affected_items") or []) == [], (
        "the artifact is still in the store; only a tombstone was written"
    )


def test_mengpo_runtime_stays_unwired_until_rollback_gate_is_accepted():
    """A passed unit test must not silently turn into daemon deletion authority."""
    import ast

    repo = Path(__file__).resolve().parent.parent
    daemon_path = repo / "ace_daemon.py"
    source = daemon_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(daemon_path))

    runtime_references = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == "MengpoRuntime":
            runtime_references.append(f"name@{node.lineno}")
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                if alias.name == "MengpoRuntime":
                    runtime_references.append(f"import@{node.lineno}")
    assert not runtime_references, (
        "MengpoRuntime must remain out of the daemon until rollback and governance "
        f"gates are independently accepted: {runtime_references}"
    )

    probe = next(
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "_run_memory_governance_probe"
    )
    probe_names = {
        node.id for node in ast.walk(probe) if isinstance(node, ast.Name)
    }
    assert "MengpoMemoryDecay" in probe_names
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "forget"
        for node in ast.walk(probe)
    ), "the current liveness probe must keep exercising the legacy archive check"
    assert any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "ForgettingCandidate"
        and any(
            keyword.arg == "id"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value == "cycle-probe"
            for keyword in node.keywords
        )
        for node in ast.walk(probe)
    ), "the probe id must stay stable to avoid graveyard file accumulation"
    probe_source = ast.get_source_segment(source, probe) or ""
    assert '"production_integration": False' in probe_source
    assert '"probe_only": True' in probe_source
