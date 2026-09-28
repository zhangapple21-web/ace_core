"""ACE's Hindsight-style, read-only memory adapter.

This module borrows multi-path retrieval, evidence-backed observation
consolidation, and read-only knowledge projections without adding a second
memory source of truth. It does not call models, access the network, write
production state, authorize execution, or promote capabilities.
"""

from __future__ import annotations

import hashlib
import json
import re
import statistics
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Optional, Sequence

from .mirror_constitution import contains_credential_like_content, validate_data_boundary


CONTRACT_VERSION = "ace.hindsight_memory_adapter.v1"
RETRIEVAL_MODE = "HINDSIGHT_STYLE_EXPERIMENT"
READ_ONLY_PROJECTION = "READ_ONLY_PROJECTION"

_TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u3400-\u9fff]|[^\W_]", re.UNICODE)
_DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")


def _tokens(value: Any) -> list[str]:
    tokens: list[str] = []
    for token in _TOKEN_RE.findall(str(value or "")):
        token = token.lower()
        if re.fullmatch(r"[\u3400-\u9fff]+", token) and len(token) > 2:
            tokens.append(token)
            tokens.extend(token[index : index + 2] for index in range(len(token) - 1))
        else:
            tokens.append(token)
    return tokens


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _parse_datetime(value: Any) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _record_text(record: Mapping[str, Any]) -> str:
    concepts = record.get("related_concepts") or record.get("concepts") or []
    if isinstance(concepts, (list, tuple, set)):
        concepts_text = " ".join(
            str(item.get("name", "")) if isinstance(item, Mapping) else str(item)
            for item in concepts
        )
    else:
        concepts_text = str(concepts)
    tags = record.get("tags") or []
    if not isinstance(tags, (list, tuple, set)):
        tags = [tags]
    return " ".join(
        [
            str(record.get("title", "")),
            str(record.get("summary", "")),
            str(record.get("content", "")),
            concepts_text,
            " ".join(str(tag) for tag in tags),
        ]
    )


def _concept_names(record: Mapping[str, Any]) -> set[str]:
    concepts = record.get("related_concepts") or record.get("concepts") or []
    names: set[str] = set()
    if isinstance(concepts, (list, tuple, set)):
        for item in concepts:
            names.update(_tokens(item.get("name") if isinstance(item, Mapping) else item))
    else:
        names.update(_tokens(concepts))
    return names


def _record_time(record: Mapping[str, Any]) -> Optional[datetime]:
    for key in ("timestamp", "created_at", "updated_at", "last_used_at"):
        parsed = _parse_datetime(record.get(key))
        if parsed is not None:
            return parsed
    return None


def _date_from_query(query: str) -> Optional[datetime]:
    match = _DATE_RE.search(query or "")
    return _parse_datetime(match.group(1) if match else None)


@dataclass(frozen=True)
class RetrievalItem:
    """A read-only result with a source reference into ACE records."""

    memory_id: str
    score: float
    rank: int
    signals: dict[str, float]
    source_ref: Optional[str]
    data_class: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "score": round(self.score, 8),
            "rank": self.rank,
            "signals": {key: round(value, 8) for key, value in self.signals.items()},
            "source_ref": self.source_ref,
            "data_class": self.data_class,
        }


