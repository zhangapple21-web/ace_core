# The unified names deserve one honest readout, not a new system.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_self_watch_survives_an_empty_root(tmp_path):
    import time

    from ops.self_watch import artifact_sensing, introspection

    now = time.time()
    intro = introspection(tmp_path, now)
    assert intro["daemon"] == {"pid": None, "run_status": None, "last_run": None}
    assert intro["needs_count"] == 0
    assert intro["providers"] == []
    sens = artifact_sensing(tmp_path, now)
    assert sens["fragment_index"]["total"] == 0
    assert sens["archaeologist"] is None
    assert sens["mine_seed"]["in_sync"] is False


def test_self_watch_reads_a_fixture_tree(tmp_path):
    import json
    import time

    from ops.self_watch import artifact_sensing

    frag = tmp_path / "02_FRAGMENT_INDEX"
    frag.mkdir(parents=True)
    (frag / "fragment_index.json").write_text(json.dumps({
        "a": {"status": "pending_scan"}, "b": {"status": "archaeologized"},
    }), encoding="utf-8")
    (frag / ".mine_seed_state.json").write_text(
        json.dumps({"last_commit": "abc123"}), encoding="utf-8")
    sens = artifact_sensing(tmp_path, time.time())
    assert sens["fragment_index"]["total"] == 2
    assert sens["fragment_index"]["by_status"] == {
        "pending_scan": 1, "archaeologized": 1}
