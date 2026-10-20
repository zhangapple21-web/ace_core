"""ACE state calculus: 状态 -> 坐标/向量 -> 变化 -> 融合 -> 方向.

This is the cross-domain computation law.  Its normative text is
``00_ROOT/STATE_CALCULUS.v1.md``; this module is the executable form.

The lesson it encodes.  R1 owned the first half of this chain and lost it.
``02_HEART_CORE/reality_weight_matrix.json``, ``DIMENSION_WEIGHTS`` /
``NODE_COORDS``, ``language_style_vectors``, an "8-dimension persona vector", and
the claim that KRMGCE were "five coordinate axes" -- all of that is a
coordinate language.  What never existed was the other half: how a coordinate
*changes*, how several things fuse into one judgement, and how a direction
becomes comparable to another direction.  So the vocabulary was real and the
calculus was missing, which is worse than either having both or neither.

Three properties make it domain-neutral, and all three are load-bearing:

*Fixed basis.*  Every subject -- a stock, a persona, a memory item, a task, a
realm -- is projected onto the same six facets.  Nothing gets its own private
dimension set, so two subjects are comparable the moment they share a frame.

*Declared frame.*  A vector is meaningless without a reference frame and a
ceiling per axis.  ``03_DATA`` and ``R1_STRUCTURE_TRANSFORMATIONS.md`` both
record the failure this prevents: a 14/16 reading that was "an instrument
reading, not a world fact" because nobody declared which frame produced it.
Comparing across frames returns BLOCKED instead of averaging two
incommensurable numbers.

*Absence is visible.*  Fusion preserves the product rule: an absent axis
contributes zero and is listed in ``absent_axes``.  Missing evidence cannot be
quietly averaged into moderate confidence, and it cannot hide either.

Pure module: no I/O, no model calls, no production writes, no promotion.  It
returns a judgement, never an action.
"""

from __future__ import annotations

from datetime import datetime, timezone
from math import sqrt
from typing import Any, Dict, Iterable, List, Mapping, Sequence

SCHEMA_VERSION = 1

#: The fixed basis.  Order is normative: a vector is a 6-tuple in this order.
#: Each axis names a live ACE facet, so every coordinate is countable from an
#: existing ledger rather than invented per subject.
BASIS: tuple[str, ...] = (
    "reality",     # 接触现实的量      -> Observation / Observer
    "knowledge",   # 已有语义理解      -> Lexicon / knowledge
    "memory",      # 已沉淀的连续性    -> MemoryIndex / Experience
    "generation",  # 产生新物的能力    -> Capability / Provider / Researcher
    "execution",   # 落地动作的能力    -> TaskPool / Worker / Execution
    "experience",  # 已有的成败经验    -> ExperienceDeposition / JudgeLayer
)

AXIS_INDEX: Dict[str, int] = {axis: idx for idx, axis in enumerate(BASIS)}

OK = "CALCULUS_OK"
BLOCKED = "CALCULUS_BLOCKED"

__all__ = [
    "SCHEMA_VERSION",
    "BASIS",
    "AXIS_INDEX",
    "OK",
    "BLOCKED",
    "make_frame",
    "project",
    "delta",
    "fuse",
    "resolve",
    "describe",
]