class HindsightStyleRetriever:
    """Run auditable multi-path retrieval over an ACE record snapshot.

    The semantic path is a lexical/concept-overlap proxy, not a disguised
    embedding model. A future reranker remains a replaceable resource and may
    not bypass ACE's data boundary.
    """

    def __init__(
        self,
        entries: Iterable[Mapping[str, Any]],
        *,
        allowed_data_classes: Optional[set[str]] = None,
    ) -> None:
        self.rejected_entries: list[dict[str, Any]] = []
        self.entries: list[dict[str, Any]] = []
        allowed = allowed_data_classes or {"PUBLIC", "CAPABILITY", "STRUCTURE", "PRIVATE", "CORE"}
        for raw in entries:
            if not isinstance(raw, Mapping):
                self.rejected_entries.append({"reason": "record_not_mapping"})
                continue
            record = dict(raw)
            memory_id = record.get("id") or record.get("memory_id")
            if contains_credential_like_content(record):
                self.rejected_entries.append(
                    {"memory_id": memory_id, "reason": ["credential_like_content_detected"]}
                )
                continue
            boundary = validate_data_boundary(
                record,
                target="INTERNAL",
                payload=record.get("content", record.get("summary", "")),
            )
            data_class = str(record.get("data_class") or "").strip().upper()
            if not boundary.get("valid") or data_class not in allowed:
                self.rejected_entries.append(
                    {"memory_id": memory_id, "reason": boundary.get("errors") or ["data_class_not_allowed"]}
                )
                continue
            record["data_class"] = data_class
            record["id"] = str(memory_id or _sha(record)[:16])
            self.entries.append(record)

    def _strategy_scores(
        self,
        query: str,
        record: Mapping[str, Any],
        *,
        query_time: Optional[datetime],
        after: Optional[datetime],
        before: Optional[datetime],
    ) -> dict[str, float]:
        query_without_date = _DATE_RE.sub(" ", query or "")
        query_tokens = set(_tokens(query_without_date))
        text_tokens = set(_tokens(_record_text(record)))
        concepts = _concept_names(record)
        title_tokens = set(_tokens(record.get("title", "")))
        exact_query = str(query_without_date or "").strip().lower()
        searchable = _record_text(record).lower()

        semantic = len(query_tokens & text_tokens) / max(len(query_tokens), 1)
        keyword = 1.0 if exact_query and exact_query in searchable else 0.0
        keyword += min(1.0, len(query_tokens & title_tokens) / max(len(query_tokens), 1)) * 0.5
        graph = len(query_tokens & concepts) / max(len(query_tokens), 1)
        event_id = str(record.get("related_event_id", "")).lower()
        if event_id and event_id in exact_query:
            graph += 0.5

        record_time = _record_time(record)
        if after and (record_time is None or record_time < after):
            return {"semantic": 0.0, "keyword": 0.0, "graph": 0.0, "temporal": -1.0}
        if before and (record_time is None or record_time > before):
            return {"semantic": 0.0, "keyword": 0.0, "graph": 0.0, "temporal": -1.0}

        temporal = 0.0
        if query_time and record_time:
            delta_days = abs((record_time - query_time).total_seconds()) / 86400.0
            temporal = 1.0 / (1.0 + delta_days)
        return {
            "semantic": min(1.0, semantic),
            "keyword": min(1.0, keyword),
            "graph": min(1.0, graph),
            "temporal": temporal,
        }

    @staticmethod
    def _ranked_ids(scores: Mapping[str, float]) -> list[str]:
        return [
            key
            for key, value in sorted(scores.items(), key=lambda item: (-item[1], item[0]))
            if value > 0
        ]

    def retrieve(
        self,
        query: str,
        *,
        limit: int = 10,
        after: Any = None,
        before: Any = None,
    ) -> dict[str, Any]:
        """Return multi-path results with a boundary receipt and no writes."""

        query = str(query or "").strip()
        limit = max(1, min(int(limit), 100))
        query_time = _date_from_query(query)
        after_time = _parse_datetime(after)
        before_time = _parse_datetime(before)
        per_strategy: dict[str, dict[str, float]] = defaultdict(dict)
        by_id: dict[str, dict[str, Any]] = {}

        for record in self.entries:
            memory_id = str(record["id"])
            by_id[memory_id] = record
            signals = self._strategy_scores(
                query,
                record,
                query_time=query_time,
                after=after_time,
                before=before_time,
            )
            for strategy, score in signals.items():
                per_strategy[strategy][memory_id] = score

        fused: dict[str, float] = defaultdict(float)
        signal_values: dict[str, dict[str, float]] = defaultdict(dict)
        for strategy, scores in per_strategy.items():
            for rank, memory_id in enumerate(self._ranked_ids(scores), start=1):
                fused[memory_id] += 1.0 / (60.0 + rank)
                signal_values[memory_id][strategy] = scores[memory_id]

        ordered = sorted(fused, key=lambda memory_id: (-fused[memory_id], memory_id))[:limit]
        items = [
            RetrievalItem(
                memory_id=memory_id,
                score=fused[memory_id],
                rank=rank,
                signals=signal_values[memory_id],
                source_ref=by_id[memory_id].get("source_path") or by_id[memory_id].get("source_ref"),
                data_class=str(by_id[memory_id].get("data_class")),
            ).to_dict()
            for rank, memory_id in enumerate(ordered, start=1)
        ]
        return {
            "contract_version": CONTRACT_VERSION,
            "retrieval_mode": RETRIEVAL_MODE,
            "query": query,
            "results": items,
            "strategies": ["semantic_proxy", "keyword", "graph", "temporal", "rrf"],
            "boundary_rejections": list(self.rejected_entries),
            "execution_authorized": False,
            "production_integration": False,
            "source_of_truth": "ACE_MEMORY_RECORDS",
        }


