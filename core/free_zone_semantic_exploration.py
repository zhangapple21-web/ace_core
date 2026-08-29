"""Descriptive semantic slicing and replayable stochastic exploration.

This module exists only for the free-research sandbox.  It does *not* decide
whether a candidate is good, true, profitable, safe for production, or worthy
of a recommendation.  It gives the productive cat a way to keep trying
different kinds of food when capacity is limited:

    source-fair turn order
        -> descriptive semantic slice coverage weights
        -> seeded stochastic draw within the chosen slice

The full allocation trace is retained so an observer can replay the resource
decision from the same candidate snapshot and seed.  Outcomes are never input
to the selection weights; Lazy Cat remains the post-execution evaluator.
"""

from __future__ import annotations

import hashlib
import json
import random
import sys
from typing import Any, Mapping


CONTRACT_VERSION = "ace.free_zone_semantic_exploration.v1"
# v2 adds one *descriptive* dimension for Lazy Cat food.  The old v1 slice
# collapsed every post-audit challenge into one bucket even when the original,
# signed challenge named different structural gaps.  This is deliberately a
# schema change instead of silently reusing old allocation counters.
SEMANTIC_SLICE_SCHEMA_VERSION = "ace.free_zone.semantic_slice.v2"
SELECTION_POLICY_VERSION = "ace.free_zone.source_fair_semantic_stochastic.v2"
_MASK_64 = (1 << 64) - 1

# These are the structural checks emitted by LazyCatAudit._assess().  A
# challenge may carry only this already-recorded list into exploration.  The
# allow-list prevents a free-text payload from multiplying the slice space or
# smuggling an outcome/market/quality label into resource allocation.
_KNOWN_CHALLENGE_GAPS = frozenset({
    "lineage",
    "bounded_method",
    "observable_evidence",
    "boundary_intact",
    "dissent_blueprint",
    "counterexample_scope",
    "counterexample_witness",
})
_NO_DECLARED_CHALLENGE_GAP = "none_declared"
_UNRECOGNIZED_DECLARED_CHALLENGE_GAP = "unrecognized_declared_gap"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _draw_weighted_index(weights: list[float], rng: random.Random) -> tuple[int, float]:
    """Choose an index and preserve the unit-interval draw for replay evidence."""
    if not weights or any(weight <= 0 for weight in weights):
        raise ValueError("weights must be non-empty and positive")
    draw = rng.random()
    total = sum(weights)
    boundary = 0.0
    for index, weight in enumerate(weights):
        boundary += weight / total
        if draw < boundary or index == len(weights) - 1:
            return index, draw
    raise AssertionError("weighted draw must select an index")


