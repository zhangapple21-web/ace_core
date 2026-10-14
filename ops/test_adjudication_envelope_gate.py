"""CAN vs MAY, wired where judgment becomes a state transition.

`validate_intent_envelope` existed, was listed in mirror_constitution's
__all__, and was called by one test file. The gate that keeps an
interpretation layer from becoming an execution authorization was never in the
path it describes. These tests pin the wiring, and pin the two properties that
make it a gate rather than a decoration:

  it actually runs   every non-HOLD ruling builds an envelope and records the
                     result in the receipt, so the boundary is auditable
  it refuses to act  an envelope carrying authority it must not have stops the
                     action instead of proceeding on a judgment that booked a
                     right
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.autonomous_adjudication import _envelope_check  # noqa: E402


def test_a_ruling_envelope_carries_no_authority():
    """The envelope is the CAN side; every authority flag must be False."""
    check = _envelope_check("RULE", "deliberation converged: CLOSE")
    assert check is not None
    assert check["valid"] is True, check
    assert check["side_effects"]["execution_authorized"] is False
    assert check["side_effects"]["persistent_write"] is False


def test_a_hold_needs_no_envelope():
    """Not acting requires no authorization to check."""
    assert _envelope_check("HOLD", "deliberation did not converge") is None


def test_an_envelope_claiming_execution_authority_is_refused():
    """A judgment that books a right is a defect, not a ruling.

    This is the case the gate exists for: the interpretation layer booking
    itself execution authority. The check must say so, and the caller must
    stop rather than proceed on it.
    """
    from core.mirror_constitution import (
        build_intent_envelope,
        validate_intent_envelope,
    )

    forged = build_intent_envelope(
        intent_kind="OBSERVATION",
        claim="close it",
        source_scope="VERIFIED_EVIDENCE",
        source_refs=["contract:x"],
    )
    forged["authority"]["execution_authorized"] = True
    check = validate_intent_envelope(forged)
    assert check["valid"] is False
    assert "intent_authority_execution_authorized_must_be_false" in check["errors"]


def test_the_gate_is_wired_not_merely_defined():
    """A gate nothing calls is decoration - the defect that hid this one."""
    import subprocess

    from pathlib import Path

    repo = Path(__file__).resolve().parent.parent
    result = subprocess.run(
        ["git", "-C", str(repo), "grep", "-n", "validate_intent_envelope", "--", "*.py"],
        capture_output=True, text=True, cwd=str(repo),
    )
    hits = [line for line in result.stdout.splitlines() if line.strip()]
    production = [h for h in hits
                  if "core/mirror_constitution.py" not in h
                  and not h.startswith("ops/test_")]
    assert production, (
        "validate_intent_envelope is still called by nothing in production: "
        f"{hits}"
    )


def test_a_receipt_records_the_envelope_check(tmp_path):
    """The boundary has to be auditable, not merely asserted.

    The receipt lands in 08_GOVERNANCE, so the fixture must load the real OWNERS
    table: an invented empty one would refuse the write for the wrong reason and
    pin the wrong defect.
    """
    import shutil

    from core.autonomous_adjudication import _write_receipt

    root = tmp_path / "repo"
    shutil.copytree(
        Path(__file__).resolve().parent.parent / "04_PROTOCOLS", root / "04_PROTOCOLS",
        ignore=shutil.ignore_patterns("*.pyc"))

    class _Task:
        task_id = "RQ-X"

    check = _envelope_check("RULE", "converged")
    receipt = _write_receipt(root, _Task(), {"task_id": "RQ-X"}, [],
                             None, "RULE", "converged", check)

    stored = receipt["intent_envelope_check"]
    assert stored["valid"] is True
    assert stored["side_effects"]["execution_authorized"] is False
    assert stored["side_effects"]["persistent_write"] is False
    # and it survives a round trip to disk, because that is what a reader sees
    on_disk = json.loads(
        (root / "08_GOVERNANCE" / "autonomous_adjudication" / "receipts"
         / f"{receipt['receipt_id']}.json").read_text(encoding="utf-8"))
    assert on_disk["intent_envelope_check"]["valid"] is True
