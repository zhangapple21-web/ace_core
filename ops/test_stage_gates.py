# The nine-day silent shift: gates must speak even when they hold.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_all_passing_gates_report_go():
    from core.stage_gates import evaluate_gates

    passed, blocker = evaluate_gates({
        "config_enabled": (True, "flag on"),
        "dedicated_window": (True, "past 18:30"),
    })
    assert (passed, blocker) == (True, "GO")


def test_first_failing_gate_names_the_blocker_in_order():
    from core.stage_gates import evaluate_gates

    passed, blocker = evaluate_gates({
        "config_enabled": (False, "flag off"),
        "dedicated_window": (False, "too early"),
    })
    assert (passed, blocker) == (False, "config_enabled")


def test_record_gate_persists_without_deciding():
    from core.stage_gates import STATE_KEY, record_gate

    state = {}
    record = record_gate(state, "evening_shift",
                         {"config_enabled": (False, "flag off")}, "DISABLED")
    assert record["decision"] == "DISABLED"
    assert record["gates"]["config_enabled"] == {"passed": False, "detail": "flag off"}
    assert state[STATE_KEY]["evening_shift"]["decision"] == "DISABLED"


def test_record_gate_never_clobbers_sibling_stages():
    from core.stage_gates import STATE_KEY, record_gate

    state = {STATE_KEY: {"other": {"decision": "GO"}}}
    record_gate(state, "evening_shift", {}, "RUNNING_SHIFT")
    assert state[STATE_KEY]["other"] == {"decision": "GO"}
    assert state[STATE_KEY]["evening_shift"]["decision"] == "RUNNING_SHIFT"