class SemanticSliceExplorer:
    """Allocate sandbox capacity without creating a quality or outcome score."""

    @staticmethod
    def _challenge_gap_signature(candidate: Mapping[str, Any]) -> str:
        """Return an immutable challenge's declared structural-gap signature.

        This reads no free text and makes no inference.  ``missing_dimensions``
        is created by the post-execution Lazy Cat audit and is already part of
        the immutable challenge record; the productive cat merely sees which
        structural repair question it received.  It is not a verdict, outcome,
        priority, or measure of a candidate's worth.
        """
        challenge = candidate.get("challenge")
        raw_gaps = challenge.get("missing_dimensions") if isinstance(challenge, Mapping) else None
        if not isinstance(raw_gaps, list):
            return _NO_DECLARED_CHALLENGE_GAP
        gaps = sorted({
            gap.strip().lower()
            for gap in raw_gaps
            if isinstance(gap, str) and gap.strip().lower() in _KNOWN_CHALLENGE_GAPS
        })
        if gaps:
            return "+".join(gaps)
        return _UNRECOGNIZED_DECLARED_CHALLENGE_GAP if raw_gaps else _NO_DECLARED_CHALLENGE_GAP

    @staticmethod
    def describe(candidate: Mapping[str, Any]) -> dict[str, Any]:
        """Build a fixed, structural description from existing candidate fields.

        No free text, model score, execution result, market field, or production
        status participates in this mapping.  Unknown input remains visible in
        an ``unknown`` category instead of becoming ineligible.
        """
        source_kind = str(candidate.get("source_kind", "unknown")) or "unknown"
        parent_status = str(candidate.get("parent_status", ""))
        challenge_gap_signature: str | None = None
        if source_kind == "lazy_cat_challenge":
            epistemic_shape = "post_audit_challenge"
            execution_stance = "COUNTEREXAMPLE_SEARCH"
            provenance_class = "sandbox_audit"
            challenge_gap_signature = SemanticSliceExplorer._challenge_gap_signature(candidate)
        elif source_kind == "distillation" and parent_status == "COUNTEREXAMPLE_ONLY":
            epistemic_shape = "counterexample_reobservation"
            execution_stance = "DIRECT_OBSERVATION"
            provenance_class = "sandbox_distillation"
        elif source_kind == "distillation" and parent_status == "OPEN_QUESTION":
            epistemic_shape = "open_question_reobservation"
            execution_stance = "DIRECT_OBSERVATION"
            provenance_class = "sandbox_distillation"
        elif source_kind == "constitution":
            epistemic_shape = "invariant_probe"
            execution_stance = "DIRECT_OBSERVATION"
            provenance_class = "local_constitution"
        elif source_kind == "museum_history":
            epistemic_shape = "historical_inventory_probe"
            execution_stance = "DIRECT_OBSERVATION"
            provenance_class = "local_museum"
        elif source_kind == "semantic_seed":
            epistemic_shape = "transferable_mechanism_pending_verification"
            execution_stance = "DIRECT_OBSERVATION"
            provenance_class = "source_preserving_semantic_seed"
        elif source_kind == "semantic_seed_unstructured":
            epistemic_shape = "raw_semantic_observation_pending_structure"
            execution_stance = "DIRECT_OBSERVATION"
            provenance_class = "sandbox_inbox"
        elif source_kind == "inbox":
            epistemic_shape = "untyped_inbound_probe"
            execution_stance = "DIRECT_OBSERVATION"
            provenance_class = "sandbox_inbox"
        elif source_kind == "local_git":
            epistemic_shape = "path_redacted_change_probe"
            execution_stance = "DIRECT_OBSERVATION"
            provenance_class = "local_git"
        elif source_kind == "external_catalog":
            epistemic_shape = "public_metadata_probe"
            execution_stance = "DIRECT_OBSERVATION"
            provenance_class = "public_metadata"
        elif source_kind == "external_repository_file":
            epistemic_shape = "public_shape_probe"
            execution_stance = "DIRECT_OBSERVATION"
            provenance_class = "public_repository_file"
        else:
            epistemic_shape = "unknown_probe"
            execution_stance = "DIRECT_OBSERVATION"
            provenance_class = "unknown"
        dimensions = {
            "source_kind": source_kind,
            "epistemic_shape": epistemic_shape,
            "execution_stance": execution_stance,
            "provenance_class": provenance_class,
        }
        if challenge_gap_signature is not None:
            dimensions["challenge_gap_signature"] = challenge_gap_signature
        slice_id = "|".join(f"{key}={dimensions[key]}" for key in sorted(dimensions))
        return {
            "schema_version": SEMANTIC_SLICE_SCHEMA_VERSION,
            "slice_id": slice_id,
            "dimensions": dimensions,
            "slice_basis": (
                ["candidate.source_kind", "candidate.challenge.missing_dimensions"]
                if challenge_gap_signature is not None
                else ["candidate.source_kind", "candidate.parent_status"]
            ),
            "descriptive_only": True,
            "outcome_used": False,
            "quality_score_used": False,
            "production_value_used": False,
        }

    @classmethod
    def allocate(
        cls,
        candidates: list[dict[str, Any]],
        *,
        limit: int,
        state: dict[str, Any],
        selection_seed: int,
    ) -> dict[str, Any]:
        """Select a bounded batch and mutate only sandbox allocation state.

        Source-kind round robin is retained as the outer fairness guard.  The
        inner draw favours *under-observed semantic slices*, based solely on
        prior allocation counts.  Every non-empty slice has a positive chance;
        no candidate is rejected because of its slice or past outcome.
        """
        if limit < 1:
            raise ValueError("limit must be positive")
        normalized_seed = int(selection_seed) & _MASK_64
        annotated = []
        for item in candidates:
            copy = dict(item)
            copy["semantic_slice"] = cls.describe(copy)
            annotated.append(copy)
        snapshot = [
            {
                "fingerprint": str(item.get("fingerprint", "")),
                "source_kind": str(item.get("source_kind", "unknown")),
                "semantic_slice_id": item["semantic_slice"]["slice_id"],
                # A Lazy Cat challenge is a signed, immutable input.  Retain
                # its existing digest as replay context without making that
                # digest, or any property it protects, an allocation weight.
                "source_record_hash": (
                    str(item["challenge"].get("challenge_hash", ""))
                    if isinstance(item.get("challenge"), Mapping)
                    else None
                ) or None,
            }
            for item in sorted(annotated, key=lambda item: str(item.get("fingerprint", "")))
        ]
        snapshot_hash = _digest(snapshot)
        base_report = {
            "contract_version": CONTRACT_VERSION,
            "policy": "source_fair_round_robin_then_semantic_slice_probability",
            "selection_policy_version": SELECTION_POLICY_VERSION,
            "semantic_slice_schema_version": SEMANTIC_SLICE_SCHEMA_VERSION,
            "selection_seed": normalized_seed,
            "prng_algorithm": "python.random.MT19937",
            "runtime_version": f"python-{sys.version_info.major}.{sys.version_info.minor}",
            "candidate_snapshot_sha256": snapshot_hash,
            "candidate_snapshot": snapshot,
            "quality_decision_performed": False,
            "outcome_used": False,
            "production_value_used": False,
            "automatic_production_promotion": False,
            "draws": [],
        }
        if not annotated:
            base_report["selected_count"] = 0
            return {"selected": [], "resource_selection": base_report}

        groups: dict[str, list[dict[str, Any]]] = {}
        for item in annotated:
            groups.setdefault(str(item.get("source_kind", "unknown")), []).append(item)
        source_kinds = sorted(groups)
        cursor = int(state.get("source_round_robin_cursor", 0)) % len(source_kinds)
        ordered_sources = source_kinds[cursor:] + source_kinds[:cursor]
        available = {
            source: sorted(items, key=lambda item: str(item.get("fingerprint", "")))
            for source, items in groups.items()
        }
        semantic_state = state.setdefault("semantic_exploration", {})
        raw_counts = semantic_state.get("slice_draw_counts", {})
        slice_draw_counts = {
            str(key): max(0, int(value))
            for key, value in raw_counts.items()
            if isinstance(key, str)
        } if isinstance(raw_counts, Mapping) else {}
        rng = random.Random(normalized_seed)
        selected: list[dict[str, Any]] = []
        draw_number = 0

        while len(selected) < limit:
            progressed = False
            for source in ordered_sources:
                options = available[source]
                if not options:
                    continue
                by_slice: dict[str, list[dict[str, Any]]] = {}
                for option in options:
                    by_slice.setdefault(option["semantic_slice"]["slice_id"], []).append(option)
                slice_ids = sorted(by_slice)
                counts_before = {slice_id: slice_draw_counts.get(slice_id, 0) for slice_id in slice_ids}
                weights = [1.0 / (1 + counts_before[slice_id]) for slice_id in slice_ids]
                slice_index, slice_draw = _draw_weighted_index(weights, rng)
                chosen_slice = slice_ids[slice_index]
                slice_probability = weights[slice_index] / sum(weights)
                members = sorted(by_slice[chosen_slice], key=lambda item: str(item.get("fingerprint", "")))
                member_index = rng.randrange(len(members))
                selected_item = members[member_index]
                candidate_probability = slice_probability / len(members)
                draw_number += 1
                allocation = {
                    "draw_number": draw_number,
                    "source_kind": source,
                    "semantic_slice": selected_item["semantic_slice"],
                    "slice_draw_counts_before": counts_before,
                    "slice_weights": [
                        {
                            "slice_id": slice_id,
                            "prior_draw_count": counts_before[slice_id],
                            "weight": weights[index],
                            "probability": weights[index] / sum(weights),
                            "candidate_count": len(by_slice[slice_id]),
                        }
                        for index, slice_id in enumerate(slice_ids)
                    ],
                    "slice_random_draw": slice_draw,
                    "member_index": member_index,
                    "candidate_probability": candidate_probability,
                    "selection_reason": "SOURCE_FAIR_ROUND_ROBIN_THEN_UNDERREPRESENTED_SEMANTIC_SLICE_DRAW",
                    "draw_state_digest": hashlib.sha256(repr(rng.getstate()).encode("utf-8")).hexdigest(),
                }
                enriched = dict(selected_item)
                enriched["allocation"] = allocation
                selected.append(enriched)
                options.remove(selected_item)
                slice_draw_counts[chosen_slice] = counts_before[chosen_slice] + 1
                base_report["draws"].append({
                    "draw_number": draw_number,
                    "selected_fingerprint": str(enriched.get("fingerprint", "")),
                    **allocation,
                })
                progressed = True
                if len(selected) >= limit:
                    break
            if not progressed:
                break

        state["source_round_robin_cursor"] = (cursor + 1) % len(source_kinds)
        semantic_state["slice_draw_counts"] = dict(sorted(slice_draw_counts.items()))
        semantic_state["last_selection_seed"] = normalized_seed
        semantic_state["turn_count"] = int(semantic_state.get("turn_count", 0)) + 1
        base_report["selected_count"] = len(selected)
        base_report["semantic_slice_count"] = len({item["semantic_slice"]["slice_id"] for item in annotated})
        base_report["slice_draw_counts_after"] = dict(sorted(slice_draw_counts.items()))
        return {"selected": selected, "resource_selection": base_report}