def make_frame(frame_id: str, ceilings: Mapping[str, float], scales: Mapping[str, float]) -> Dict[str, Any]:
    """Declare a reference frame: an id, a ceiling per axis, a movement scale.

    ``ceilings`` convert raw counts into [0, 1] coordinates.  ``scales``
    convert raw movement into [-1, 1] changes, and must be the axis's own
    typical movement -- otherwise a rarely-moving axis looks dramatic and a
    busy axis looks still.  Both mappings must cover the whole basis; a partial
    frame is refused, because a half-declared frame is how undeclared readings
    enter a system.
    """

    reasons: List[str] = []
    if not isinstance(frame_id, str) or not frame_id.strip():
        reasons.append("FRAME_ID_MISSING")
    for name, mapping in (("ceilings", ceilings), ("scales", scales)):
        if not isinstance(mapping, Mapping):
            reasons.append(f"FRAME_{name.upper()}_MISSING")
            continue
        for axis in BASIS:
            value = mapping.get(axis)
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                reasons.append(f"FRAME_{name.upper()}_MISSING_AXIS:{axis}")
            elif value <= 0:
                reasons.append(f"FRAME_{name.upper()}_NONPOSITIVE:{axis}")
    if reasons:
        return {
            "contract_version": f"ace.calculus.frame.v{SCHEMA_VERSION}",
            "status": BLOCKED,
            "frame": None,
            "reason_codes": list(dict.fromkeys(reasons)),
        }
    return {
        "contract_version": f"ace.calculus.frame.v{SCHEMA_VERSION}",
        "status": OK,
        "frame": {
            "frame_id": frame_id.strip(),
            "ceilings": {axis: float(ceilings[axis]) for axis in BASIS},
            "scales": {axis: float(scales[axis]) for axis in BASIS},
        },
        "reason_codes": [],
    }


def _frame_or_block(frame: Any) -> tuple[Dict[str, Any] | None, List[str]]:
    if not isinstance(frame, Mapping) or not isinstance(frame.get("frame"), Mapping):
        return None, ["FRAME_MISSING"]
    inner = frame["frame"]
    if not isinstance(inner.get("frame_id"), str) or not inner["frame_id"].strip():
        return None, ["FRAME_ID_MISSING"]
    for name in ("ceilings", "scales"):
        mapping = inner.get(name)
        if not isinstance(mapping, Mapping) or any(axis not in mapping for axis in BASIS):
            return None, [f"FRAME_{name.upper()}_INCOMPLETE"]
    return dict(inner), []


def _envelope(kind: str, status: str, reasons: List[str], **extra: Any) -> Dict[str, Any]:
    payload = {
        "contract_version": f"ace.calculus.{kind}.v{SCHEMA_VERSION}",
        "status": status,
        "reason_codes": list(dict.fromkeys(reasons)),
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "execution_authorized": False,
    }
    payload.update(extra)
    return payload


def project(
    measures: Mapping[str, float] | None,
    frame: Any,
    *,
    subject: str = "",
) -> Dict[str, Any]:
    """Stage 1 -- 状态 -> 坐标/向量.

    ``measures`` is the raw countable state of one subject on the fixed basis.
    Every axis must be present: a missing axis is refused rather than defaulted,
    because an invented zero and an absent measurement are different facts.
    """

    inner, reasons = _frame_or_block(frame)
    if inner is None:
        return _envelope("project", BLOCKED, reasons, vector=None, absent_axes=list(BASIS))

    if not isinstance(measures, Mapping):
        return _envelope("project", BLOCKED, reasons + ["MEASURES_MISSING"], vector=None,
                         absent_axes=list(BASIS))

    coords: List[float] = []
    absent: List[str] = []
    for axis in BASIS:
        raw = measures.get(axis)
        if not isinstance(raw, (int, float)) or isinstance(raw, bool) or raw < 0:
            absent.append(axis)
            coords.append(0.0)
            continue
        ceiling = float(inner["ceilings"][axis])
        coords.append(min(1.0, float(raw) / ceiling))

    status = OK if not absent else BLOCKED
    codes = [f"MEASURE_MISSING:{axis}" for axis in absent]
    return _envelope(
        "project", status, reasons + codes,
        subject=subject or None,
        basis=list(BASIS),
        frame_id=inner["frame_id"],
        # The vector carries its own measurement context.  A coordinate without
        # the scale it was measured against cannot be differenced later, which
        # is how undeclared readings get compared to each other.
        scales=dict(inner["scales"]),
        vector=tuple(round(value, 6) for value in coords),
        absent_axes=absent,
    )


