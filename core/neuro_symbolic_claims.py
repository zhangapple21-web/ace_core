"""Evidence-linked symbolic claim checks for ACE task outputs.

This is a deterministic, read-only shadow over the existing TaskPool evidence.
It validates the *shape and provenance references* of model-proposed claims and
checks simple proposition conflicts / premise cycles. It cannot establish that a
source entails a claim, promote a claim to fact, authorize execution, or write to
any memory store. All model claims therefore remain unverified candidates.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections import defaultdict
from collections.abc import Mapping, Sequence
from typing import Any

CONTRACT_VERSION = "ace.neuro_symbolic_claims.v1"
EPISTEMIC_STATUSES = frozenset({"FACT", "INFERENCE", "HYPOTHESIS", "UNKNOWN"})
POLARITIES = frozenset({"SUPPORTS", "REFUTES", "UNKNOWN"})
CLAIM_FIELDS = frozenset({
    "claim_id",
    "subject",
    "predicate",
    "object",
    "polarity",
    "epistemic_status",
    "evidence_refs",
    "premise_ids",
    "falsifiable_if",
})
MAX_CLAIMS = 32
MAX_COMBINED_CLAIMS = MAX_CLAIMS * 2
MAX_EVIDENCE_REFS = 12
MAX_TEXT_LENGTH = 512
MAX_EVIDENCE_ITEMS = 512
MAX_EVIDENCE_TEXT_TOTAL = 32768
MAX_CLAIM_INPUT_CHARS = 131072
MAX_CLAIM_INPUT_ITEM_CHARS = 4096
MAX_REFERENCE_LENGTH = 1024


def audit_symbolic_claims(
    claims: Any,
    evidence_context: Sequence[Any] | None = None,
    *,
    max_claims: int = MAX_CLAIMS,
    namespace: str = "",
    external_premise_ids: Sequence[str] = (),
    side_effect_scope: str = "audit_function_only",
) -> dict[str, Any]:
    """Return a pure audit of typed claims against caller-supplied evidence.

    ``evidence_refs`` must exactly match a source id in ``evidence_context``.
    Matching a source establishes traceability only, never semantic support.
    Opposing polarities for the same normalized triple are kept together as
    ``NEEDS_REVIEW``; this function never selects a winner.
    """
    if claims is None:
        return _report("ABSENT", side_effect_scope=side_effect_scope)
    if not isinstance(claims, list):
        return _report(
            "INVALID",
            issues=[_issue(None, "CLAIMS_NOT_LIST", "symbolic_claims")],
            side_effect_scope=side_effect_scope,
        )
    if (
        not isinstance(max_claims, int) or isinstance(max_claims, bool)
        or max_claims < 1 or max_claims > MAX_COMBINED_CLAIMS
    ):
        return _report(
            "INVALID",
            claim_count=len(claims),
            issues=[_issue(None, "CLAIM_BUDGET_INVALID", "symbolic_claims")],
            side_effect_scope=side_effect_scope,
        )
    if len(claims) > max_claims:
        return _report(
            "INVALID",
            claim_count=len(claims),
            issues=[_issue(None, "CLAIM_BUDGET_EXCEEDED", "symbolic_claims")],
            side_effect_scope=side_effect_scope,
        )
    input_chars = 0
    if len(claims) > MAX_CLAIMS and max_claims == MAX_CLAIMS:
        return _report(
            "INVALID",
            claim_count=len(claims),
            issues=[_issue(None, "CLAIM_BUDGET_EXCEEDED", "symbolic_claims")],
            side_effect_scope=side_effect_scope,
        )
    for raw_claim in claims:
        if isinstance(raw_claim, Mapping):
            try:
                claim_items = list(raw_claim.items())
            except (TypeError, ValueError):
                return _report(
                    "INVALID",
                    claim_count=len(claims),
                    issues=[_issue(None, "CLAIM_INPUT_UNREADABLE", "symbolic_claims")],
                )
            for key, value in claim_items:
                try:
                    item_chars = len(str(key)) + len(str(value))
                except (TypeError, ValueError):
                    item_chars = MAX_CLAIM_INPUT_ITEM_CHARS + 1
                if item_chars > MAX_CLAIM_INPUT_ITEM_CHARS:
                    return _report(
                        "INVALID",
                        claim_count=len(claims),
                        issues=[_issue(None, "CLAIM_INPUT_ITEM_TOO_LARGE", "symbolic_claims")],
                    )
                input_chars += item_chars
                if input_chars > MAX_CLAIM_INPUT_CHARS:
                    return _report(
                        "INVALID",
                        claim_count=len(claims),
                        issues=[_issue(None, "CLAIM_INPUT_BUDGET_EXCEEDED", "symbolic_claims")],
                    )
        else:
            try:
                input_chars += len(str(raw_claim))
            except (TypeError, ValueError):
                input_chars = MAX_CLAIM_INPUT_CHARS + 1
            if input_chars > MAX_CLAIM_INPUT_CHARS:
                return _report(
                    "INVALID",
                    claim_count=len(claims),
                    issues=[_issue(None, "CLAIM_INPUT_BUDGET_EXCEEDED", "symbolic_claims")],
                )
    try:
        evidence_items = list(evidence_context or ())
    except TypeError:
        return _report(
            "INVALID",
            claim_count=len(claims),
            issues=[_issue(None, "EVIDENCE_CONTEXT_NOT_ITERABLE", "evidence_context")],
        )
    if len(evidence_items) > MAX_EVIDENCE_ITEMS:
        return _report(
            "INVALID",
            claim_count=len(claims),
            issues=[_issue(None, "EVIDENCE_CONTEXT_BUDGET_EXCEEDED", "evidence_context")],
        )
    for raw_claim in claims:
        if isinstance(raw_claim, Mapping):
            claim_id_value = raw_claim.get("claim_id")
            if isinstance(claim_id_value, str) and len(claim_id_value) > 64:
                return _report(
                    "INVALID",
                    claim_count=len(claims),
                    issues=[_issue(None, "CLAIM_ID_TOO_LONG", "claim_id")],
                )
            for unknown_field in set(raw_claim) - CLAIM_FIELDS:
                if len(str(unknown_field)) > 256:
                    return _report(
                        "INVALID",
                        claim_count=len(claims),
                        issues=[_issue(None,
                                       "UNKNOWN_FIELD_NAME_TOO_LONG", "symbolic_claims")],
                    )
            for text_field in ("subject", "predicate", "object", "falsifiable_if"):
                value = raw_claim.get(text_field)
                if isinstance(value, str) and len(value) > MAX_TEXT_LENGTH:
                    return _report(
                        "INVALID",
                        claim_count=len(claims),
                        issues=[_issue(_text(raw_claim.get("claim_id")) or None,
                                       "CLAIM_TEXT_BUDGET_EXCEEDED", text_field)],
                    )
            for list_field in ("evidence_refs", "premise_ids"):
                value = raw_claim.get(list_field)
                if isinstance(value, list) and len(value) > MAX_EVIDENCE_REFS:
                    return _report(
                        "INVALID",
                        claim_count=len(claims),
                        issues=[_issue(None, "REFERENCE_BUDGET_EXCEEDED", list_field)],
                    )
                if isinstance(value, list) and any(
                    not isinstance(item, str) or len(item) > MAX_REFERENCE_LENGTH
                    for item in value
                ):
                    return _report(
                        "INVALID",
                        claim_count=len(claims),
                        issues=[_issue(None, "REFERENCE_TOO_LONG_OR_INVALID", list_field)],
                    )
    if not claims:
        return _report("NO_CLAIMS")
    if (
        not isinstance(namespace, str) or len(namespace) > 24
        or (namespace and not re.fullmatch(r"[a-z][a-z0-9_-]*", namespace))
        or not isinstance(external_premise_ids, (list, tuple))
        or any(
            not isinstance(premise_id, str)
            or len(premise_id.strip()) > 64
            or not premise_id.strip()
            or ":" not in premise_id.strip()
            or not re.fullmatch(r"[a-z][a-z0-9_-]*", premise_id.strip().split(":", 1)[0])
            or premise_id.strip().split(":", 1)[0] == namespace
            or not premise_id.strip().split(":", 1)[1]
            for premise_id in external_premise_ids
        )
    ):
        return _report(
            "INVALID",
            claim_count=len(claims),
            issues=[_issue(None, "NAMESPACE_INVALID", "namespace")],
        )

    issues: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    try:
        catalog = _evidence_catalog(evidence_items)
    except (TypeError, ValueError):
        return _report(
            "INVALID",
            claim_count=len(claims),
            issues=[_issue(None, "EVIDENCE_CATALOG_AMBIGUOUS", "evidence_context")],
        )
    rows = claims
    # Role-scoped audits may accept premises from another producer only when the
    # caller supplies that producer's independently bound claim IDs. The combined
    # lifecycle audit has all rows locally and does not need an external inventory.
    external_premise_id_set = set(external_premise_ids)

    normalized: list[dict[str, Any]] = []
    id_occurrences: dict[str, int] = defaultdict(int)
    for raw in rows:
        if not isinstance(raw, Mapping):
            issues.append(_issue(None, "CLAIM_NOT_OBJECT", "symbolic_claims"))
            continue

        local_claim_id = _text(raw.get("claim_id"))
        claim_id = local_claim_id
        if claim_id and namespace and not claim_id.startswith(f"{namespace}:"):
            claim_id = _qualified_id(namespace, claim_id)
        if claim_id:
            id_occurrences[claim_id] += 1
        extras = sorted(str(key) for key in raw if key not in CLAIM_FIELDS)
        for field in extras:
            issues.append(_issue(claim_id or None, "UNKNOWN_CLAIM_FIELD", field))

        subject = _bounded_text(raw.get("subject"), claim_id, "subject", issues)
        predicate = _bounded_text(raw.get("predicate"), claim_id, "predicate", issues)
        obj = _bounded_text(raw.get("object"), claim_id, "object", issues)
        if not claim_id:
            issues.append(_issue(None, "CLAIM_ID_REQUIRED", "claim_id"))
        elif len(claim_id) > 64:
            issues.append(_issue(claim_id, "CLAIM_ID_TOO_LONG", "claim_id"))

        status = _text(raw.get("epistemic_status")).upper()
        if status not in EPISTEMIC_STATUSES:
            issues.append(_issue(claim_id or None, "EPISTEMIC_STATUS_INVALID", "epistemic_status"))
        polarity = _text(raw.get("polarity")).upper()
        if polarity not in POLARITIES:
            issues.append(_issue(claim_id or None, "POLARITY_INVALID", "polarity"))
        elif status == "UNKNOWN" and polarity != "UNKNOWN":
            issues.append(_issue(claim_id or None, "UNKNOWN_POLARITY_MISMATCH", "polarity"))
        elif status in {"FACT", "INFERENCE", "HYPOTHESIS"} and polarity == "UNKNOWN":
            issues.append(_issue(claim_id or None, "ASSERTED_CLAIM_POLARITY_UNKNOWN", "polarity"))

        evidence_refs = _string_list(
            raw.get("evidence_refs"), claim_id, "evidence_refs", issues, required=True
        )
        if len(evidence_refs) > MAX_EVIDENCE_REFS:
            issues.append(_issue(claim_id or None, "EVIDENCE_REFERENCE_BUDGET_EXCEEDED", "evidence_refs"))
        local_claim_ids = {
            _text(claim.get("claim_id"))
            for claim in claims if isinstance(claim, Mapping)
        }
        premise_ids = [
            (
                _qualified_id(namespace, premise)
                if namespace and isinstance(premise, str) and premise in local_claim_ids
                else premise
                if namespace and isinstance(premise, str) and premise in external_premise_id_set
                else f"{namespace}:{premise}"
                if namespace and isinstance(premise, str) and premise
                and not premise.startswith(f"{namespace}:")
                else premise
            )
            for premise in _string_list(
                raw.get("premise_ids", []), claim_id, "premise_ids", issues, required=False
            )
        ]
        falsifiable_if = raw.get("falsifiable_if", "")
        if falsifiable_if is None:
            falsifiable_if = ""
        if not isinstance(falsifiable_if, str):
            issues.append(_issue(claim_id or None, "FALSIFIER_NOT_TEXT", "falsifiable_if"))
            falsifiable_if = ""
        else:
            falsifiable_if = falsifiable_if.strip()
            if len(falsifiable_if) > MAX_TEXT_LENGTH:
                issues.append(_issue(claim_id or None, "FALSIFIER_TOO_LONG", "falsifiable_if"))
                falsifiable_if = falsifiable_if[:MAX_TEXT_LENGTH]

        if status == "FACT" and not evidence_refs:
            issues.append(_issue(claim_id or None, "FACT_WITHOUT_EVIDENCE", "evidence_refs"))
        if status == "INFERENCE" and not premise_ids:
            issues.append(_issue(claim_id or None, "INFERENCE_WITHOUT_PREMISE", "premise_ids"))
        if status == "HYPOTHESIS" and not falsifiable_if:
            issues.append(_issue(claim_id or None, "HYPOTHESIS_WITHOUT_FALSIFIER", "falsifiable_if"))
        if status == "UNKNOWN" and (evidence_refs or premise_ids):
            issues.append(_issue(claim_id or None, "UNKNOWN_MUST_NOT_ASSERT_SUPPORT", "epistemic_status"))

        ref_classes: dict[str, str] = {}
        for ref in evidence_refs:
            if ref not in catalog:
                issues.append(_issue(claim_id or None, "UNRESOLVED_EVIDENCE_REF", ref))
            else:
                ref_classes[ref] = catalog[ref]
        if status == "FACT" and evidence_refs and all(
            ref_classes.get(ref) in {"REUSE_POINTER", "ARCHIVE_POINTER", "PRIOR_KNOWLEDGE"}
            for ref in evidence_refs
        ):
            warnings.append(_issue(claim_id or None, "FACT_ONLY_CITES_PRIOR_KNOWLEDGE", "evidence_refs"))

        normalized.append({
            "claim_id": claim_id,
            "triple": {"subject": subject, "predicate": predicate, "object": obj},
            "polarity": polarity,
            "submitted_epistemic_status": status,
            "evidence_refs": evidence_refs,
            "evidence_ref_classes": ref_classes,
            "premise_ids": premise_ids,
            "falsifiable_if": falsifiable_if,
            "truth_status": "UNVERIFIED",
            "validation_status": "TRACEABLE_UNVERIFIED",
        })

    duplicate_ids = {claim_id for claim_id, count in id_occurrences.items() if count > 1}
    for claim_id in sorted(duplicate_ids):
        issues.append(_issue(claim_id, "DUPLICATE_CLAIM_ID", "claim_id"))

    unique_ids = {
        row["claim_id"]: row
        for row in normalized
        if row["claim_id"] and id_occurrences.get(row["claim_id"]) == 1
    }
    graph: dict[str, list[str]] = {}
    for claim_id, row in unique_ids.items():
        premises = row["premise_ids"]
        graph[claim_id] = []
        if row["submitted_epistemic_status"] == "INFERENCE" and not premises:
            issues.append(_issue(claim_id, "INFERENCE_WITHOUT_PREMISE", "premise_ids"))
        for premise_id in premises:
            if namespace and premise_id in external_premise_id_set:
                # The caller has supplied the independently bound external ID;
                # the owning role's audit performs its own premise validation.
                continue
            if premise_id not in id_occurrences:
                issues.append(_issue(claim_id, "UNRESOLVED_PREMISE_REF", premise_id))
            elif id_occurrences[premise_id] > 1:
                issues.append(_issue(claim_id, "AMBIGUOUS_PREMISE_REF", premise_id))
            elif premise_id not in unique_ids:
                issues.append(_issue(claim_id, "UNRESOLVED_PREMISE_REF", premise_id))
            else:
                graph[claim_id].append(premise_id)

    premise_order, cycle_ids = _topological_order(graph)
    invalid_premise_ids = _propagate_invalid_premises(graph, cycle_ids)
    premise_order = [claim_id for claim_id in premise_order if claim_id not in invalid_premise_ids]
    for claim_id in sorted(cycle_ids):
        issues.append(_issue(claim_id, "PREMISE_CYCLE", "premise_ids"))
    for claim_id in sorted(invalid_premise_ids - cycle_ids):
        issues.append(_issue(claim_id, "INVALID_PREMISE_DEPENDENCY", "premise_ids"))

    conflicts = _find_conflicts(normalized)
    conflict_ids = {
        claim_id
        for conflict in conflicts
        for claim_id in conflict["claim_ids"]
    }
    invalid_ids = {
        issue["claim_id"] for issue in issues if issue.get("claim_id")
    }
    global_issues = any(not issue.get("claim_id") for issue in issues)
    for row in normalized:
        claim_id = row["claim_id"]
        if claim_id in invalid_ids or global_issues:
            row["validation_status"] = "INVALID"
        elif claim_id in conflict_ids:
            row["validation_status"] = "NEEDS_REVIEW"

    if issues:
        status = "INVALID"
    elif conflicts:
        status = "NEEDS_REVIEW"
    else:
        status = "TRACEABLE_UNVERIFIED"
    return _report(
        status,
        claim_count=len(claims),
        claims=normalized,
        issues=issues,
        warnings=warnings,
        conflicts=conflicts,
        premise_order=premise_order,
        side_effect_scope=side_effect_scope,
    )


def claims_from_audit(audit: Any) -> list[dict[str, Any]]:
    """Project normalized audit rows back into the input claim schema."""
    if (
        not isinstance(audit, Mapping)
        or audit.get("status") not in {"TRACEABLE_UNVERIFIED", "NEEDS_REVIEW"}
        or not isinstance(audit.get("claims"), list)
    ):
        return []
    projected = []
    for row in audit["claims"]:
        if not isinstance(row, Mapping):
            continue
        triple = row.get("triple")
        triple = triple if isinstance(triple, Mapping) else {}
        projected.append({
            "claim_id": row.get("claim_id", ""),
            "subject": triple.get("subject", ""),
            "predicate": triple.get("predicate", ""),
            "object": triple.get("object", ""),
            "polarity": row.get("polarity", ""),
            "epistemic_status": row.get("submitted_epistemic_status", ""),
            "evidence_refs": list(row.get("evidence_refs", []))
            if isinstance(row.get("evidence_refs"), list) else [],
            "premise_ids": list(row.get("premise_ids", []))
            if isinstance(row.get("premise_ids"), list) else [],
            "falsifiable_if": row.get("falsifiable_if", ""),
        })
    return projected


def combine_symbolic_claim_sets(claim_sets: Mapping[str, Any]) -> list[Any]:
    """Combine role-scoped claims; resolve unqualified premises locally only."""
    combined: list[Any] = []
    namespaces = sorted(str(key) for key in claim_sets)
    qualified_prefixes = tuple(f"{namespace}:" for namespace in namespaces)
    for namespace in namespaces:
        claims = claim_sets.get(namespace)
        if claims is None:
            continue
        if not isinstance(claims, list):
            combined.append(claims)
            continue
        id_map: dict[str, str] = {}
        for claim in claims:
            if isinstance(claim, Mapping):
                claim_id = _text(claim.get("claim_id"))
                if claim_id:
                    id_map[claim_id] = (
                        claim_id if claim_id.startswith(f"{namespace}:")
                        else _qualified_id(namespace, claim_id)
                    )
        for claim in claims:
            if not isinstance(claim, Mapping):
                combined.append(claim)
                continue
            row = dict(claim)
            claim_id = _text(row.get("claim_id"))
            if claim_id:
                row["claim_id"] = id_map[claim_id]
            premises = row.get("premise_ids")
            if isinstance(premises, list):
                row["premise_ids"] = [
                    _qualify_premise(premise, namespace, id_map, qualified_prefixes)
                    for premise in premises
                ]
            combined.append(row)
    return combined


def _qualify_premise(
    premise: Any,
    namespace: str,
    local_ids: Mapping[str, str],
    qualified_prefixes: tuple[str, ...],
) -> Any:
    if not isinstance(premise, str):
        return premise
    value = _text(premise)
    if value in local_ids:
        return local_ids[value]
    if value.startswith(f"{namespace}:"):
        return value
    if not value.startswith(qualified_prefixes):
        return _qualified_id(namespace, value)
    return value


def _qualified_id(namespace: str, claim_id: str) -> str:
    qualified = f"{namespace}:{claim_id}"
    if len(qualified) <= 64:
        return qualified
    digest = hashlib.sha256(qualified.encode("utf-8")).hexdigest()[:12]
    return f"{namespace[:10]}:{claim_id[:40]}:{digest}"


def _evidence_catalog(evidence_context: Sequence[Any] | None) -> dict[str, str]:
    catalog: dict[str, str] = {}
    source_chars = 0
    for item in evidence_context or ():
        if isinstance(item, Mapping):
            source = _text(item.get("source") or item.get("source_ref"))
            kind = _text(item.get("kind") or item.get("type")).lower()
            content = _text(item.get("content") or item.get("detail"))
        else:
            source = _text(item)
            kind = ""
            content = ""
        if not source:
            continue
        source_chars += len(source)
        if len(source) > MAX_TEXT_LENGTH or source_chars > MAX_EVIDENCE_TEXT_TOTAL:
            raise ValueError("evidence source identifiers exceed bounded size")
        source_lower = source.lower()
        if source_lower.startswith("knowledge_join:"):
            source_class = "REUSE_POINTER"
        elif source_lower.startswith("archivist:") or content.startswith("## 任务ID: RQ-"):
            source_class = "ARCHIVE_POINTER"
        elif (
            kind in {"memory", "experience", "concept", "archived_knowledge"}
            or source_lower.startswith(("memory:", "experience:", "lexicon"))
        ):
            source_class = "PRIOR_KNOWLEDGE"
        else:
            source_class = "UNCLASSIFIED_SOURCE"
        # If one source appears in several shapes, retain the most conservative
        # classification rather than treating a reuse pointer as new evidence.
        rank = {
            "UNCLASSIFIED_SOURCE": 0,
            "PRIOR_KNOWLEDGE": 1,
            "ARCHIVE_POINTER": 2,
            "REUSE_POINTER": 3,
        }
        for existing_source in catalog:
            if _normalise_term(existing_source) == _normalise_term(source) and existing_source != source:
                raise ValueError("ambiguous normalized evidence source identifiers")
        previous = catalog.get(source)
        if previous is None or rank[source_class] > rank[previous]:
            catalog[source] = source_class
    return catalog


def _find_conflicts(claims: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], dict[str, set[str]]] = defaultdict(
        lambda: {"SUPPORTS": set(), "REFUTES": set()}
    )
    display: dict[tuple[str, str, str], dict[str, str]] = {}
    for claim in claims:
        triple = claim["triple"]
        subject = _normalise_term(triple["subject"])
        predicate = _normalise_term(triple["predicate"])
        obj = _normalise_term(triple["object"])
        if not subject or not predicate or not obj:
            continue
        key = (subject, predicate, obj)
        display[key] = triple
        if claim["polarity"] in {"SUPPORTS", "REFUTES"}:
            groups[key][claim["polarity"]].add(claim["claim_id"])
    result = []
    for key in sorted(groups):
        supports = groups[key]["SUPPORTS"]
        refutes = groups[key]["REFUTES"]
        if supports and refutes:
            result.append({
                "triple": display[key],
                "claim_ids": sorted(supports | refutes),
                "status": "NEEDS_REVIEW",
                "reason": "opposing_polarities_for_same_triple",
            })
    return result


def _propagate_invalid_premises(
    graph: Mapping[str, list[str]], invalid_ids: set[str]
) -> set[str]:
    affected = set(invalid_ids)
    changed = True
    while changed:
        changed = False
        for claim_id, premises in graph.items():
            if claim_id not in affected and any(premise in affected for premise in premises):
                affected.add(claim_id)
                changed = True
    return affected


def _topological_order(graph: Mapping[str, list[str]]) -> tuple[list[str], set[str]]:
    state: dict[str, int] = {}
    stack: list[str] = []
    order: list[str] = []
    cycles: set[str] = set()

    def visit(node: str) -> None:
        marker = state.get(node, 0)
        if marker == 2:
            return
        if marker == 1:
            try:
                start = stack.index(node)
            except ValueError:
                start = 0
            cycles.update(stack[start:])
            return
        state[node] = 1
        stack.append(node)
        for premise in sorted(graph.get(node, [])):
            visit(premise)
        stack.pop()
        state[node] = 2
        order.append(node)

    for node in graph:
        visit(node)
    return [node for node in order if node not in cycles], cycles


def _bounded_text(value: Any, claim_id: str | None, field: str,
                  issues: list[dict[str, Any]]) -> str:
    if not isinstance(value, str) or not value.strip():
        issues.append(_issue(claim_id, "CLAIM_TERM_REQUIRED", field))
        return ""
    result = value.strip()
    if len(result) > MAX_TEXT_LENGTH:
        issues.append(_issue(claim_id, "CLAIM_TERM_TOO_LONG", field))
        return result[:MAX_TEXT_LENGTH]
    return result


def _string_list(value: Any, claim_id: str | None, field: str,
                 issues: list[dict[str, Any]], *, required: bool) -> list[str]:
    if value is None and not required:
        return []
    if not isinstance(value, list):
        issues.append(_issue(claim_id, "REFERENCE_LIST_INVALID", field))
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str) or not item.strip():
            issues.append(_issue(claim_id, "REFERENCE_ITEM_INVALID", field))
            continue
        if len(item) > MAX_REFERENCE_LENGTH:
            issues.append(_issue(claim_id, "REFERENCE_TOO_LONG", field))
            continue
        reference = item.strip()
        if reference in seen:
            issues.append(_issue(claim_id, "DUPLICATE_REFERENCE", field))
            continue
        seen.add(reference)
        result.append(reference)
    return result


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _normalise_term(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def _issue(claim_id: str | None, code: str, field: str) -> dict[str, Any]:
    return {"claim_id": claim_id, "code": code, "field": field}


def _report(
    status: str,
    *,
    claim_count: int = 0,
    claims: list[dict[str, Any]] | None = None,
    issues: list[dict[str, Any]] | None = None,
    warnings: list[dict[str, Any]] | None = None,
    conflicts: list[dict[str, Any]] | None = None,
    premise_order: list[str] | None = None,
    side_effect_scope: str = "audit_function_only",
) -> dict[str, Any]:
    return {
        "contract_version": CONTRACT_VERSION,
        "side_effect_scope": side_effect_scope,
        "status": status,
        "claim_count": claim_count,
        "claims": claims or [],
        "issues": issues or [],
        "warnings": warnings or [],
        "conflicts": conflicts or [],
        "premise_order": premise_order or [],
        "truth_status": "UNVERIFIED",
        "execution_authorized": False,
        "promotion_authorized": False,
        "side_effects": {
            "scope": side_effect_scope,
            "persistent_write": False,
            "taskpool_mutation": False,
            "memory_mutation": False,
            "model_called": False,
            "execution_authorized": False,
            "promotion_authorized": False,
        },
    }
