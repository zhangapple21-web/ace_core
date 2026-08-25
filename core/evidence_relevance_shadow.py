"""Deterministic, shadow-only evidence relevance and lineage diagnostics.

This module has no TaskPool, Validator, daemon, model, or persistence
integration.  It reports lexical alignment, duplicate content, and explicit
lineage facts from an in-memory task snapshot.  Its findings are warnings,
never production admission or validation decisions.
"""

from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from datetime import datetime
from typing import Any, Iterable, Mapping


GENERIC_ARCHAEOLOGY_MARKERS = (
    "碎片考古",
    "启动碎片考古",
    "尚未考古",
    "未考古文件",
)

GENERIC_TERMS = {
    "核查",
    "复核",
    "分析",
    "处理",
    "任务",
    "证据",
    "问题",
    "研究",
    "结果",
    "compare",
    "review",
    "result",
    "task",
    "evidence",
}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _evidence_pair(item: Any) -> tuple[str, str]:
    if isinstance(item, Mapping):
        source = item.get("source", item.get("source_ref", ""))
        content = item.get(
            "content",
            item.get("detail", item.get("description", "")),
        )
        return _text(source), _text(content)
    return "", _text(item)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _tokens(value: str) -> set[str]:
    normalized = value.lower()
    tokens = {
        token
        for token in re.findall(r"[a-z_][a-z0-9_]{3,}", normalized)
        if token not in GENERIC_TERMS
    }
    for chunk in re.findall(r"[\u4e00-\u9fff]+", normalized):
        for size in (3, 4, 5):
            tokens.update(
                chunk[index:index + size]
                for index in range(max(0, len(chunk) - size + 1))
            )
    return {token for token in tokens if token not in GENERIC_TERMS}


def _query_context(task: Mapping[str, Any]) -> str:
    outputs = _mapping(task.get("outputs"))
    admission = _mapping(outputs.get("admission"))
    discovery = _mapping(outputs.get("discovery"))
    return "\n".join(
        filter(
            None,
            (
                _text(task.get("title")),
                _text(task.get("hypothesis")),
                _text(outputs.get("source_obs_description")),
                _text(admission.get("expected_result")),
                _text(admission.get("verification_method")),
                _text(discovery.get("objective")),
                _text(discovery.get("completion_criteria")),
            ),
        )
    )


def _query_specificity(task: Mapping[str, Any], query_tokens: set[str]) -> str:
    outputs = _mapping(task.get("outputs"))
    admission = _mapping(outputs.get("admission"))
    title = _text(task.get("title"))
    hypothesis = _text(task.get("hypothesis"))
    if not admission and any(marker in title or marker in hypothesis for marker in GENERIC_ARCHAEOLOGY_MARKERS):
        return "generic"
    return "specific" if query_tokens else "generic"


