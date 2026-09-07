"""Research-only market-context records.

This module records how public discussion, institutional/public commentary and
sector narratives relate to already observed market facts.  It deliberately
does not fetch sources, score a security, generate a recommendation, or alter
market-data admission.  Its output is an auditable list of corroborations and
questions for a human researcher to verify.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


CONTRACT_VERSION = "ace.market_context_research.v1"
_ALLOWED_SOURCE_ROLES = frozenset({
    "market_fact", "institutional_public", "sector_news", "short_term_flow", "community_discussion",
})


def _canonical_hash(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _evidence_item(value: Mapping[str, Any]) -> dict[str, Any]:
    required = {"source_role", "source_ref", "observed_at", "summary"}
    if not required.issubset(value):
        raise ValueError("market context evidence is incomplete")
    role = str(value["source_role"])
    if role not in _ALLOWED_SOURCE_ROLES:
        raise ValueError("market context source_role is not allowed")
    source_ref = str(value["source_ref"]).strip()
    summary = str(value["summary"]).strip()
    if not source_ref or not summary:
        raise ValueError("market context source_ref and summary must be non-empty")
    return {
        "source_role": role,
        "source_ref": source_ref,
        "observed_at": str(value["observed_at"]),
        "summary": summary,
        "content_hash": str(value.get("content_hash") or _canonical_hash(value)),
        "upstream_identity": str(value.get("upstream_identity", "UNVERIFIED")),
        "lineage_observable": value.get("lineage_observable") is True,
    }


def build_market_context_research(
    *,
    market_date: str,
    observed_at: str,
    market_facts: Sequence[Mapping[str, Any]],
    context_evidence: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build a research-only cross-validation record.

    Context may surface a question or disagreement; it cannot turn an
    unverified discussion item into a market fact or a recommendation signal.
    """
    facts = [_evidence_item({**item, "source_role": "market_fact"}) for item in market_facts]
    context = [_evidence_item(item) for item in context_evidence]
    if not facts:
        raise ValueError("market context requires at least one market fact")
    if not context:
        raise ValueError("market context requires at least one context evidence item")

    questions = []
    for item in context:
        if item["source_role"] == "community_discussion" or not item["lineage_observable"]:
            questions.append({
                "source_ref": item["source_ref"],
                "question": "Does this public discussion claim have an independent, time-stamped primary or editorial source?",
                "status": "UNVERIFIED_CONTEXT",
            })
    return {
        "contract_version": CONTRACT_VERSION,
        "market_date": str(market_date),
        "observed_at": str(observed_at),
        "research_status": "RESEARCH_ONLY",
        "recommendation_authority": False,
        "market_data_admission_changed": False,
        "market_facts": facts,
        "context_evidence": context,
        "cross_validation_questions": questions,
        "conclusion": "Context evidence is supplementary research only; validate disagreement against traceable market facts before any human review.",
    }


def write_market_context_research(path: str | Path, record: Mapping[str, Any]) -> Path:
    """Atomically persist a validated research-only context record."""
    if record.get("contract_version") != CONTRACT_VERSION:
        raise ValueError("unsupported market context contract")
    if record.get("research_status") != "RESEARCH_ONLY" or record.get("recommendation_authority") is not False:
        raise ValueError("market context must remain research-only")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        handle.flush()
        import os
        os.fsync(handle.fileno())
    import os
    os.replace(temporary, target)
    return target
