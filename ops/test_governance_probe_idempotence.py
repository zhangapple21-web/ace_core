# RQ-20261006-013 regression: the governance probe must not accumulate files.
#
# Before the fix, _run_memory_governance_probe built its ForgettingCandidate
# with a timestamped id, and MengpoMemoryDecay.forget() derives the graveyard
# filename from that id. The probe therefore wrote one new
# research_probe_cycle-probe-<timestamp>.json per cycle: about 250 files a
# day, 1070 in five days, inside the governance graveyard whose whole purpose
# is to hold the civilization's forgetting evidence. It also pushed the
# working tree's untracked count up and slowed any scan of that directory.
#
# A stable id rewrites a single file. The probe still runs, still proves the
# archive path works, and its forgotten_at becomes the probe's liveness time.
import ast
import glob
import json
import os
import tempfile

ADMISSION = {
    "source_type": "maintenance",
    "source_ref": "ops/test_governance_probe_idempotence.py",
    "why_now": "regression for probe accumulation in the governance graveyard",
    "evidence": ["graveyard held 1070 cycle-probe files over five days"],
    "expected_result": "one stable probe file, no per-cycle growth",
    "verification_method": "pytest plus a live daemon measurement",
    "risk": "low: test fixture",
    "estimated_scope": "single-test",
}


def test_probe_id_is_stable_not_timestamped():
    source = open("ace_daemon.py", encoding="utf-8").read()
    assert 'ForgettingCandidate(id="cycle-probe"' in source, (
        "the probe must use a stable id so one file is rewritten"
    )
    assert "cycle-probe-{datetime.now()" not in source, (
        "a timestamped probe id reintroduces per-cycle files"
    )


def test_mengpo_writes_one_file_per_stable_id():
    """Prove the filename really is derived from the id, so a stable id is one file."""
    from core.governance.mengpo import ForgettingCandidate, MengpoMemoryDecay

    with tempfile.TemporaryDirectory() as td:
        graveyard = os.path.join(td, "graveyard")
        records = os.path.join(td, "records.jsonl")
        lines = os.path.join(td, "lines.jsonl")
        engine = MengpoMemoryDecay(
            graveyard_path=graveyard,
            lines_path=lines,
            records_path=records,
        )
        candidate = ForgettingCandidate(
            id="cycle-probe",
            artifact="ACE_CYCLE_GOVERNANCE_PROBE",
            artifact_type="research_probe",
            reason="isolated non-production archive verification",
            pollution_score=MengpoMemoryDecay.POLLUTION_THRESHOLD,
            age_days=0,
            references=0,
            alternatives_exist=True,
            is_core=False,
        )
        for _ in range(5):
            assert engine.forget(candidate, reason=candidate.reason) is True
        files = glob.glob(os.path.join(graveyard, "*.json"))
        assert len(files) == 1, f"five cycles must leave one file, found {len(files)}"
        payload = json.loads(open(files[0], encoding="utf-8").read())
        assert payload["artifact"] == "ACE_CYCLE_GOVERNANCE_PROBE"
        assert payload["forgotten_at"], "the receipt must stay observable"


def test_probe_fixture_admission_is_complete():
    """Guards the fixture itself so the test cannot silently degrade."""
    for field in ADMISSION:
        assert ADMISSION[field], f"admission field {field} must be non-empty"