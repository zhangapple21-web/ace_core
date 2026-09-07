"""A bounded ACE Reality -> Free Zone research hand-off.

ACE may offer a *real, evidence-complete gap* to the Free Zone as research
food.  This is not Admission and it is not TaskPool work: the Free Zone may
experiment, refuse, or retain an inconclusive result.  A later, separate
FreeZoneRealityBridge review is the only route back into ACE Reality.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


CONTRACT_VERSION = "ace.reality_free_zone_exchange.v1"
EPISTEMIC_STATES = frozenset({"FACT", "INFERENCE", "HYPOTHESIS", "UNKNOWN"})
REVIEW_FIELDS = frozenset({"decision", "reviewer", "review_basis"})
GAP_FIELDS = frozenset(
    {
        "gap_id",
        "epistemic_status",
        "observation",
        "reality_scope",
        "research_question",
        "expected_result",
        "verification_method",
        "constraints",
        "evidence_refs",
        "ace_review",
    }
)
EVIDENCE_FIELDS = frozenset({"ref", "independence_group", "kind"})


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _non_empty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


class RealityFreeZoneExchange:
    """Write an immutable reality-gap receipt and Free Zone inbox reference."""

    def __init__(
        self,
        workspace_root: str | Path,
        *,
        receipt_dir: str | Path | None = None,
        inbox_dir: str | Path | None = None,
    ) -> None:
        self.workspace_root = Path(workspace_root).resolve()
        self.receipt_dir = Path(
            receipt_dir or self.workspace_root / "08_GOVERNANCE" / "free_zone_exchange" / "receipts"
        ).resolve()
        self.inbox_dir = Path(
            inbox_dir or self.workspace_root / "07_SANDBOX" / "free_research" / "inbox"
        ).resolve()
        if not _within(self.receipt_dir, self.workspace_root):
            raise ValueError("receipt_dir must stay inside the workspace")
        if not _within(self.inbox_dir, self.workspace_root):
            raise ValueError("inbox_dir must stay inside the workspace")

    def release(self, gap: Mapping[str, Any]) -> dict[str, Any]:
        """Release one evidence-complete ACE gap as sandbox-only research food."""
        normalized, evidence, review = self._validate_gap(gap)
        identity = {
            "contract_version": CONTRACT_VERSION,
            "gap": normalized,
            "evidence": evidence,
            "ace_review": review,
        }
        exchange_id = f"EXCHANGE-{_digest(identity)[:24].upper()}"
        destination = self.receipt_dir / f"{exchange_id}.json"
        existing = self._read_existing(destination)
        if existing is not None:
            self._write_inbox(existing)
            return existing

        receipt = {
            "contract_version": CONTRACT_VERSION,
            "exchange_id": exchange_id,
            "created_at": _now(),
            "source_realm": "ACE_REALITY",
            "destination_realm": "FREE_ZONE",
            "gap": normalized,
            "evidence": evidence,
            "ace_review": review,
            "disposition": {
                "status": "RELEASED_TO_FREE_ZONE",
                "task_created": False,
                "model_call": False,
                "production_runtime_mutation": False,
                "admission_bypassed": False,
                "recommendation_authority": False,
                "semantics": "research food only; Free Zone may experiment, refuse, or remain inconclusive",
            },
        }
        receipt["receipt_hash"] = _digest(receipt)
        self._write_once(destination, receipt)
        persisted = self._read_existing(destination) or receipt
        self._write_inbox(persisted)
        return persisted

    def _validate_gap(self, gap: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        if not isinstance(gap, Mapping) or set(gap) != GAP_FIELDS:
            raise ValueError("gap has missing or unknown fields")
        for key in (
            "gap_id", "observation", "reality_scope", "research_question", "expected_result", "verification_method"
        ):
            if not _non_empty(gap.get(key)):
                raise ValueError(f"gap {key} must be non-empty")
        if gap.get("epistemic_status") not in EPISTEMIC_STATES:
            raise ValueError("invalid epistemic_status")
        constraints = gap.get("constraints")
        if not isinstance(constraints, list) or not constraints or any(not _non_empty(item) for item in constraints):
            raise ValueError("gap constraints must be non-empty strings")
        review = gap.get("ace_review")
        if not isinstance(review, Mapping) or set(review) != REVIEW_FIELDS:
            raise ValueError("ace_review has missing or unknown fields")
        if review.get("decision") != "RELEASE_TO_FREE_ZONE":
            raise ValueError("ace_review decision must release to Free Zone")
        if review.get("reviewer") not in {"main_steward", "ace_reality_runtime_relay"}:
            raise ValueError("authorized ACE Reality review required")
        basis = review.get("review_basis")
        if not isinstance(basis, list) or not basis or any(not _non_empty(item) for item in basis):
            raise ValueError("ace_review review_basis must be non-empty strings")
        refs = gap.get("evidence_refs")
        if not isinstance(refs, list) or not refs:
            raise ValueError("gap evidence_refs must be non-empty")
        evidence = self._validate_evidence(refs)
        if evidence["independent_count"] < 2:
            raise ValueError("independent evidence groups required")
        normalized = {key: json.loads(json.dumps(gap[key], ensure_ascii=False)) for key in GAP_FIELDS - {"evidence_refs", "ace_review"}}
        return normalized, evidence, json.loads(json.dumps(dict(review), ensure_ascii=False))

    def _validate_evidence(self, refs: list[dict[str, str]]) -> dict[str, Any]:
        items = []
        groups = set()
        for item in refs:
            if not isinstance(item, Mapping) or set(item) != EVIDENCE_FIELDS:
                raise ValueError("evidence ref has missing or unknown fields")
            if any(not _non_empty(item.get(key)) for key in EVIDENCE_FIELDS):
                raise ValueError("evidence ref fields must be non-empty")
            path = (self.workspace_root / str(item["ref"])).resolve()
            if not _within(path, self.workspace_root) or not path.is_file():
                raise ValueError("evidence ref must name an existing workspace file")
            group = str(item["independence_group"]).strip()
            groups.add(group)
            items.append({
                "ref": path.relative_to(self.workspace_root).as_posix(),
                "independence_group": group,
                "kind": str(item["kind"]).strip(),
                "sha256": _file_digest(path),
                "size_bytes": path.stat().st_size,
            })
        items.sort(key=lambda value: (value["independence_group"], value["ref"]))
        return {"refs": items, "independent_groups": sorted(groups), "independent_count": len(groups)}

    def _write_inbox(self, receipt: Mapping[str, Any]) -> None:
        destination = self.inbox_dir / f"{receipt['exchange_id']}.json"
        payload = {
            "food_kind": "ace_reality_gap",
            "origin": {"exchange_id": receipt["exchange_id"], "receipt_sha256": receipt["receipt_hash"]},
            "observation": receipt["gap"]["observation"],
            "hypothesis": receipt["gap"]["research_question"],
            "method": receipt["gap"]["verification_method"],
            "expected_result": receipt["gap"]["expected_result"],
            "constraints": receipt["gap"]["constraints"],
            "evidence": receipt["evidence"],
            "production_integration": False,
            "automatic_production_promotion": False,
            "automatic_task_creation": False,
        }
        self._write_once(destination, payload)

    @staticmethod
    def _read_existing(path: Path) -> dict[str, Any] | None:
        if not path.is_file():
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("existing exchange receipt is unreadable") from error
        if not isinstance(value, dict):
            raise ValueError("existing exchange receipt must be a JSON object")
        stored = value.get("receipt_hash")
        unsigned = dict(value)
        unsigned.pop("receipt_hash", None)
        if not _non_empty(stored) or _digest(unsigned) != stored:
            raise ValueError("existing exchange receipt hash mismatch")
        return value

    @staticmethod
    def _write_once(path: Path, value: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            return
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            pass
        finally:
            temporary.unlink(missing_ok=True)
