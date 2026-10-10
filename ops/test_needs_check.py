# The system says what it needs: one active record per need, none per cycle.
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _daemon(tmp_path, seeds=()):
    from core.observation import RuntimeObserver
    from ace_daemon import AceDaemon

    root = Path(tmp_path)
    inbox = root / "07_SANDBOX" / "free_research" / "inbox"
    inbox.mkdir(parents=True)
    for name, payload in seeds:
        (inbox / name).write_text(json.dumps(payload), encoding="utf-8")
    daemon = AceDaemon.__new__(AceDaemon)
    daemon.base_dir = root
    daemon.config = {"runtime": {"free_zone_model_shift": {"enabled": True}}}
    daemon.state = {}
    daemon.runtime_observer = RuntimeObserver(str(root / "observations"))
    daemon._log_error = lambda *a, **k: None
    return daemon


def _seed(name="s.json"):
    import hashlib

    body = {
        "contract_version": "ace.semantic_seed.v1",
        "source_ref": "x", "source_snapshot_hash": "a" * 64,
        "source_kind": "f", "extracted_mechanism": "m", "ace_symptom": "s",
        "transfer_hypothesis": "h", "counterexample_question": "q",
        "next_verification": "v", "local_evidence_refs": [],
        "external_evidence_refs": [], "lineage": ["x"],
    }
    return name, body


def test_empty_inbox_records_one_named_need(tmp_path):
    daemon = _daemon(tmp_path)
    assert daemon._run_needs_check() == {"recorded": 1}
    needs = daemon.runtime_observer.get_by_category("need")
    assert len(needs) == 1
    assert needs[0].system_state.get("need") == "free_zone_seed_supply"


def test_repeated_cycles_do_not_multiply_the_need(tmp_path):
    daemon = _daemon(tmp_path)
    daemon._run_needs_check()
    daemon._run_needs_check()
    daemon._run_needs_check()
    assert len(daemon.runtime_observer.get_by_category("need")) == 1


def test_seed_arrival_recovers_without_new_record(tmp_path):
    daemon = _daemon(tmp_path)
    daemon._run_needs_check()
    name, payload = _seed()
    (Path(tmp_path) / "07_SANDBOX" / "free_research" / "inbox" / name).write_text(
        json.dumps(payload), encoding="utf-8"
    )
    assert daemon._run_needs_check() == {"recorded": 0}
    assert len(daemon.runtime_observer.get_by_category("need")) == 1


def test_disabled_shift_or_missing_observer_stays_silent(tmp_path):
    from core.observation import RuntimeObserver
    from ace_daemon import AceDaemon

    daemon = _daemon(tmp_path)
    daemon.config = {"runtime": {"free_zone_model_shift": {"enabled": False}}}
    assert daemon._run_needs_check() == {"recorded": 0}
    daemon.runtime_observer = None
    daemon.config = {"runtime": {"free_zone_model_shift": {"enabled": True}}}
    assert daemon._run_needs_check() == {"recorded": 0}