def delta(
    before: Any,
    after: Any,
    *,
    subject: str = "",
) -> Dict[str, Any]:
    """Stage 2 -- 坐标 -> 变化.

    Per-axis movement normalised by that axis's own declared scale, so the same
    raw change means different things on a quiet axis and a busy one.  Two
    vectors in different frames are BLOCKED: there is no honest change between
    two reference frames without an explicit transform.
    """

    reasons: List[str] = []
    for label, item in (("before", before), ("after", after)):
        if not isinstance(item, Mapping):
            reasons.append(f"{label.upper()}_MISSING")
        elif item.get("vector") is None:
            reasons.append(f"{label.upper()}_VECTOR_MISSING")
        elif not isinstance(item.get("frame_id"), str) or not item["frame_id"].strip():
            reasons.append(f"{label.upper()}_FRAME_ID_MISSING")

    if reasons:
        return _envelope("delta", BLOCKED, reasons, change=None, absent_axes=list(BASIS),
                         basis=list(BASIS))

    if before["frame_id"] != after["frame_id"]:
        return _envelope(
            "delta", BLOCKED,
            ["FRAME_MISMATCH:%s!=%s" % (before["frame_id"], after["frame_id"])],
            change=None, absent_axes=list(BASIS), basis=list(BASIS),
            frame_id=None,
        )

    scales = before.get("scales")
    if not isinstance(scales, Mapping) or any(
        axis not in scales or not isinstance(scales[axis], (int, float)) or isinstance(scales[axis], bool)
        for axis in BASIS
    ):
        scales = after.get("scales")
    if not isinstance(scales, Mapping) or any(axis not in scales for axis in BASIS):
        return _envelope(
            "delta", BLOCKED, ["FRAME_SCALES_REQUIRED_FOR_DELTA"],
            change=None, absent_axes=list(BASIS), basis=list(BASIS),
            frame_id=before["frame_id"],
        )

    before_absent = set(before.get("absent_axes") or ())
    after_absent = set(after.get("absent_axes") or ())
    absent = sorted(before_absent | after_absent)

    b_vec = before["vector"]
    a_vec = after["vector"]
    if len(b_vec) != len(BASIS) or len(a_vec) != len(BASIS):
        return _envelope("delta", BLOCKED, ["VECTOR_SHAPE_MISMATCH"],
                         change=None, absent_axes=list(BASIS), basis=list(BASIS))

    change: List[float] = []
    for axis, before_value, after_value in zip(BASIS, b_vec, a_vec):
        if axis in before_absent or axis in after_absent:
            change.append(0.0)
            continue
        scale = float(scales[axis])
        moved = (float(after_value) - float(before_value)) / scale
        change.append(max(-1.0, min(1.0, moved)))

    return _envelope(
        "delta", OK, reasons,
        subject=subject or before.get("subject") or after.get("subject"),
        basis=list(BASIS),
        frame_id=before["frame_id"],
        scales={axis: float(scales[axis]) for axis in BASIS},
        change=tuple(round(value, 6) for value in change),
        absent_axes=absent,
    )


