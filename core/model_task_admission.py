from typing import Any, Dict, List


LOCAL_ARCHAEOLOGY_TAGS = {
    "archaeology",
    "fragment_archaeology",
    "local_archaeology",
}


class ModelTaskAdmission:
    def evaluate(self, candidate: Dict[str, Any]) -> Dict[str, Any]:
        source_type = str(candidate.get("source_type", ""))
        source_ref = str(candidate.get("source_ref", ""))
        evidence_refs = self._evidence_refs(candidate.get("evidence"))
        admission_basis = {
            "source_ref": source_ref,
            "source_type": source_type,
        }
        if self._is_local_only(candidate, source_type):
            return {
                "eligible": False,
                "classification": "local_evidence_only",
                "reasons": ["local_evidence_only"],
                "evidence_refs": evidence_refs,
                "admission_basis": admission_basis,
            }
        requested_type = str(candidate.get("task_type", "reasoning")).lower()
        classification, role_reasons = self._role_classification(
            requested_type,
            candidate.get("model_work_contract"),
            evidence_refs,
        )
        reasons = self._missing_reasons(candidate, evidence_refs) + role_reasons
        return {
            "eligible": not reasons,
            "classification": classification if not reasons else "local_evidence_only",
            "reasons": reasons,
            "evidence_refs": evidence_refs,
            "admission_basis": admission_basis,
        }

    @staticmethod
    def _role_classification(task_type: str, contract: Any, evidence_refs: List[str]):
        if task_type not in {"strategic", "execution"}:
            return "reasoning", []
        if not isinstance(contract, dict):
            return "reasoning", ["model_role_contract_required"]
        if task_type == "strategic":
            reasons = []
            if contract.get("value_level") != "L2_STRATEGIC":
                reasons.append("strategic_value_level_required")
            if len(evidence_refs) < 3:
                reasons.append("strategic_independent_evidence_required")
            alternatives = contract.get("alternatives")
            if not isinstance(alternatives, list) or len([x for x in alternatives if str(x).strip()]) < 2:
                reasons.append("strategic_alternatives_required")
            for field in ("impact_scope", "counter_evidence", "decision_verification"):
                if not isinstance(contract.get(field), str) or not contract[field].strip():
                    reasons.append(f"strategic_{field}_required")
            return "strategic", reasons
        reasons = []
        if contract.get("value_level") != "L3_EXECUTION":
            reasons.append("execution_value_level_required")
        if len(evidence_refs) < 3:
            reasons.append("execution_independent_evidence_required")
        for field in (
            "approved_parent_task_id",
            "authorization_scope",
            "rollback_plan",
            "execution_verification",
        ):
            if not isinstance(contract.get(field), str) or not contract[field].strip():
                reasons.append(f"execution_{field}_required")
        return "execution", reasons

    @staticmethod
    def _evidence_refs(evidence: Any) -> List[str]:
        if not isinstance(evidence, list):
            return []
        refs = []
        for item in evidence:
            if not isinstance(item, dict):
                continue
            source_ref = item.get("source_ref")
            if isinstance(source_ref, str) and source_ref and source_ref not in refs:
                refs.append(source_ref)
        return refs

    @staticmethod
    def _is_local_only(candidate: Dict[str, Any], source_type: str) -> bool:
        tags = candidate.get("tags", [])
        normalized_tags = {
            tag.lower() for tag in tags if isinstance(tag, str)
        }
        return (
            source_type == "archaeology"
            or candidate.get("local_evidence_only") is True
            or bool(normalized_tags & LOCAL_ARCHAEOLOGY_TAGS)
        )

    @staticmethod
    def _missing_reasons(candidate: Dict[str, Any], evidence_refs: List[str]) -> List[str]:
        reasons = []
        if len(evidence_refs) < 2:
            reasons.append("independent_evidence_required")
        for field in ("research_question", "expected_result", "verification_method"):
            if not isinstance(candidate.get(field), str) or not candidate[field].strip():
                reasons.append(f"{field}_required")
        return reasons
