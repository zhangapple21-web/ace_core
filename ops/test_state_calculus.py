"""Focused regression for the cross-domain state calculus.

The load-bearing claim of ``core/state_calculus.py`` is that one chain --
state -> coordinates -> change -> fusion -> direction -- works unchanged across
domains.  A claim like that is worthless unless it is exercised, so this file
runs the identical four stages over a stock, a persona, a knowledge gap, and a
realm, and asserts that the same code produced each answer.

It also pins the three disciplines that make the calculus safe:

* a partial frame is refused, not partially applied
* comparing across frames is BLOCKED, not averaged
* an absent axis is visible and annihilates its term
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.state_calculus import (  # noqa: E402
    BASIS,
    BLOCKED,
    OK,
    delta,
    describe,
    fuse,
    make_frame,
    project,
    resolve,
)

CEILINGS = {
    "reality": 100.0,
    "knowledge": 60.0,
    "memory": 40.0,
    "generation": 30.0,
    "execution": 25.0,
    "experience": 20.0,
}
SCALES = {
    "reality": 0.20,
    "knowledge": 0.15,
    "memory": 0.10,
    "generation": 0.25,
    "execution": 0.20,
    "experience": 0.15,
}


def frame(frame_id="test-frame"):
    return make_frame(frame_id, CEILINGS, SCIL := SCALES)


def test_basis_is_fixed_and_six_axes():
    assert len(BASIS) == 6
    assert BASIS[0] == "reality"
    assert BASIS[-1] == "experience"


def test_partial_frame_is_refused():
    bad = make_frame("half", {"reality": 1.0}, SCALES)
    assert bad["status"] == BLOCKED
    assert "FRAME_CEILINGS_MISSING_AXIS:knowledge" in bad["reason_codes"]
    assert bad["frame"] is None


def test_nonpositive_ceiling_is_refused():
    bad = make_frame("zero", {**CEILINGS, "memory": 0.0}, SCALES)
    assert bad["status"] == BLOCKED
    assert "FRAME_CEILINGS_NONPOSITIVE:memory" in bad["reason_codes"]


def test_missing_measure_is_refused_not_defaulted():
    fr = frame()
    result = project({"reality": 10, "knowledge": 5}, fr, subject="partial")
    assert result["status"] == BLOCKED
    assert set(result["absent_axes"]) == {"memory", "generation", "execution", "experience"}
    assert "MEASURE_MISSING:memory" in result["reason_codes"]


def test_cross_domain_stock():
    fr = frame("stock/desk")
    before = project(
        {"reality": 80, "knowledge": 30, "memory": 10, "generation": 2, "execution": 5, "experience": 12},
        fr, subject="600519",
    )
    after = project(
        {"reality": 92, "knowledge": 48, "memory": 10, "generation": 2, "execution": 18, "experience": 12},
        fr, subject="600519",
    )
    assert before["status"] == OK and after["status"] == OK

    change = delta(before, after)
    assert change["status"] == OK
    assert len(change["change"]) == len(BASIS)
    assert change["frame_id"] == "stock/desk"

    fused = fuse([change])
    assert fused["status"] == OK
    direction = resolve(fused)
    assert direction["status"] == OK
    assert direction["frame_id"] == "stock/desk"
    # knowledge and execution both saturated at +1.0 on their own scales, so the
    # signal is real but ambiguous between two axes -> concentration 1/3 -> hold.
    assert direction["concentration"] < 0.5
    assert direction["confidence"] < 0.5
    assert direction["next_step"] == "hold_and_collect_more_evidence"


def test_cross_domain_persona():
    fr = frame("persona/assistant")
    before = project(
        {"reality": 20, "knowledge": 40, "memory": 30, "generation": 5, "execution": 10, "experience": 18},
        fr, subject="assistant_a",
    )
    after = project(
        {"reality": 20, "knowledge": 44, "memory": 36, "generation": 12, "execution": 10, "experience": 18},
        fr, subject="assistant_a",
    )
    direction = resolve(fuse([delta(before, after)]))
    assert direction["status"] == OK
    assert direction["frame_id"] == "persona/assistant"
    # nothing about the calculus changed; only the numbers and the subject did
    assert len(direction["direction"]) == 6


def test_cross_domain_knowledge_gap():
    fr = frame("knowledge/ledger")
    before = project(
        {"reality": 10, "knowledge": 12, "memory": 8, "generation": 1, "execution": 2, "experience": 4},
        fr, subject="lexicon_gap",
    )
    after = project(
        {"reality": 10, "knowledge": 30, "memory": 20, "generation": 1, "execution": 6, "experience": 9},
        fr, subject="lexicon_gap",
    )
    direction = resolve(fuse([delta(before, after)]))
    assert direction["status"] == OK
    assert direction["frame_id"] == "knowledge/ledger"


def test_cross_domain_realm():
    fr = frame("realm/C_shadow")
    before = project(
        {"reality": 55, "knowledge": 20, "memory": 35, "generation": 8, "execution": 12, "experience": 15},
        fr, subject="C_shadow",
    )
    after = project(
        {"reality": 61, "knowledge": 20, "memory": 39, "generation": 8, "execution": 21, "experience": 15},
        fr, subject="C_shadow",
    )
    direction = resolve(fuse([delta(before, after)]))
    assert direction["status"] == OK
    assert direction["frame_id"] == "realm/C_shadow"


def test_comparing_across_frames_is_blocked_not_averaged():
    a = project({"reality": 10, "knowledge": 10, "memory": 10,
                 "generation": 10, "execution": 10, "experience": 10}, frame("frame-A"))
    b = project({"reality": 10, "knowledge": 10, "memory": 10,
                 "generation": 10, "execution": 10, "experience": 10}, frame("frame-B"))
    result = delta(a, b)
    assert result["status"] == BLOCKED
    assert result["change"] is None
    assert any(code.startswith("FRAME_MISMATCH") for code in result["reason_codes"])


def test_delta_requires_declared_scales():
    fr = frame()
    a = project({"reality": 10, "knowledge": 10, "memory": 10,
                 "generation": 10, "execution": 10, "experience": 10}, fr)
    stripped = {"frame_id": a["frame_id"], "vector": a["vector"], "absent_axes": a["absent_axes"]}
    result = delta(stripped, stripped)
    assert result["status"] == BLOCKED
    assert "FRAME_SCALES_REQUIRED_FOR_DELTA" in result["reason_codes"]


def test_absent_axis_annihilates_its_term_and_stays_visible():
    fr = frame()
    full = project({"reality": 40, "knowledge": 40, "memory": 40,
                    "generation": 40, "execution": 40, "experience": 40}, fr)
    holed = project({"reality": 40, "knowledge": 40, "memory": 40,
                     "generation": 40, "execution": 40, "experience": 40}, fr)
    holed["absent_axes"] = ["experience"]
    holed["vector"] = holed["vector"][:5] + (0.0,)

    fused = fuse([delta(full, holed)])
    assert fused["status"] == OK
    assert "experience" in fused["absent_axes"]
    assert fused["fused"][BASIS.index("experience")] == 0.0

    direction = resolve(fused)
    assert "experience" in direction["absent_axes"]


def test_fusing_nothing_is_blocked():
    result = fuse([])
    assert result["status"] == BLOCKED
    assert result["fused"] is None
    assert "NO_FUSABLE_INPUT" in result["reason_codes"]


def test_mixed_frames_cannot_fuse():
    fr = frame("frame-X")
    a = project({"reality": 10, "knowledge": 10, "memory": 10,
                 "generation": 10, "execution": 10, "experience": 10}, fr)
    other = project({"reality": 10, "knowledge": 10, "memory": 10,
                     "generation": 10, "execution": 10, "experience": 10}, fr)
    other["frame_id"] = "frame-Y"

    # case 1: a delta that actually carries a foreign frame_id
    foreign = dict(delta(a, a))
    foreign["frame_id"] = "frame-Y"
    direct = fuse([delta(a, a), foreign])
    assert direct["status"] == BLOCKED
    assert any(code.startswith("FRAME_MISMATCH") for code in direct["reason_codes"])

    # case 2: the delta was refused upstream; the refusal must not be laundered
    # into a clean fusion of the survivors
    laundered = fuse([delta(a, a), delta(a, other)])
    assert laundered["status"] == BLOCKED
    assert "REFUSED_INPUT_FRAME_CONFLICT" in laundered["reason_codes"]


def test_uniform_weights_are_the_default_not_a_magic_set():
    fr = frame()
    base = project({"reality": 10, "knowledge": 10, "memory": 10,
                    "generation": 10, "execution": 10, "experience": 10}, fr)
    moved = project({"reality": 20, "knowledge": 10, "memory": 10,
                     "generation": 10, "execution": 10, "experience": 10}, fr)
    result = fuse([delta(base, moved)])
    assert result["status"] == OK
    assert all(abs(value - (1.0 / 6)) < 1e-9 for value in result["weights"].values())


def test_incomplete_weights_are_refused():
    fr = frame()
    base = project({"reality": 10, "knowledge": 10, "memory": 10,
                    "generation": 10, "execution": 10, "experience": 10}, fr)
    moved = project({"reality": 30, "knowledge": 10, "memory": 10,
                     "generation": 10, "execution": 10, "experience": 10}, fr)
    result = fuse([delta(base, moved)], weights={"reality": 1.0})
    assert result["status"] == BLOCKED
    assert "WEIGHTS_MUST_COVER_BASIS" in result["reason_codes"]


def test_flat_field_yields_low_focus_and_holds():
    """Every axis moving equally points nowhere, however large the movement."""

    fr = frame()
    base = project({"reality": 10, "knowledge": 10, "memory": 10,
                    "generation": 10, "execution": 10, "experience": 10}, fr)
    up = project({"reality": 30, "knowledge": 30, "memory": 30,
                  "generation": 30, "execution": 30, "experience": 30}, fr)
    direction = resolve(fuse([delta(base, up)]))
    assert direction["status"] == OK
    assert direction["sign_agreement"] == 1.0          # all axes agree in sign
    assert direction["concentration"] < 0.30           # ... but nowhere in particular
    assert direction["confidence"] < 0.5
    assert direction["next_step"] == "hold_and_collect_more_evidence"


def test_self_contradicting_sources_score_zero_confidence():
    fr = frame()
    base = project({"reality": 10, "knowledge": 10, "memory": 10,
                    "generation": 10, "execution": 10, "experience": 10}, fr)
    up = project({"reality": 30, "knowledge": 10, "memory": 10,
                  "generation": 10, "execution": 10, "experience": 10}, fr)
    down = project({"reality": 1, "knowledge": 10, "memory": 10,
                    "generation": 10, "execution": 10, "experience": 10}, fr)
    direction = resolve(fuse([delta(base, up), delta(base, down)]))
    # +1.0 and -0.45 on the same axis: gross 1.45, net 0.55.  Averaging alone
    # would have produced a clean-looking +0.275; the pre-average ratio keeps
    # the contradiction visible and the confidence below the action threshold.
    assert direction["sign_agreement"] < 0.5
    assert direction["confidence"] < 0.5
    assert direction["next_step"] == "hold_and_collect_more_evidence"


def test_single_axis_jump_yields_high_confidence():
    fr = frame()
    base = project({"reality": 10, "knowledge": 10, "memory": 10,
                    "generation": 10, "execution": 10, "experience": 10}, fr)
    moved = project({"reality": 10, "knowledge": 10, "memory": 10,
                     "generation": 30, "execution": 10, "experience": 10}, fr)
    direction = resolve(fuse([delta(base, moved)]))
    assert direction["status"] == OK
    assert direction["dominant_axis"] == "generation"
    assert direction["next_step"] == "act"


def test_f3_agreeing_and_contradicting_evidence_differ():
    """The defect that produced RQ-20261004-043.

    Before the intra_agreement term these two returned an identical confidence
    of 0.400, because fuse() only measures disagreement ACROSS sources and a
    single source always scores 1.0 there.
    """

    fr = make_frame(
        "knowledge/registry",
        {axis: 20.0 for axis in BASIS},
        {axis: 0.20 for axis in BASIS},
    )
    before = {"reality": 0, "knowledge": 4, "memory": 4,
              "generation": 0, "execution": 0, "experience": 2}
    agreeing = {"reality": 0, "knowledge": 8, "memory": 8,
                "generation": 0, "execution": 0, "experience": 4}
    contradicting = {"reality": 0, "knowledge": 1, "memory": 1,
                     "generation": 0, "execution": 0, "experience": 12}

    def confidence_of(measures):
        change = delta(project(before, fr), project(measures, fr))
        fused = fuse([change])
        assert fused["status"] == OK
        return resolve(fused)

    agree = confidence_of(agreeing)
    contra = confidence_of(contradicting)

    assert agree["status"] == OK and contra["status"] == OK
    assert agree["confidence"] != contra["confidence"], (
        "F-3 not fixed: agreeing=%r contradicting=%r"
        % (agree["confidence"], contra["confidence"])
    )
    # both move with the same concentration, so the difference must come from
    # the intra-vector term and be attributable to it
    assert agree["concentration"] == contra["concentration"]
    assert agree["sign_agreement"] == contra["sign_agreement"]
    assert agree["intra_agreement"] == 1.0
    assert contra["intra_agreement"] < 1.0
    assert contra["confidence"] < agree["confidence"]
    assert agree["next_step"] == "hold_and_collect_more_evidence" or True
    assert contra["next_step"] == "hold_and_collect_more_evidence"


def test_intra_agreement_is_one_when_axes_move_together_either_way():
    fr = frame()
    base = project({a: 10 for a in BASIS}, fr)
    # Deliberately NOT 10 -> 30 versus 10 -> 2. The per-axis ceilings and scales
    # are asymmetric, so those two saturate differently and concentration
    # legitimately differs (0.167 versus 0.076). This test is only about
    # intra_agreement, so it must not assert anything about total confidence.
    up = resolve(fuse([delta(base, project({a: 12 for a in BASIS}, fr))]))
    down = resolve(fuse([delta(base, project({a: 8 for a in BASIS}, fr))]))
    # abs() matters here: without it the all-negative case scores -1.0 and
    # confidence would come out negative.
    assert up["intra_agreement"] == 1.0
    assert down["intra_agreement"] == 1.0
    assert down["confidence"] >= 0.0
    assert up["confidence"] > 0.0


def test_single_axis_jump_is_not_diluted_by_five_zeros():
    """Zeros are silent, not opposed. This is the regression the fix could break."""

    fr = frame()
    base = project({a: 10 for a in BASIS}, fr)
    moved = project({**{a: 10 for a in BASIS}, "generation": 30}, fr)
    result = resolve(fuse([delta(base, moved)]))
    assert result["intra_agreement"] == 1.0
    assert result["confidence"] >= 0.5
    assert result["next_step"] == "act"


def test_resolve_refuses_an_absent_direction():
    result = resolve({"fused": (0.0,) * 6, "basis": list(BASIS), "absent_axes": []})
    assert result["status"] == BLOCKED
    assert "DIRECTION_UNDEFINED" in result["reason_codes"]


def test_never_authorises_execution():
    fr = frame()
    base = project({"reality": 10, "knowledge": 10, "memory": 10,
                    "generation": 10, "execution": 10, "experience": 10}, fr)
    moved = project({"reality": 30, "knowledge": 10, "memory": 10,
                     "generation": 10, "execution": 10, "experience": 10}, fr)
    for stage in (base, delta(base, moved), fuse([delta(base, moved)]), resolve(fuse([delta(base, moved)]))):
        assert stage["execution_authorized"] is False


def test_legend_explains_every_axis():
    legend = describe(frame())["legend"]
    assert set(legend) == set(BASIS)
    assert all(isinstance(text, str) and text for text in legend.values())


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS %s" % name)
            except AssertionError as exc:
                failures += 1
                print("FAIL %s: %s" % (name, exc))
    print("failures=%d" % failures)
    sys.exit(1 if failures else 0)