def fuse(
    changes: Sequence[Mapping[str, Any]] | None,
    *,
    weights: Mapping[str, float] | None = None,
) -> Dict[str, Any]:
    """Stage 3 -- 变化 -> 融合.

    Fuses per-axis changes from several sources in the same frame.  ``weights``
    defaults to uniform, which is the point: uniform is a decision that can be
    argued with, whereas a set of unexplained numbers cannot.  An absent axis
    contributes zero and is reported.  If every input is absent, fusion refuses
    rather than returning a confident zero.
    """

    rows = changes if isinstance(changes, Sequence) and not isinstance(changes, (str, bytes)) else []

    # Frame agreement is checked across every row that declares one, including
    # rows that are otherwise unusable.  Filtering first would let a frame
    # mismatch degrade into "fewer inputs", which is precisely the quiet
    # averaging of incommensurable readings that this calculus exists to stop.
    declared = {
        row["frame_id"]
        for row in rows
        if isinstance(row, Mapping) and isinstance(row.get("frame_id"), str) and row["frame_id"].strip()
    }
    if len(declared) > 1:
        return _envelope(
            "fuse", BLOCKED,
            ["FRAME_MISMATCH:" + "|".join(sorted(declared))],
            fused=None, absent_axes=list(BASIS), basis=list(BASIS), frame_id=None,
        )

    # An input that was itself refused for frame disagreement is still evidence
    # of disagreement.  Dropping it and fusing the survivors would launder a
    # blocked comparison into a clean result.
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        codes = row.get("reason_codes")
        if isinstance(codes, list) and any(
            isinstance(code, str) and code.startswith("FRAME_MISMATCH") for code in codes
        ):
            return _envelope(
                "fuse", BLOCKED,
                ["REFUSED_INPUT_FRAME_CONFLICT"],
                fused=None, absent_axes=list(BASIS), basis=list(BASIS),
                frame_id=next(iter(sorted(declared)), None),
            )

    usable: List[Mapping[str, Any]] = [
        row for row in rows
        if isinstance(row, Mapping) and row.get("change") is not None
        and isinstance(row.get("frame_id"), str) and row["frame_id"].strip()
        and len(row["change"]) == len(BASIS)
    ]
    if not usable:
        return _envelope("fuse", BLOCKED, ["NO_FUSABLE_INPUT"], fused=None,
                         absent_axes=list(BASIS), basis=list(BASIS))

    if weights is None:
        weight_map = {axis: 1.0 / len(BASIS) for axis in BASIS}
    elif isinstance(weights, Mapping) and all(
        axis in weights and isinstance(weights[axis], (int, float)) and not isinstance(weights[axis], bool)
        for axis in BASIS
    ):
        weight_map = {axis: float(weights[axis]) for axis in BASIS}
    else:
        return _envelope("fuse", BLOCKED, ["WEIGHTS_MUST_COVER_BASIS"], fused=None,
                         absent_axes=list(BASIS), basis=list(BASIS))

    total_weight = sum(abs(value) for value in weight_map.values())
    if total_weight <= 0:
        return _envelope("fuse", BLOCKED, ["WEIGHTS_SUM_TO_ZERO"], fused=None,
                         absent_axes=list(BASIS), basis=list(BASIS))

    absent = sorted({axis for row in usable for axis in (row.get("absent_axes") or ())})

    # Disagreement has to be measured BEFORE averaging, or fusion erases the
    # very signal resolve needs.  Averaging +1.0 and -0.45 yields a clean +0.275
    # that looks like confident agreement; it was not.  So the per-axis ratio of
    # net movement to gross movement is computed across sources first, and
    # carried forward untouched.
    per_axis_agreement: Dict[str, float] = {}
    for idx, axis in enumerate(BASIS):
        if axis in absent:
            continue
        column = [float(row["change"][idx]) for row in usable]
        gross = sum(abs(value) for value in column)
        if gross <= 0:
            continue
        per_axis_agreement[axis] = round(abs(sum(column)) / gross, 6)

    source_agreement = (
        sum(per_axis_agreement.values()) / len(per_axis_agreement)
        if per_axis_agreement else 0.0
    )

    fused: List[float] = []
    for idx, axis in enumerate(BASIS):
        if axis in absent:
            fused.append(0.0)
            continue
        accumulated = 0.0
        for row in usable:
            accumulated += float(row["change"][idx]) * weight_map[axis]
        fused.append(max(-1.0, min(1.0, accumulated / total_weight)))

    live = [axis for axis in BASIS if axis not in absent]
    if not live:
        return _envelope(
            "fuse", BLOCKED, ["ALL_AXES_ABSENT"],
            fused=None, absent_axes=absent, basis=list(BASIS), frame_id=usable[0]["frame_id"],
        )

    return _envelope(
        "fuse", OK, [],
        basis=list(BASIS),
        frame_id=usable[0]["frame_id"],
        fused=tuple(round(value, 6) for value in fused),
        weights=weight_map,
        per_axis_agreement=per_axis_agreement,
        source_agreement=round(source_agreement, 6),
        absent_axes=absent,
        source_count=len(usable),
    )