def _admission_records(task: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    outputs = _mapping(task.get("outputs"))
    admission = _mapping(outputs.get("admission"))
    records = admission.get("evidence", [])
    if not isinstance(records, list):
        return ()
    return tuple(item for item in records if isinstance(item, Mapping))


def _admission_source(item: Mapping[str, Any]) -> str:
    """Prefer the persisted provenance reference over a display source name."""
    return _text(item.get("source_ref") or item.get("source"))


def _admission_index(task: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    index: dict[str, Mapping[str, Any]] = {}
    for item in _admission_records(task):
        source = _admission_source(item)
        if source:
            index[source] = item
    return index


def _lineage(task: Mapping[str, Any]) -> dict[str, Any]:
    groups = set()
    upstreams = set()
    observable_count = 0
    unobservable_refs = []
    for item in _admission_records(task):
        source = _admission_source(item)
        metadata = _mapping(item.get("metadata"))
        upstream = _text(metadata.get("upstream_identity"))
        group = _text(metadata.get("independence_group"))
        explicitly_observable = metadata.get("lineage_observable") is True
        verified_upstream = bool(upstream) and not upstream.upper().startswith("UNVERIFIED")
        if explicitly_observable and verified_upstream:
            observable_count += 1
            upstreams.add(upstream)
            if group and not group.upper().startswith("UNVERIFIED"):
                groups.add(group)
        else:
            unobservable_refs.append(source)
    return {
        "admission_record_count": len(_admission_records(task)),
        "observable_count": observable_count,
        "upstream_count": len(upstreams),
        "upstream_identities": sorted(upstreams),
        "independent_group_count": len(groups),
        "independence_groups": sorted(groups),
        "unobservable_refs": sorted(filter(None, unobservable_refs)),
    }


def _duplicates(evidence: list[Any]) -> dict[str, Any]:
    pairs = [_evidence_pair(item) for item in evidence]
    pair_counts = Counter(pairs)
    exact_duplicate_count = sum(count - 1 for count in pair_counts.values() if count > 1)

    content_sources: dict[str, set[str]] = defaultdict(set)
    for source, content in pairs:
        if content:
            content_sources[_hash(content)].add(source)
    cross_source_groups = {
        content_hash: sorted(sources)
        for content_hash, sources in content_sources.items()
        if len(sources) > 1
    }
    return {
        "evidence_count": len(evidence),
        "unique_source_content_count": len(pair_counts),
        "exact_duplicate_count": exact_duplicate_count,
        "cross_source_duplicate_count": len(cross_source_groups),
        "cross_source_duplicate_groups": cross_source_groups,
    }


def evaluate_task(task: Mapping[str, Any]) -> dict[str, Any]:
    """Return warnings for one task without mutating it or making a verdict."""
    evidence = task.get("evidence", [])
    materialized = list(evidence) if isinstance(evidence, list) else []
    admission_index = _admission_index(task)
    query_tokens = _tokens(_query_context(task))
    specificity = _query_specificity(task, query_tokens)
    duplicate_facts = _duplicates(materialized)
    lineage = _lineage(task)
    records = []
    warnings = set()

    pair_first_index: dict[tuple[str, str], int] = {}
    content_first_source: dict[str, str] = {}
    for index, item in enumerate(materialized):
        source, content = _evidence_pair(item)
        pair = (source, content)
        content_hash = _hash(content) if content else ""
        record_warnings = []
        if pair in pair_first_index:
            record_warnings.append("exact_duplicate_evidence")
        else:
            pair_first_index[pair] = index
        if content_hash and content_hash in content_first_source and content_first_source[content_hash] != source:
            record_warnings.append("cross_source_content_duplicate")
        elif content_hash:
            content_first_source[content_hash] = source

        traced = source in admission_index
        if traced:
            relevance = "admission_traced"
            overlap = []
        elif specificity == "generic":
            relevance = "unassessed"
            overlap = []
        else:
            overlap = sorted(query_tokens & _tokens(f"{source}\n{content}"))
            relevance = "lexically_aligned" if overlap else "low_alignment"
            if relevance == "low_alignment":
                record_warnings.append("possible_semantic_contamination")

        warnings.update(record_warnings)
        records.append({
            "index": index,
            "source": source,
            "content_sha256": content_hash,
            "admission_trace": "traced" if traced else "untraced",
            "lexical_relevance": relevance,
            "overlap_tokens": overlap[:20],
            "warnings": record_warnings,
        })

    if specificity == "generic":
        warnings.add("generic_research_question")
    if duplicate_facts["exact_duplicate_count"]:
        warnings.add("exact_duplicate_evidence")
    if duplicate_facts["cross_source_duplicate_count"]:
        warnings.add("cross_source_content_duplicate")
    if materialized and lineage["observable_count"] == 0:
        warnings.add("lineage_unobservable")
    if len(materialized) >= 2 and lineage["independent_group_count"] < 2:
        warnings.add("source_independence_unverified")

    return {
        "mode": "shadow_only",
        "enforcement": False,
        "task_id": _text(task.get("task_id")),
        "status": _text(task.get("status")),
        "query_specificity": specificity,
        "warnings": sorted(warnings),
        "duplicates": duplicate_facts,
        "lineage": lineage,
        "relevance": {
            "admission_traced_count": sum(record["admission_trace"] == "traced" for record in records),
            "lexically_aligned_count": sum(record["lexical_relevance"] == "lexically_aligned" for record in records),
            "low_alignment_count": sum(record["lexical_relevance"] == "low_alignment" for record in records),
            "unassessed_count": sum(record["lexical_relevance"] == "unassessed" for record in records),
        },
        "evidence_records": records,
    }


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=None)


def _archived_in_window(task: Mapping[str, Any], start: datetime, end: datetime) -> bool:
    audit_log = task.get("audit_log", [])
    if not isinstance(audit_log, list):
        return False
    for event in audit_log:
        if not isinstance(event, Mapping):
            continue
        if event.get("event") != "transition" or event.get("to") != "archived":
            continue
        try:
            if start <= _parse_timestamp(_text(event.get("at"))) <= end:
                return True
        except ValueError:
            continue
    return False


def shadow_audit(
    tasks: Iterable[Mapping[str, Any]],
    *,
    start_at: str,
    end_at: str,
) -> dict[str, Any]:
    """Audit archived tasks in a window and aggregate warnings in memory."""
    start = _parse_timestamp(start_at)
    end = _parse_timestamp(end_at)
    selected = [task for task in tasks if _archived_in_window(task, start, end)]
    records = [evaluate_task(task) for task in selected]
    warning_counts = Counter(
        warning
        for record in records
        for warning in record["warnings"]
    )
    return {
        "mode": "shadow_only",
        "enforcement": False,
        "window": {"start": start_at, "end": end_at},
        "task_count": len(records),
        "warning_counts": dict(sorted(warning_counts.items())),
        "tasks_with_possible_semantic_contamination": sum(
            "possible_semantic_contamination" in record["warnings"]
            for record in records
        ),
        "records": records,
    }
