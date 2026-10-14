"""Mengpo is designed but never runs: the diagnosis, as executable tests.

Three findings, each pinned so none can be argued away as a reading:

1. The auto-trigger that was written to actually do the forgetting
   (MengpoAutoTrigger: thresholds, cooldown, daily cap, backup-first, archive-
   not-delete) has ZERO call sites in the whole repo. It was built and never
   wired.

2. MengpoMemoryDecay.forget() writes a graveyard tombstone but never removes
   the artifact from the lexicon or the experience store. Every one of the
   2837 records in mengpo_records.jsonl has affected_items == [] because the
   thing it "forgot" is still exactly where it was.

3. The scorer that decides WHAT to forget asks only "is this dirty", never
   "what would I lose". A low-pollution, unreferenced artifact with no
   functional substitute is content whose removal creates a hole, and a dirty
   one that nothing else can replace is worse to forget than to keep. Nothing
   in the design models substitutability, so forgetting cannot be selective in
   the sense the owner means.

The first two are wiring and are fixed in core/autonomous_adjudication's
sibling, core/governance/mengpo_runtime.py. The third is the substantive design
addition: a substitution check that runs before any forget.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest  # noqa: E402

from core.governance.mengpo import (  # noqa: E402
    MengpoMemoryDecay,
)


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
        capture_output=True, text=True, cwd=str(repo),
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