def resolve(fused_result: Any) -> Dict[str, Any]:
    """Stage 4 -- 融合 -> 方向.

    Returns a unit direction plus the dominant axis and a confidence that
    measures directional coherence, not magnitude.  A large change in every
    axis is low confidence -- it points nowhere.  Confidence near zero means
    "the axes disagree", and the honest response to that is to hold, not to
    pick the largest component.

    Three independent questions are asked and reported separately, because
    collapsing them is what let a contradiction through once already:

    concentration  is the movement focused or smeared across the basis?
    source_agreement  did the fused sources point the same way BEFORE
                       averaging?  Taken from fuse(), which measured it there;
                       recomputing it here would read a cancellation that has
                       already been smoothed into agreement.
    intra_agreement  do the live axes of THIS vector disagree in sign with each
                       other?  Without this term a single source whose axes move
                       in opposite directions scores exactly like one whose axes
                       move together -- the defect recorded as F-3 by the T0
                       canary, where agreeing and contradicting evidence both
                       returned confidence 0.400.
    """

    if not isinstance(fused_result, Mapping) or fused_result.get("fused") is None:
        return _envelope("resolve", BLOCKED, ["FUSED_MISSING"], direction=None)

    fused = fused_result["fused"]
    basis = fused_result.get("basis") or list(BASIS)
    if len(fused) != len(basis):
        return _envelope("resolve", BLOCKED, ["VECTOR_SHAPE_MISMATCH"], direction=None)

    magnitude = sqrt(sum(float(value) ** 2 for value in fused))
    absent = list(fused_result.get("absent_axes") or ())
    live_pairs = [(axis, float(value)) for axis, value in zip(basis, fused) if axis not in absent]

    if magnitude <= 0.0 or not live_pairs:
        return _envelope(
            "resolve", BLOCKED, ["DIRECTION_UNDEFINED"],
            direction=None, basis=list(basis), frame_id=fused_result.get("frame_id"),
            dominant_axis=None, confidence=0.0, absent_axes=absent,
        )

    unit = tuple(round(float(value) / magnitude, 6) for value in fused)
    dominant_axis, dominant_value = max(live_pairs, key=lambda pair: (pair[1], basis.index(pair[0])))

    gross = sum(abs(value) for _, value in live_pairs)
    concentration = abs(dominant_value) / gross if gross else 0.0

    # Cross-source agreement, measured before averaging.  A missing value is
    # treated as zero rather than assumed favourable.
    agreement = fused_result.get("source_agreement")
    agreement = float(agreement) if isinstance(agreement, (int, float)) else 0.0

    # Intra-vector agreement: do the live axes contradict each other in sign?
    # abs() is required, not cosmetic.  Without it, a vector whose axes all move
    # NEGATIVE together would score -1.0 and yield negative confidence, when
    # moving together one way is exactly as coherent as moving together the
    # other way.  Axes at 0.0 are silent, not opposed, which is why a single-axis
    # jump still scores 1.0 here instead of being diluted by five zeros.
    positive = sum(value for _, value in live_pairs if value > 0)
    negative = sum(-value for _, value in live_pairs if value < 0)
    intra = abs((positive - negative) / gross) if gross else 0.0

    confidence = round(concentration * agreement * intra, 6)
    return _envelope(
        "resolve", OK, [],
        basis=list(basis),
        frame_id=fused_result.get("frame_id"),
        direction=unit,
        dominant_axis=dominant_axis,
        dominant_value=round(dominant_value, 6),
        concentration=round(concentration, 6),
        sign_agreement=round(agreement, 6),
        intra_agreement=round(intra, 6),
        confidence=confidence,
        absent_axes=absent,
        next_step="act" if confidence >= 0.5 else "hold_and_collect_more_evidence",
    )


def describe(frame: Any) -> Dict[str, Any]:
    """Human-readable basis legend, so no caller has to guess what an axis means."""

    legend = {
        "reality": "接触现实的量（Observation / Observer）",
        "knowledge": "已有语义理解（Lexicon / knowledge）",
        "memory": "已沉淀的连续性（MemoryIndex / Experience）",
        "generation": "产生新物的能力（Capability / Provider / Researcher）",
        "execution": "落地动作的能力（TaskPool / Worker / Execution）",
        "experience": "已有的成败经验（ExperienceDeposition / JudgeLayer）",
    }
    inner, reasons = _frame_or_block(frame)
    return _envelope(
        "describe", OK if inner else BLOCKED, reasons,
        basis=list(BASIS),
        legend=legend,
        frame_id=inner["frame_id"] if inner else None,
    )
