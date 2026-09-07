"""Append-only, evidence-bound records for internal finance evaluation.

This journal is deliberately separate from live recommendations.  It neither
discovers symbols nor fetches prices; an upstream caller must provide complete
point-in-time evidence.  Daily Shift consumes summaries read-only.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable

from core.micro_observation import validate_micro_observation


class PaperEvaluationJournal:
    SCHEMA_VERSION = 1

    def __init__(self, data_dir: str):
        self.directory = Path(data_dir) / "paper_evaluations"
        self.path = self.directory / "journal.json"

    def _load(self) -> Dict[str, Any]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {"records": []}
        except (OSError, json.JSONDecodeError):
            return {"schema_version": self.SCHEMA_VERSION, "records": []}

    def _write(self, value: Dict[str, Any]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.path)

    @staticmethod
    def _non_empty(value: Any) -> bool:
        return value not in (None, "", [], {})

    @classmethod
    def _validate_record(cls, record: Dict[str, Any]) -> None:
        required = (
            "evaluation_id", "recorded_at", "observation_at", "symbol",
            "reference_price", "hypothesis", "invalidating_conditions",
            "data_snapshot_hash", "source_refs", "data_quality_state",
            "feature_version", "strategy_id", "strategy_version", "horizon_policy",
            "micro_observation",
        )
        if not isinstance(record, dict) or any(not cls._non_empty(record.get(key)) for key in required):
            raise ValueError("incomplete_evaluation_record")
        if record.get("mode") != "EVALUATION_ONLY" or record.get("publication_authority") is not False:
            raise ValueError("evaluation_only_boundary_required")
        if record.get("not_a_recommendation") is not True:
            raise ValueError("not_a_recommendation_required")
        if not isinstance(record["invalidating_conditions"], list) or not isinstance(record["source_refs"], list):
            raise ValueError("evaluation_evidence_collections_required")
        if not isinstance(record["horizon_policy"], dict) or not record["horizon_policy"].get("version"):
            raise ValueError("frozen_horizon_policy_required")
        validate_micro_observation(record["micro_observation"])
        try:
            if float(record["reference_price"]) <= 0:
                raise ValueError("reference_price_must_be_positive")
        except (TypeError, ValueError) as exc:
            raise ValueError("reference_price_must_be_positive") from exc

    def record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        self._validate_record(record)
        payload = self._load()
        records = payload.get("records") if isinstance(payload.get("records"), list) else []
        evaluation_id = str(record["evaluation_id"])
        if any(isinstance(item, dict) and item.get("evaluation_id") == evaluation_id for item in records):
            return {"status": "ALREADY_RECORDED", "evaluation_id": evaluation_id}
        entry = dict(record)
        entry["schema_version"] = self.SCHEMA_VERSION
        entry["outcomes"] = []
        entry["record_hash"] = hashlib.sha256(
            json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        records.append(entry)
        payload = {"schema_version": self.SCHEMA_VERSION, "records": records}
        self._write(payload)
        return {"status": "RECORDED", "evaluation_id": evaluation_id, "record_hash": entry["record_hash"]}

    def record_outcome(self, receipt: Dict[str, Any]) -> Dict[str, Any]:
        required = ("evaluation_id", "horizon", "observed_at", "result_snapshot_hash", "source_refs", "evaluation_rule_version")
        if not isinstance(receipt, dict) or any(not self._non_empty(receipt.get(key)) for key in required):
            raise ValueError("incomplete_outcome_receipt")
        if (
            not isinstance(receipt["source_refs"], list)
            or not receipt["source_refs"]
            or any(not isinstance(item, str) or not item.strip() for item in receipt["source_refs"])
            or not isinstance(receipt["result_snapshot_hash"], str)
            or not re.fullmatch(r"[0-9a-fA-F]{64}", receipt["result_snapshot_hash"])
        ):
            raise ValueError("outcome_evidence_malformed")
        payload = self._load()
        for record in payload.get("records", []):
            if not isinstance(record, dict) or record.get("evaluation_id") != receipt["evaluation_id"]:
                continue
            policy = record.get("horizon_policy", {})
            allowed = policy.get("horizons", []) if isinstance(policy, dict) else []
            normalized_allowed = {str(item) if str(item).startswith("D+") else f"D+{item}" for item in allowed}
            if str(receipt["horizon"]) not in normalized_allowed:
                raise ValueError("horizon_not_in_frozen_policy")
            outcomes = record.get("outcomes") if isinstance(record.get("outcomes"), list) else []
            if any(item.get("horizon") == receipt["horizon"] for item in outcomes if isinstance(item, dict)):
                return {"status": "OUTCOME_ALREADY_RECORDED", "evaluation_id": receipt["evaluation_id"]}
            outcome = dict(receipt)
            outcome["status"] = "OUTCOME_RECORDED"
            outcomes.append(outcome)
            record["outcomes"] = outcomes
            self._write(payload)
            return {"status": "OUTCOME_RECORDED", "evaluation_id": receipt["evaluation_id"]}
        raise ValueError("evaluation_record_not_found")

    def summary(self) -> Dict[str, Any]:
        records = [item for item in self._load().get("records", []) if isinstance(item, dict)]
        outcomes = [outcome for record in records for outcome in record.get("outcomes", []) if isinstance(outcome, dict) and outcome.get("status") == "OUTCOME_RECORDED"]
        return {
            "schema_version": self.SCHEMA_VERSION,
            "recorded_count": len(records),
            "outcome_receipt_count": len(outcomes),
            "postmortem_status": "READY_FOR_REVIEW" if outcomes else "NO_ELIGIBLE_PRIOR_RECORD",
            "publication_authority": False,
            "semantics": "read_only_summary; outcome_receipts_require_explicit_snapshot_evidence",
        }
