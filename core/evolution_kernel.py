"""ACE Evolution Kernel: one governed bridge from observation to capability.

This module is deliberately small and deterministic.  It does not run models,
grant execution rights, install external code, or create media tasks.  It
normalizes evidence from ACE branches (including Video Kingdom), chooses the
best existing learning path, and applies the same promotion/rollback gate to
every candidate.

The kernel is a contract and a receipt producer; the existing DailyLearning,
TaskPool, MinerPool, Guardian, and LearningReturnBridge remain the executors.
That keeps this layer from becoming a second scheduler or a parallel memory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


SCHEMA = "ace.evolution_kernel.packet.v1"
PROMOTION_STATUSES = {
    "PROMOTE",
    "ROLLBACK_REQUIRED",
    "REJECTED_NO_MEASURABLE_GAIN",
    "REJECTED_MISSING_PAINFUL_REVIEW",
    "BLOCKED_INSUFFICIENT_EVIDENCE",
}

# Internal failure evidence is more valuable than a new external idea.  The
# order is intentional: it makes the system repair repeated local failure
# before it goes shopping for another framework.
SOURCE_PRIORITY = {
    "internal_failure": 0,
    "internal_metric": 1,
    "video_receipt": 2,
    "local_experiment": 3,
    "external_primary": 4,
    "external_secondary": 5,
    "user_reference": 6,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _unique_strings(values: Any) -> list[str]:
    if values is None:
        return []
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, (list, tuple, set)):
        return []
    output: list[str] = []
    for value in values:
        value = str(value).strip()
        if value and value not in output:
            output.append(value)
    return output


def _as_bool(value: Any) -> bool:
    """Parse boolean evidence without treating the string ``"false"`` as true."""

    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "passed", "pass", "改善", "通过"}
    return False


def _sha(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def normalize_observation(observation: dict[str, Any] | None, *, source_ref: str = "") -> dict[str, Any]:
    """Convert a loose observation into the ACE fact/evidence boundary.

    Text from chats, files, tool output, or remote repositories is never
    treated as a fact automatically.  ``facts`` are claims already supported
    by the caller; ``inferences`` and ``unknowns`` remain explicitly separate.
    """

    raw = observation if isinstance(observation, dict) else {}
    normalized = {
        "facts": _unique_strings(raw.get("facts")),
        "evidence": _unique_strings(raw.get("evidence") or raw.get("evidence_refs")),
        "inferences": _unique_strings(raw.get("inferences") or raw.get("inference")),
        "unknowns": _unique_strings(raw.get("unknowns")),
        "experience": _unique_strings(raw.get("experience") or raw.get("lessons")),
        "source_refs": _unique_strings(raw.get("source_refs") or raw.get("sources")),
        "tags": _unique_strings(raw.get("tags")),
    }
    if source_ref and source_ref not in normalized["source_refs"]:
        normalized["source_refs"].append(source_ref)
    normalized["observation_sha256"] = _sha(normalized)
    return normalized


def route_learning(candidates: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Choose one bounded learning target without creating a new queue.

    Existing internal evidence wins over external inspiration.  Ties are
    resolved deterministically by candidate id, so a replay cannot send work
    down a different route merely because dictionary order changed.
    """

    items: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        source_kind = str(candidate.get("source_kind") or "external_secondary").strip().lower()
        item = dict(candidate)
        item["source_kind"] = source_kind
        item["evidence_count"] = len(normalize_observation(candidate.get("observation")).get("evidence", []))
        item["priority_rank"] = SOURCE_PRIORITY.get(source_kind, 99)
        items.append(item)
    if not items:
        return {"status": "NO_TARGET", "selected": None, "reason": "no_candidates"}
    items.sort(key=lambda item: (
        item["priority_rank"],
        -int(item.get("evidence_count", 0)),
        str(item.get("candidate_id") or item.get("title") or ""),
    ))
    selected = items[0]
    return {
        "status": "SELECTED",
        "selected": selected,
        "considered": [item.get("candidate_id") or item.get("title") for item in items],
        "reason": "internal_evidence_first" if selected["priority_rank"] < SOURCE_PRIORITY["external_primary"] else "no_higher_confidence_internal_target",
    }


