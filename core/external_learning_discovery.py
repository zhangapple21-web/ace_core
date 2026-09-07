"""Bounded external evidence discovery for the existing DailyLearningLoop.

This is deliberately *not* a replacement for WebScout.  WebScout's legacy
``scout`` entrypoint deposits concepts, memory, and tasks itself.  This module
only reads a small, configured public metadata feed and returns candidates when
their evidence already meets the normal independence contract.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Tuple
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

from .discovery import DiscoveryCandidate


class ExternalLearningDiscovery:
    """Read-only discovery adapter with an inspectable last-result status."""

    DEFAULT_SOURCES = ({
        "id": "github_ace_research",
        "type": "github_search",
        "query": "ACE agent runtime evidence governance",
        "max_results": 3,
    },)

    def __init__(
        self,
        sources: List[Dict[str, Any]] | None = None,
        fetch_json: Callable[[str], Dict[str, Any]] | None = None,
    ) -> None:
        self.sources = list(sources or self.DEFAULT_SOURCES)
        self._fetch_json = fetch_json or self._http_json
        self.last_result: Dict[str, Any] = {
            "status": "NOT_EXECUTED",
            "reason": "external_discovery_not_yet_run",
            "sources_checked": 0,
            "findings": 0,
        }

    def discover(
        self, objective: str, source_tiers: List[str]
    ) -> List[Tuple[DiscoveryCandidate, List[Dict[str, Any]]]]:
        """Return only independently corroborated candidates; never persists."""
        findings: List[Tuple[DiscoveryCandidate, List[Dict[str, Any]]]] = []
        unavailable: List[str] = []
        insufficient = 0
        checked = 0
        for source in self.sources:
            if source.get("type") != "github_search":
                continue
            checked += 1
            try:
                payload = self._fetch_json(self._github_search_url(source))
            except Exception as error:  # Network failure is a governed result.
                unavailable.append(f"{source.get('id', 'unknown')}:{type(error).__name__}")
                continue
            for item in payload.get("items", [])[: int(source.get("max_results", 3))]:
                if not self._relevant(item, objective):
                    continue
                evidence = self._evidence_for(item, source)
                # GitHub discovery gives one attributable upstream, which is
                # useful for observation but intentionally cannot create Work.
                if len({x["metadata"]["independence_group"] for x in evidence}) < 2:
                    insufficient += 1
                    continue
                candidate = self._candidate_for(item, evidence)
                findings.append((candidate, evidence))

        if findings:
            status, reason = "EXTERNAL_CANDIDATE_FOUND", "independent_evidence_available"
        elif unavailable and checked == len(unavailable):
            status, reason = "SOURCE_UNAVAILABLE", "all_configured_sources_unavailable"
        elif insufficient:
            status, reason = "CANDIDATE_FOUND_BUT_INSUFFICIENT_EVIDENCE", "single_upstream_discovery_is_not_work"
        else:
            status, reason = "EXECUTED_NO_CANDIDATE", "no_relevant_external_finding"
        self.last_result = {
            "status": status, "reason": reason, "sources_checked": checked,
            "findings": len(findings), "insufficient_findings": insufficient,
            "unavailable_sources": unavailable,
        }
        return findings

    @staticmethod
    def _github_search_url(source: Dict[str, Any]) -> str:
        query = quote_plus(str(source.get("query", "ACE")))
        return f"https://api.github.com/search/repositories?q={query}&sort=updated&per_page={int(source.get('max_results', 3))}"

    @staticmethod
    def _http_json(url: str) -> Dict[str, Any]:
        request = Request(url, headers={"User-Agent": "ACE-ExternalLearning/1.0", "Accept": "application/vnd.github+json"})
        with urlopen(request, timeout=8) as response:
            data = json.loads(response.read().decode("utf-8"))
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _relevant(item: Dict[str, Any], objective: str) -> bool:
        text = " ".join(str(item.get(key, "")) for key in ("name", "full_name", "description")).lower()
        terms = ("agent", "runtime", "govern", "evidence", "memory", "cognitive", "orchestrat", "workflow")
        return bool(item.get("html_url")) and any(term in text for term in terms)

    @staticmethod
    def _evidence_for(item: Dict[str, Any], source: Dict[str, Any]) -> List[Dict[str, Any]]:
        url = str(item["html_url"])
        content = json.dumps({key: item.get(key) for key in ("full_name", "description", "updated_at", "default_branch")}, ensure_ascii=False, sort_keys=True)
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        repository = str(item.get("full_name") or url)
        return [{
            "source": "github_repository_metadata",
            "source_ref": f"{url}#sha256={digest}", "content": content,
            "confidence": 0.55, "author": repository, "source_location": url,
            "metadata": {
                "source_tier": "technical_primary", "publisher": repository,
                "upstream_identity": f"github_repo:{repository}",
                "independence_group": f"github_repo:{repository}",
                "lineage_observable": True, "directness": "primary",
                "retrieval_method": "bounded_external_discovery",
                "cross_validation_source": "external",
                "retrieved_at": datetime.now(timezone.utc).isoformat(),
                "content_hash": digest, "discovery_source": source.get("id"),
            },
        }]

    @staticmethod
    def _candidate_for(item: Dict[str, Any], evidence: List[Dict[str, Any]]) -> DiscoveryCandidate:
        name = str(item.get("full_name") or item.get("name"))
        return DiscoveryCandidate(
            fingerprint=f"external_learning:{hashlib.sha256(name.encode('utf-8')).hexdigest()[:16]}",
            title=f"外部考古 {name}",
            description="External material is an evidence-backed research hypothesis, never an installed capability.",
            reason="Independent, attributable external evidence indicates a concrete ACE learning question.",
            objective=f"Evaluate {name} against ACE governance and portability boundaries without installation.",
            completion_criteria="Record evidence-backed ABSORB, ADAPT, CONFLICT, REDUNDANT, or REJECT.",
            verification_method="Recheck each evidence reference and ACE compatibility evidence.",
            priority="medium", task_type="reasoning", severity="medium",
            candidate_source="bounded_external_learning",
            metadata={"learning": {
                "why_learn": "Independent external evidence reveals a potentially relevant capability.",
                "learning_objective": f"Evaluate {name} without installation or production integration.",
                "required_evidence": ["two independent attributable sources"],
                "mastery_criteria": ["Governed disposition with source references and boundary."],
                "requires_miner": True,
            }},
        )
