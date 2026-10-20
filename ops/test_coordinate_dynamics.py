from core.coordinate_dynamics import Axis, CoordinateDynamics, WorkConservationGate


def test_coordinate_dynamics_selects_weighted_axis_and_applies_feedback():
    dynamics = CoordinateDynamics([Axis("state", 1.0), Axis("evidence", 2.0)])
    receipt = dynamics.locate(
        objective="repair closed loop",
        position={"state": 1, "evidence": 2},
        target={"state": 4, "evidence": 3},
        state={"active_axes": ["state", "evidence"]},
        feedback={"observed_delta": {"state": 1}},
        lineage={"source": "archaeology:R1_PRINCIPIA_PROBE_LINEAGE_GAP"},
    )
    assert receipt["contract_version"] == "ace.coordinate_dynamics.v1"
    assert receipt["selected_axis"] == "state"
    assert receipt["direction"] == {"evidence": 1.0, "state": 3.0}
    assert receipt["updated_position"]["state"] == 2.0
    assert receipt["state_transition"] == "FEEDBACK_APPLIED"
    assert receipt["receipt_hash"]


def test_coordinate_dynamics_rejects_non_numeric_state():
    try:
        CoordinateDynamics().locate(objective="x", position={"state": "unknown"}, target={"state": 1})
    except ValueError as error:
        assert str(error) == "position_not_numeric:state"
    else:
        raise AssertionError("non-numeric coordinate must be rejected")


def test_work_conservation_requires_new_discovery_and_deduplicates_window():
    gate = WorkConservationGate()
    assert gate.admit(work_signature="same-gap", discovery_refs=[], window_id="w1")["reason"] == "NO_NEW_DISCOVERY"
    first = gate.admit(work_signature="same-gap", discovery_refs=["obs-1"], window_id="w1")
    assert first["admitted"] is True
    duplicate = gate.admit(work_signature="same-gap", discovery_refs=["obs-2"], window_id="w1")
    assert duplicate["reason"] == "DUPLICATE_WORK_IN_WINDOW"
    next_window = gate.admit(work_signature="same-gap", discovery_refs=["obs-2"], window_id="w2")
    assert next_window["admitted"] is True