def assess_promotion(experiment: dict[str, Any] | None) -> dict[str, Any]:
    """Apply the non-negotiable baseline/change/test/evaluation gate."""

    exp = experiment if isinstance(experiment, dict) else {}
    required = ("baseline", "change", "test", "evaluation", "comparison")
    missing = [field for field in required if not exp.get(field)]
    if missing:
        return {"status": "BLOCKED_INSUFFICIENT_EVIDENCE", "missing": missing, "execution_authorized": False}
    test = exp.get("test")
    if isinstance(test, dict):
        test_passed = _as_bool(test.get("passed"))
    else:
        test_passed = _as_bool(test)
    if not test_passed:
        return {"status": "ROLLBACK_REQUIRED", "reason": "test_failed", "execution_authorized": False}
    evaluation = exp.get("evaluation")
    regressed = _as_bool(exp.get("regression")) or (isinstance(evaluation, dict) and _as_bool(evaluation.get("regression")))
    if regressed:
        return {"status": "ROLLBACK_REQUIRED", "reason": "regression_detected", "execution_authorized": False}
    painful = exp.get("painful_review")
    if not isinstance(painful, dict) or not all(str(painful.get(key, "")).strip() for key in ("cost", "counterfactual", "recurrence_risk", "reusable_lesson")):
        return {"status": "REJECTED_MISSING_PAINFUL_REVIEW", "execution_authorized": False}
    measurable_gain = _as_bool(exp.get("measurable_gain")) or (isinstance(evaluation, dict) and _as_bool(evaluation.get("measurable_gain")))
    if not measurable_gain:
        return {"status": "REJECTED_NO_MEASURABLE_GAIN", "execution_authorized": False}
    return {"status": "PROMOTE", "execution_authorized": False, "reason": "evidence_and_painful_review_passed"}


def make_packet(
    *,
    scope: str,
    candidate: dict[str, Any],
    observation: dict[str, Any] | None = None,
    experiment: dict[str, Any] | None = None,
    next_tasks: list[str] | None = None,
) -> dict[str, Any]:
    """Create a stable packet consumed by existing ACE governance components."""

    normalized = normalize_observation(observation or candidate.get("observation"), source_ref=str(candidate.get("source_ref") or ""))
    decision = assess_promotion(experiment) if experiment is not None else {
        "status": "RESEARCH",
        "execution_authorized": False,
        "reason": "candidate_requires_existing_task_pool_validation",
    }
    packet = {
        "schema": SCHEMA,
        "scope": str(scope or "ace"),
        "candidate_id": str(candidate.get("candidate_id") or candidate.get("title") or "unknown"),
        "title": str(candidate.get("title") or "untitled"),
        "source_kind": str(candidate.get("source_kind") or "unknown"),
        "source_content_key": str(candidate.get("source_content_key") or ""),
        "source_status": str(candidate.get("source_status") or ""),
        "source_refs": _unique_strings(candidate.get("source_refs")) + [ref for ref in normalized["source_refs"] if ref not in _unique_strings(candidate.get("source_refs"))],
        "observation": normalized,
        "experiment": experiment if isinstance(experiment, dict) else None,
        "decision": decision,
        "next_tasks": _unique_strings(next_tasks),
        "execution_authorized": False,
        "production_integration": False,
        "created_at": _now(),
    }
    stable = dict(packet)
    stable.pop("created_at", None)
    packet["packet_id"] = "EK-" + _sha(stable)[:20]
    packet["packet_sha256"] = _sha({key: value for key, value in packet.items() if key not in {"packet_sha256", "created_at"}})
    return packet