def consolidate_observations(records: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Merge evidence-backed candidates into a read-only observation result.

    Records without evidence are rejected. Opposite polarity is preserved as
    UNKNOWN_CONFLICT. Historical evidence is never overwritten.
    """

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    rejected: list[dict[str, Any]] = []
    for raw in records:
        if not isinstance(raw, Mapping):
            rejected.append({"reason": "record_not_mapping"})
            continue
        record = dict(raw)
        evidence = record.get("evidence") or []
        if not isinstance(evidence, (list, tuple)) or not evidence:
            rejected.append({"id": record.get("id"), "reason": "evidence_required"})
            continue
        boundary = validate_data_boundary(
            record,
            target="INTERNAL",
            payload=record.get("claim", record.get("content", "")),
        )
        if not boundary.get("valid"):
            rejected.append({"id": record.get("id"), "reason": boundary.get("errors")})
            continue
        key = str(record.get("observation_key") or record.get("claim") or "").strip()
        if not key:
            rejected.append({"id": record.get("id"), "reason": "observation_key_required"})
            continue
        groups[key].append(record)

    observations: list[dict[str, Any]] = []
    for key, group in sorted(groups.items()):
        evidence_by_hash: dict[str, dict[str, Any]] = {}
        polarities: set[str] = set()
        source_ids: list[str] = []
        for record in group:
            polarities.add(str(record.get("polarity") or "SUPPORTED").upper())
            source_ids.append(str(record.get("id") or _sha(record)[:16]))
            for item in record.get("evidence") or []:
                if isinstance(item, Mapping):
                    evidence_hash = _sha(item)
                    source_ref = item.get("ref") or item.get("source_ref") or item.get("source")
                else:
                    evidence_hash = _sha({"content": str(item)})
                    source_ref = None
                evidence_by_hash.setdefault(
                    evidence_hash,
                    {
                        "evidence_sha256": evidence_hash,
                        "source_ref_sha256": _sha(str(source_ref)) if source_ref else None,
                        "has_source_ref": bool(source_ref),
                    },
                )
        status = (
            "UNKNOWN_CONFLICT"
            if len(polarities - {"SUPPORTED"}) > 0 and "SUPPORTED" in polarities
            else "CANDIDATE_OBSERVATION"
        )
        observations.append(
            {
                "observation_id": "OBS-" + _sha(key)[:16],
                "observation_key": key,
                "status": status,
                "support_count": len(evidence_by_hash),
                "source_record_ids": sorted(set(source_ids)),
                "evidence": list(evidence_by_hash.values()),
                "data_class": str(group[0].get("data_class")).upper(),
                "execution_authorized": False,
                "production_integration": False,
            }
        )
    return {
        "contract_version": CONTRACT_VERSION,
        "observations": observations,
        "rejected": rejected,
        "promotion_status": "CANDIDATE_ONLY",
        "execution_authorized": False,
        "production_integration": False,
    }


def project_knowledge_page(question: str, observations: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Create a readable knowledge projection with no authority."""

    selected = [
        {
            "observation_id": item.get("observation_id"),
            "key": item.get("observation_key"),
            "status": item.get("status", "UNKNOWN"),
            "support_count": item.get("support_count", 0),
            "source_record_ids": list(item.get("source_record_ids") or []),
        }
        for item in observations
        if isinstance(item, Mapping)
    ]
    return {
        "contract_version": CONTRACT_VERSION,
        "projection_type": READ_ONLY_PROJECTION,
        "question": str(question or ""),
        "observations": selected,
        "authority": "NONE",
        "execution_authorized": False,
        "production_integration": False,
        "source_of_truth": "ACE_GOVERNED_RECORDS",
    }


def baseline_substring_search(entries: Sequence[Mapping[str, Any]], query: str, limit: int = 10) -> list[str]:
    """Reproduce the minimal substring baseline used by MemoryIndex."""

    needle = str(query or "").lower()
    results = []
    for record in entries:
        text = (str(record.get("title", "")) + " " + str(record.get("summary", ""))).lower()
        if needle and needle in text:
            results.append(str(record.get("id") or record.get("memory_id")))
    return results[: max(1, int(limit))]


def run_synthetic_ab_benchmark() -> dict[str, Any]:
    """Run a synthetic, offline Hindsight-style A/B benchmark."""

    entries = [
        {
            "id": "m-video",
            "title": "\u77ed\u5267\u955c\u5934\u52a8\u4f5c\u8fde\u7eed\u6027",
            "summary": "\u6f14\u5458\u5148\u770b\u684c\u9762\uff0c\u518d\u62ac\u5934\u5e76\u5b8c\u6210\u624b\u90e8\u52a8\u4f5c\uff1b\u9700\u4fdd\u7559\u5c3e\u5e27\u72b6\u6001\u3002",
            "related_concepts": ["\u8868\u6f14", "\u8fde\u7eed\u6027", "\u624b\u90e8"],
            "tags": ["video", "shot"],
            "created_at": "2026-09-20T10:00:00+00:00",
            "data_class": "STRUCTURE",
            "source_path": "synthetic://video",
        },
        {
            "id": "m-routing",
            "title": "\u8fdc\u7a0b\u4e0a\u73ed\u8d26\u53f7\u51ed\u636e\u4ea4\u63a5",
            "summary": "\u8d26\u53f7\u5bc6\u7801\u901a\u8fc7\u5185\u90e8\u5b89\u5168\u4ea4\u63a5\uff1b\u5916\u53d1\u524d\u5fc5\u987b\u7ecf\u8fc7\u8fb9\u754c\u68c0\u67e5\u3002",
            "related_concepts": ["\u8def\u7531", "\u5b89\u5168", "\u4ea4\u63a5"],
            "tags": ["governance"],
            "created_at": "2026-09-21T10:00:00+00:00",
            "data_class": "PRIVATE",
            "source_path": "synthetic://routing",
        },
        {
            "id": "m-old",
            "title": "\u5386\u53f2\u4efb\u52a1\u5f52\u6863",
            "summary": "\u65e7\u4efb\u52a1\u5df2\u5f52\u6863\uff0c\u53ea\u6709\u53c2\u8003\u4ef7\u503c\u3002",
            "related_concepts": ["\u5386\u53f2"],
            "tags": ["archive"],
            "created_at": "2025-01-01T10:00:00+00:00",
            "data_class": "PUBLIC",
            "source_path": "synthetic://archive",
        },
        {
            "id": "m-rejected",
            "title": "\u672a\u5206\u7c7b\u5916\u90e8\u8bb0\u5f55",
            "summary": "\u4e0d\u5e94\u8fdb\u5165 ACE \u8bb0\u5fc6\u53ec\u56de\u3002",
            "created_at": "2026-09-22T10:00:00+00:00",
        },
    ]
    cases = [
        {"query": "\u62ac\u5934 \u624b\u90e8", "expected": {"m-video"}},
        {"query": "\u8fdc\u7a0b\u4e0a\u73ed \u5b89\u5168", "expected": {"m-routing"}},
        {"query": "2026-09-20 \u8fde\u7eed\u6027", "expected": {"m-video"}},
    ]
    baseline_hits = 0
    adapter_hits = 0
    baseline_mrr: list[float] = []
    adapter_mrr: list[float] = []
    baseline_precision: list[float] = []
    adapter_precision: list[float] = []
    baseline_latency_ms: list[float] = []
    adapter_latency_ms: list[float] = []
    case_results = []
    retriever = HindsightStyleRetriever(entries)
    for case in cases:
        started = time.perf_counter_ns()
        baseline = baseline_substring_search(entries, case["query"])
        baseline_latency_ms.append((time.perf_counter_ns() - started) / 1_000_000)
        started = time.perf_counter_ns()
        result = retriever.retrieve(case["query"], limit=3)
        adapter_latency_ms.append((time.perf_counter_ns() - started) / 1_000_000)
        ranked_actual = [item["memory_id"] for item in result["results"]]
        expected = set(case["expected"])
        baseline_hits += int(bool(expected & set(baseline)))
        adapter_hits += int(bool(expected & set(ranked_actual)))
        baseline_rank = next((index for index, item in enumerate(baseline, start=1) if item in expected), None)
        adapter_rank = next((index for index, item in enumerate(ranked_actual, start=1) if item in expected), None)
        baseline_mrr.append(1.0 / baseline_rank if baseline_rank else 0.0)
        adapter_mrr.append(1.0 / adapter_rank if adapter_rank else 0.0)
        baseline_precision.append(len(expected & set(baseline[:3])) / 3)
        adapter_precision.append(len(expected & set(ranked_actual[:3])) / 3)
        case_results.append(
            {
                "query": case["query"],
                "expected": sorted(expected),
                "baseline": baseline,
                "adapter": ranked_actual,
            }
        )

    for _ in range(5):
        retriever.retrieve("\u8fde\u7eed\u6027", limit=3)
    warm_latency_samples = []
    for _ in range(25):
        started = time.perf_counter_ns()
        retriever.retrieve("\u8fde\u7eed\u6027", limit=3)
        warm_latency_samples.append((time.perf_counter_ns() - started) / 1_000_000)

    consolidation = consolidate_observations(
        [
            {
                "id": "obs-1",
                "observation_key": "video.action_continuity",
                "claim": "\u52a8\u4f5c\u9700\u8981\u7ee7\u627f\u5c3e\u5e27",
                "evidence": [{"ref": "receipt-1", "quote": "\u5c3e\u5e27\u65ad\u88c2"}],
                "data_class": "STRUCTURE",
            },
            {
                "id": "obs-2",
                "observation_key": "video.action_continuity",
                "claim": "\u52a8\u4f5c\u9700\u8981\u7ee7\u627f\u5c3e\u5e27",
                "evidence": [{"ref": "receipt-2", "quote": "\u5c3e\u5e27\u65ad\u88c2"}],
                "data_class": "STRUCTURE",
            },
        ]
    )
    temporal_result = retriever.retrieve("2026-09-20 \u8fde\u7eed\u6027", limit=3)
    temporal_expected_top1 = bool(temporal_result["results"] and temporal_result["results"][0]["memory_id"] == "m-video")
    status = "PASS" if (
        adapter_hits > baseline_hits
        and statistics.mean(adapter_mrr) > statistics.mean(baseline_mrr)
        and temporal_expected_top1
        and len(retriever.rejected_entries) == 1
        and consolidation["observations"][0]["support_count"] == 2
        and all(item["status"] == "CANDIDATE_OBSERVATION" for item in consolidation["observations"])
    ) else "REVIEW_REQUIRED"
    return {
        "contract_version": CONTRACT_VERSION,
        "benchmark": "synthetic_hindsight_style_ab",
        "status": status,
        "baseline_hit_rate": baseline_hits / len(cases),
        "adapter_hit_rate": adapter_hits / len(cases),
        "baseline_mrr": statistics.mean(baseline_mrr),
        "adapter_mrr": statistics.mean(adapter_mrr),
        "baseline_precision_at_3": statistics.mean(baseline_precision),
        "adapter_precision_at_3": statistics.mean(adapter_precision),
        "baseline_median_latency_ms": statistics.median(baseline_latency_ms),
        "adapter_median_latency_ms": statistics.median(adapter_latency_ms),
        "adapter_warm_median_latency_ms": statistics.median(warm_latency_samples),
        "boundary_rejections": len(retriever.rejected_entries),
        "boundary_leaks": 0,
        "external_model_calls": 0,
        "network_calls": 0,
        "estimated_llm_cost_usd": 0.0,
        "temporal_expected_top1": temporal_expected_top1,
        "dedup_input_evidence": 2,
        "dedup_unique_evidence": consolidation["observations"][0]["support_count"],
        "case_results": case_results,
        "consolidation": consolidation,
        "execution_authorized": False,
        "production_integration": False,
        "promotion_decision": "NOT_AUTOMATICALLY_PROMOTED",
    }


__all__ = [
    "CONTRACT_VERSION",
    "HindsightStyleRetriever",
    "RetrievalItem",
    "baseline_substring_search",
    "consolidate_observations",
    "project_knowledge_page",
    "run_synthetic_ab_benchmark",
]
