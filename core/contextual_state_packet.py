"""Evidence-bound contextual state for Free Zone research.

This module turns a small, explicitly supplied situation into a portable
packet.  It deliberately does *not* infer minds, fetch memory, call a model,
or attach to the ACE daemon.  Interpretations stay as competing hypotheses and
are retracted when their declared falsifying facts appear.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from typing import Any, Mapping


CONTRACT_VERSION = "ace.contextual_state_packet.v1"
RESEARCH_SCOPE = "FREE_ZONE_RESEARCH_ONLY"
FACT_FIELDS = frozenset({"fact_id", "statement", "observed_at", "entities", "scope", "evidence_refs"})
RELATION_FIELDS = frozenset({"relation_id", "subject", "object", "kind", "state", "evidence_refs"})
HYPOTHESIS_FIELDS = frozenset(
    {"hypothesis_id", "statement", "about_entities", "supported_by", "falsified_by", "status"}
)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def _texts(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a non-empty list")
    values = [_text(item, label) for item in value]
    if len(set(values)) != len(values):
        raise ValueError(f"{label} must not contain duplicates")
    return sorted(values)


class ContextualStatePacket:
    """Build deterministic, research-only packets from explicit situation data."""

    def build(self, scene: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(scene, Mapping):
            raise ValueError("scene must be a mapping")
        required = {"packet_id", "scope", "question", "entities", "facts", "relations", "hypotheses", "constraints"}
        if set(scene) != required:
            raise ValueError("scene has missing or unknown fields")

        packet_id = _text(scene["packet_id"], "packet_id")
        scene_scope = _text(scene["scope"], "scope")
        question = _text(scene["question"], "question")
        entities = _texts(scene["entities"], "entities")
        constraints = _texts(scene["constraints"], "constraints")
        facts = self._facts(scene["facts"], scene_scope, set(entities))
        relations = self._relations(scene["relations"], set(entities))
        hypotheses = self._hypotheses(scene["hypotheses"], set(entities), facts, relations)

        fact_ids = {item["fact_id"] for item in facts}
        active: list[dict[str, Any]] = []
        retracted: list[dict[str, Any]] = []
        for item in hypotheses:
            if set(item["falsified_by"]).intersection(fact_ids):
                retracted.append(
                    {
                        **item,
                        "epistemic_status": "HYPOTHESIS",
                        "retraction_reason": "falsifying_fact_present",
                        "falsified_by_present": sorted(set(item["falsified_by"]).intersection(fact_ids)),
                    }
                )
            elif item["status"] == "ACTIVE":
                active.append({**item, "epistemic_status": "HYPOTHESIS"})

        active.sort(key=lambda item: item["hypothesis_id"])
        retracted.sort(key=lambda item: item["hypothesis_id"])
        relevant_facts = [{**item, "epistemic_status": "FACT"} for item in facts]
        relevant_relations = [{**item, "epistemic_status": "FACT"} for item in relations]
        groups = self._competing_groups(active)
        packet = {
            "contract_version": CONTRACT_VERSION,
            "packet_id": packet_id,
            "scope": RESEARCH_SCOPE,
            "scene_scope": scene_scope,
            "question": question,
            "entities": entities,
            "constraints": constraints,
            "relevant_facts": relevant_facts,
            "relevant_relations": relevant_relations,
            "active_hypotheses": active,
            "retracted_hypotheses": retracted,
            "competing_hypothesis_groups": groups,
            "learning_needs": self._learning_needs(active, fact_ids),
            "production_integration": False,
            "side_effects": {
                "task_created": False,
                "model_called": False,
                "production_runtime_mutation": False,
            },
        }
        packet["packet_hash"] = _digest(packet)
        return packet

    def from_research_candidate(self, candidate: Mapping[str, Any]) -> dict[str, Any]:
        """Adapt one already-observed Free Zone candidate without inventing context.

        The adapter does not inspect the referenced file.  It only binds the
        provenance and the candidate's own hypothesis/method into an explicit
        question: what observation would change this tentative interpretation?
        """
        if not isinstance(candidate, Mapping):
            raise ValueError("candidate must be a mapping")
        fingerprint = _text(candidate.get("fingerprint"), "candidate fingerprint")
        source_kind = _text(candidate.get("source_kind"), "candidate source_kind")
        source_ref = _text(candidate.get("source_ref"), "candidate source_ref")
        hypothesis = _text(candidate.get("hypothesis"), "candidate hypothesis")
        method = _text(candidate.get("method"), "candidate method")
        source_identity = _digest({"source_kind": source_kind, "fingerprint": fingerprint})[:12].upper()
        source_entity = f"SOURCE_{source_identity}"
        identity = _digest({"fingerprint": fingerprint, "hypothesis": hypothesis})[:24].upper()
        return self.build(
            {
                "packet_id": f"CSP-{identity}",
                "scope": f"free_zone:{source_kind}",
                "question": method,
                "entities": ["FREE_ZONE", source_entity],
                "facts": [
                    {
                        "fact_id": "FACT-SOURCE-OBSERVED",
                        "statement": "A bounded Free Zone source was observed and selected for isolated research.",
                        "observed_at": "CANDIDATE_PROVENANCE",
                        "entities": ["FREE_ZONE", source_entity],
                        "scope": f"free_zone:{source_kind}",
                        "evidence_refs": [source_ref],
                    }
                ],
                "relations": [
                    {
                        "relation_id": "REL-FREE-ZONE-SOURCE",
                        "subject": "FREE_ZONE",
                        "object": source_entity,
                        "kind": "investigates",
                        "state": "ACTIVE",
                        "evidence_refs": [source_ref],
                    }
                ],
                "hypotheses": [
                    {
                        "hypothesis_id": "HYP-CANDIDATE-TRANSFER",
                        "statement": hypothesis,
                        "about_entities": ["FREE_ZONE", source_entity],
                        "supported_by": ["FACT-SOURCE-OBSERVED", "REL-FREE-ZONE-SOURCE"],
                        "falsified_by": ["FACT-INDEPENDENT-COUNTEREVIDENCE"],
                        "status": "ACTIVE",
                    },
                    {
                        "hypothesis_id": "HYP-EVIDENCE-INSUFFICIENT",
                        "statement": "The observed source alone is insufficient to settle the candidate interpretation.",
                        "about_entities": ["FREE_ZONE", source_entity],
                        "supported_by": ["FACT-SOURCE-OBSERVED"],
                        "falsified_by": ["FACT-INDEPENDENT-CONFIRMATION"],
                        "status": "ACTIVE",
                    },
                ],
                "constraints": [
                    "research only",
                    "do not treat hypotheses as facts",
                    "require an independent observation before a conclusion",
                ],
            }
        )

    @staticmethod
    def _facts(value: Any, scope: str, entities: set[str]) -> list[dict[str, Any]]:
        if not isinstance(value, list) or not value:
            raise ValueError("facts must be a non-empty list")
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for raw in value:
            if not isinstance(raw, Mapping) or set(raw) != FACT_FIELDS:
                raise ValueError("fact has missing or unknown fields")
            fact_id = _text(raw["fact_id"], "fact_id")
            if fact_id in seen:
                raise ValueError("fact_id must be unique")
            seen.add(fact_id)
            row = {
                "fact_id": fact_id,
                "statement": _text(raw["statement"], "fact statement"),
                "observed_at": _text(raw["observed_at"], "observed_at"),
                "entities": _texts(raw["entities"], "fact entities"),
                "scope": _text(raw["scope"], "fact scope"),
                "evidence_refs": _texts(raw["evidence_refs"], "fact evidence_refs"),
            }
            if row["scope"] != scope:
                raise ValueError("fact scope must match scene scope")
            if not set(row["entities"]).issubset(entities):
                raise ValueError("fact entities must be declared in scene")
            rows.append(row)
        return sorted(rows, key=lambda item: item["fact_id"])

    @staticmethod
    def _relations(value: Any, entities: set[str]) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            raise ValueError("relations must be a list")
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for raw in value:
            if not isinstance(raw, Mapping) or set(raw) != RELATION_FIELDS:
                raise ValueError("relation has missing or unknown fields")
            relation_id = _text(raw["relation_id"], "relation_id")
            if relation_id in seen:
                raise ValueError("relation_id must be unique")
            seen.add(relation_id)
            row = {
                "relation_id": relation_id,
                "subject": _text(raw["subject"], "relation subject"),
                "object": _text(raw["object"], "relation object"),
                "kind": _text(raw["kind"], "relation kind"),
                "state": _text(raw["state"], "relation state"),
                "evidence_refs": _texts(raw["evidence_refs"], "relation evidence_refs"),
            }
            if {row["subject"], row["object"]}.difference(entities):
                raise ValueError("relation entities must be declared in scene")
            rows.append(row)
        return sorted(rows, key=lambda item: item["relation_id"])

    @staticmethod
    def _hypotheses(value: Any, entities: set[str], facts: list[dict[str, Any]], relations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not isinstance(value, list) or not value:
            raise ValueError("hypotheses must be a non-empty list")
        known = {item["fact_id"] for item in facts}.union(item["relation_id"] for item in relations)
        fact_ids = {item["fact_id"] for item in facts}
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for raw in value:
            if not isinstance(raw, Mapping) or set(raw) != HYPOTHESIS_FIELDS:
                raise ValueError("hypothesis has missing or unknown fields")
            hypothesis_id = _text(raw["hypothesis_id"], "hypothesis_id")
            if hypothesis_id in seen:
                raise ValueError("hypothesis_id must be unique")
            seen.add(hypothesis_id)
            row = {
                "hypothesis_id": hypothesis_id,
                "statement": _text(raw["statement"], "hypothesis statement"),
                "about_entities": _texts(raw["about_entities"], "hypothesis about_entities"),
                "supported_by": _texts(raw["supported_by"], "hypothesis supported_by"),
                "falsified_by": _texts(raw["falsified_by"], "hypothesis falsified_by"),
                "status": _text(raw["status"], "hypothesis status"),
            }
            if row["status"] not in {"ACTIVE", "RETIRED"}:
                raise ValueError("hypothesis status must be ACTIVE or RETIRED")
            if not set(row["about_entities"]).issubset(entities):
                raise ValueError("hypothesis entities must be declared in scene")
            if set(row["supported_by"]).difference(known):
                raise ValueError("unknown support reference")
            # Falsifiers deliberately name future observable facts.  They may
            # be absent now (the normal case) and become active only when a
            # later packet contains the same FACT-* identity.  Keep the
            # namespace explicit so prose cannot masquerade as a fact id.
            if any(not reference.startswith("FACT-") for reference in row["falsified_by"]):
                raise ValueError("falsifying references must use FACT-* identities")
            rows.append(row)
        return sorted(rows, key=lambda item: item["hypothesis_id"])

    @staticmethod
    def _competing_groups(active: list[dict[str, Any]]) -> list[list[str]]:
        grouped: defaultdict[tuple[str, ...], list[str]] = defaultdict(list)
        for item in active:
            grouped[tuple(item["about_entities"])].append(item["hypothesis_id"])
        return sorted(sorted(ids) for ids in grouped.values() if len(ids) > 1)

    @staticmethod
    def _learning_needs(active: list[dict[str, Any]], present_fact_ids: set[str]) -> list[dict[str, Any]]:
        needs: dict[str, list[str]] = defaultdict(list)
        for hypothesis in active:
            for fact_id in hypothesis["falsified_by"]:
                if fact_id not in present_fact_ids:
                    needs[fact_id].append(hypothesis["hypothesis_id"])
        return [
            {
                "fact_id": fact_id,
                "status": "MISSING",
                "reason": "A future observable fact could falsify the named active hypothesis.",
                "required_by_hypotheses": sorted(hypothesis_ids),
            }
            for fact_id, hypothesis_ids in sorted(needs.items())
        ]