def ingest_video_run(path: str | Path) -> list[dict[str, Any]]:
    """Convert a Video Kingdom learning receipt into ACE packets.

    A receipt is evidence of an observation, not a promotion.  This is the
    only intended cross-branch direction for the learning bridge.
    """

    source_path = Path(path).resolve()
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema") != "video_kingdom.external_learning_run.v1":
        raise ValueError("unsupported_video_learning_receipt_schema")
    if payload.get("source_boundary") != "PUBLIC_PRIMARY_SOURCES_ONLY":
        raise ValueError("video_learning_receipt_source_boundary_not_public_primary")
    promotion = payload.get("promotion")
    if not isinstance(promotion, dict) or promotion.get("status") not in {"NONE", "REVIEW_REQUIRED", None}:
        raise ValueError("video_learning_receipt_already_promoted")
    if payload.get("production_integration") is True or payload.get("execution_authorized") is True:
        raise ValueError("video_learning_receipt_has_execution_authority")
    records = payload.get("records", []) if isinstance(payload, dict) else []
    if not isinstance(records, list) or not records:
        raise ValueError("video_learning_receipt_records_missing")
    packets: list[dict[str, Any]] = []
    for index, record in enumerate(records if isinstance(records, list) else []):
        if not isinstance(record, dict):
            continue
        status = str(record.get("status") or "UNKNOWN").upper()
        if status in {"UNCHANGED", "NO_NEW_EVIDENCE"}:
            continue
        if record.get("production_authority") not in {None, "", "NONE"}:
            raise ValueError("video_learning_record_has_production_authority")
        if record.get("production_integration") is True or str(record.get("promotion_status") or "").upper() in {"PROMOTED", "PRODUCTION"}:
            raise ValueError("video_learning_record_already_promoted")
        source_id = str(record.get("source_id") or f"record-{index}")
        status = str(record.get("status") or "UNKNOWN")
        observation = {
            "facts": [f"video_learning_receipt_status:{status}"],
            "evidence": [str(record.get("readme_sha256"))] if record.get("readme_sha256") else [],
            "unknowns": ["local production benefit not yet proven"],
            "experience": [],
            "source_refs": [str(record.get("readme_url"))] if record.get("readme_url") else [str(source_path)],
            "tags": ["video_kingdom", "external_learning"],
        }
        candidate = {
            "candidate_id": f"video:{payload.get('run_id', source_path.stem)}:{source_id}",
            "title": f"Video Kingdom external learning: {source_id}",
            "source_kind": "video_receipt",
            "source_ref": str(source_path),
            "source_content_key": str(record.get("source_content_key") or ""),
            "source_status": status,
            "source_refs": [str(record.get("api_url"))] if record.get("api_url") else [],
            "observation": observation,
        }
        packets.append(make_packet(scope="video", candidate=candidate, observation=observation, next_tasks=["用本地虚构样本做隔离 A/B", "补 baseline/change/test/evaluation/painful_review 后再判定"]))
    return packets


def append_packets(packets: Iterable[dict[str, Any]], out_path: str | Path) -> dict[str, Any]:
    """Append packets idempotently to an ACE receipt stream."""

    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    existing_ids: set[str] = set()
    existing_content_keys: set[str] = set()
    if target.exists():
        for line in target.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict) and item.get("packet_id"):
                existing_ids.add(str(item["packet_id"]))
                content_key = str(item.get("source_content_key") or "")
                if content_key:
                    existing_content_keys.add(content_key)
    added = 0
    with target.open("a", encoding="utf-8") as handle:
        for packet in packets:
            packet_id = str(packet.get("packet_id") or "")
            content_key = str(packet.get("source_content_key") or "")
            if not packet_id or packet_id in existing_ids or (content_key and content_key in existing_content_keys):
                continue
            handle.write(json.dumps(packet, ensure_ascii=False, sort_keys=True) + "\n")
            existing_ids.add(packet_id)
            if content_key:
                existing_content_keys.add(content_key)
            added += 1
    return {"status": "RECORDED", "out": str(target), "added": added, "total_seen": len(existing_ids)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ingest-video-run", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    if not args.ingest_video_run:
        parser.error("--ingest-video-run is required")
    packets = ingest_video_run(args.ingest_video_run)
    result = {"status": "NO_OUTPUT", "packets": len(packets)}
    if args.out:
        result = append_packets(packets, args.out)
        result["packets"] = len(packets)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "SCHEMA",
    "normalize_observation",
    "route_learning",
    "assess_promotion",
    "make_packet",
    "ingest_video_run",
    "append_packets",
]
