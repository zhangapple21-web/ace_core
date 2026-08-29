"""Durable five-factory relations for the ACE free-zone ecology.

R1's factories are not renamed roles.  They are a material flow:

    food -> recovered thread -> marks -> rival world blueprints
         -> isolated processing receipt -> (where applicable) courier receipt
         -> existing ruin smelter/distillation.

Every record in this module is sandbox-only, append-only, and intentionally
contains only a safe research shape.  It never stores inbox bodies, Git diffs,
credentials, remote README bodies, or production authority.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .free_zone_realm import state_for


CONTRACT_VERSION = "ace.free_zone_factories.v1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


class FreeZoneFactoryLine:
    """The five R1 factory relationships, re-instantiated inside one sandbox."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.factory_root = self.root / "factories"
        self.threads = self.factory_root / "threads"
        self.marks = self.factory_root / "marks"
        self.worlds = self.factory_root / "worlds"
        self.processing = self.factory_root / "processing"
        self.courier = self.factory_root / "courier"
        self.smelter = self.factory_root / "smelter"

    def initialize(self) -> None:
        for directory in (
            self.threads,
            self.marks,
            self.worlds,
            self.processing,
            self.courier,
            self.smelter,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def prepare(self, candidates: list[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
        """Recover, mark and imitate every discovered food item.

        Discovery is not selection.  Even a candidate that is not processed in
        this turn gets a durable thread and alternative blueprints, so a later
        ecology turn can return to it without rediscovering or overwriting it.
        """
        self.initialize()
        prepared: dict[str, dict[str, Any]] = {}
        for candidate in candidates:
            fingerprint = str(candidate.get("fingerprint", ""))
            if not fingerprint:
                continue
            thread = self._recover(candidate)
            mark = self._mark(thread, candidate)
            worlds = self._imitate(thread, candidate)
            prepared[fingerprint] = {"thread": thread, "mark": mark, "worlds": worlds}
        return prepared

    def process(
        self,
        *,
        candidate: Mapping[str, Any],
        prepared: Mapping[str, Any],
        experiment_id: str,
        outcome: str,
        record_hash: str,
        selected_stance: str = "DIRECT_OBSERVATION",
    ) -> dict[str, Any]:
        """Record which recovered thread became which isolated experiment."""
        thread = self._mapping(prepared.get("thread"))
        worlds = prepared.get("worlds") if isinstance(prepared.get("worlds"), list) else []
        direct_world = next(
            (item for item in worlds if isinstance(item, Mapping) and item.get("stance") == selected_stance),
            {},
        )
        receipt = {
            "contract_version": CONTRACT_VERSION,
            "receipt_id": f"PROCESS-{experiment_id}",
            "recorded_at": _now(),
            "factory": "processing",
            "thread_id": thread.get("thread_id"),
            "mark_id": self._mark_id(thread.get("thread_id", "")),
            "world_id": direct_world.get("world_id"),
            "selected_stance": selected_stance,
            "unexecuted_rival_world_ids": [
                item.get("world_id")
                for item in worlds
                # A counterexample turn deliberately executes the rival
                # world.  Define "unexecuted" relative to the selected
                # stance, not relative to the usual direct-observation
                # default, so the receipt never claims its own world was
                # left unexecuted.
                if isinstance(item, Mapping) and item.get("stance") != selected_stance
            ],
            "experiment_id": experiment_id,
            "outcome": outcome,
            "record_hash": record_hash,
            "production_integration": False,
            "realm_state": state_for("processing_receipt", source_kind=str(candidate.get("source_kind", "unknown"))),
            "receipt_hash": "",
        }
        receipt["receipt_hash"] = _digest({key: value for key, value in receipt.items() if key != "receipt_hash"})
        self._append(self.processing / f"{experiment_id}.json", receipt)
        if str(candidate.get("source_kind")) in {"external_catalog", "external_repository_file"}:
            self._courier(thread, candidate, experiment_id)
        return receipt

    def smelt(self, *, record: Mapping[str, Any], distillation: Mapping[str, Any]) -> dict[str, Any]:
        """Link the existing all-outcome smelter to a factory-thread lineage."""
        metadata = record.get("metadata") if isinstance(record.get("metadata"), Mapping) else {}
        experiment_id = str(record.get("experiment_id", ""))
        receipt = {
            "contract_version": CONTRACT_VERSION,
            "receipt_id": f"SMELT-{experiment_id}",
            "recorded_at": _now(),
            "factory": "ruin_smelter",
            "experiment_id": experiment_id,
            "thread_id": metadata.get("factory_thread_id"),
            "world_id": metadata.get("factory_world_id"),
            "outcome": record.get("outcome"),
            "distillation_status": distillation.get("status"),
            "source_record_hash": record.get("record_hash"),
            "distillation_hash": distillation.get("distillation_hash"),
            "production_integration": False,
            "realm_state": state_for("smelter_receipt", source_kind=str(metadata.get("source_kind", "unknown"))),
            "receipt_hash": "",
        }
        receipt["receipt_hash"] = _digest({key: value for key, value in receipt.items() if key != "receipt_hash"})
        self._append(self.smelter / f"{experiment_id}.json", receipt)
        return receipt

    def snapshot(self) -> dict[str, Any]:
        self.initialize()
        return {
            "contract_version": CONTRACT_VERSION,
            "recovery_thread_count": self._count(self.threads),
            "mark_count": self._count(self.marks),
            "world_count": self._count(self.worlds),
            "processing_receipt_count": self._count(self.processing),
            "courier_receipt_count": self._count(self.courier),
            "smelter_receipt_count": self._count(self.smelter),
            "production_integration": False,
        }

    def _recover(self, candidate: Mapping[str, Any]) -> dict[str, Any]:
        fingerprint = str(candidate["fingerprint"])
        thread_id = f"THREAD-{_digest(fingerprint)[:16].upper()}"
        record = {
            "contract_version": CONTRACT_VERSION,
            "thread_id": thread_id,
            "created_at": _now(),
            "factory": "recovery",
            "origin": {
                "fingerprint": fingerprint,
                "source_kind": str(candidate.get("source_kind", "unknown")),
                "source_ref": str(candidate.get("source_ref", "")),
                "parent_experiment_id": str(candidate.get("parent_experiment_id", "")) or None,
            },
            "research_shape": {
                "hypothesis": str(candidate.get("hypothesis", "")),
                "method": str(candidate.get("method", "")),
            },
            "content_retained": False,
            "realm_state": state_for("factory_thread", source_kind=str(candidate.get("source_kind", "unknown"))),
            "production_integration": False,
            "thread_hash": "",
        }
        record["thread_hash"] = _digest({key: value for key, value in record.items() if key != "thread_hash"})
        return self._append(self.threads / f"{thread_id}.json", record)

    def _mark(self, thread: Mapping[str, Any], candidate: Mapping[str, Any]) -> dict[str, Any]:
        thread_id = str(thread["thread_id"])
        source_kind = str(candidate.get("source_kind", "unknown"))
        labels = ["FREE_RESEARCH_ONLY", "PRODUCTION_FORBIDDEN", f"SOURCE:{source_kind.upper()}"]
        if source_kind in {"distillation", "museum_history"}:
            labels.append("HISTORICAL_OR_REOBSERVATION")
        if source_kind in {"external_catalog", "external_repository_file"}:
            labels.append("EXTERNAL_PUBLIC_OBSERVATION")
        if source_kind == "local_git":
            labels.append("LOCAL_PATH_REDACTED")
        record = {
            "contract_version": CONTRACT_VERSION,
            "mark_id": self._mark_id(thread_id),
            "recorded_at": _now(),
            "factory": "marking",
            "thread_id": thread_id,
            "labels": sorted(labels),
            "lineage_observable": True,
            "evidence_posture": "HYPOTHESIS_NOT_PRODUCTION_FACT",
            "production_integration": False,
            "realm_state": state_for("factory_mark", source_kind=source_kind),
            "mark_hash": "",
        }
        record["mark_hash"] = _digest({key: value for key, value in record.items() if key != "mark_hash"})
        return self._append(self.marks / f"{record['mark_id']}.json", record)

    def _imitate(self, thread: Mapping[str, Any], candidate: Mapping[str, Any]) -> list[dict[str, Any]]:
        """Create competing research blueprints without claiming either is true."""
        thread_id = str(thread["thread_id"])
        hypothesis = str(candidate.get("hypothesis", ""))
        method = str(candidate.get("method", ""))
        records = []
        for stance, question, world_method in (
            (
                "DIRECT_OBSERVATION",
                hypothesis,
                method,
            ),
            (
                "COUNTEREXAMPLE_SEARCH",
                f"What bounded observation would restrict or falsify the research shape of {thread_id}?",
                "Preserve this rival world for a dedicated counterexample executor; do not infer a result merely because it has not run.",
            ),
        ):
            world_id = f"WORLD-{thread_id}-{stance}"
            record = {
                "contract_version": CONTRACT_VERSION,
                "world_id": world_id,
                "recorded_at": _now(),
                "factory": "imitation",
                "thread_id": thread_id,
                "stance": stance,
                "question": question,
                "method": world_method,
                "execution_state": "BLUEPRINT_ONLY",
                "production_integration": False,
                "realm_state": state_for("world_blueprint", source_kind=str(candidate.get("source_kind", "unknown"))),
                "world_hash": "",
            }
            record["world_hash"] = _digest({key: value for key, value in record.items() if key != "world_hash"})
            records.append(self._append(self.worlds / f"{world_id}.json", record))
        return records

    def _courier(self, thread: Mapping[str, Any], candidate: Mapping[str, Any], experiment_id: str) -> dict[str, Any]:
        """Record the strictly one-way, public-only battlefield return path."""
        thread_id = str(thread["thread_id"])
        record = {
            "contract_version": CONTRACT_VERSION,
            "receipt_id": f"COURIER-{experiment_id}",
            "recorded_at": _now(),
            "factory": "courier",
            "direction": "PUBLIC_BATTLEFIELD_TO_FREE_ZONE",
            "thread_id": thread_id,
            "experiment_id": experiment_id,
            "source_kind": str(candidate.get("source_kind")),
            "source_ref": str(candidate.get("source_ref", "")),
            "payload_retained": False,
            "credentials_read": False,
            "production_integration": False,
            "realm_state": state_for("courier_receipt", source_kind=str(candidate.get("source_kind", "unknown"))),
            "receipt_hash": "",
        }
        record["receipt_hash"] = _digest({key: value for key, value in record.items() if key != "receipt_hash"})
        return self._append(self.courier / f"{record['receipt_id']}.json", record)

    @staticmethod
    def _mapping(value: Any) -> dict[str, Any]:
        return dict(value) if isinstance(value, Mapping) else {}

    @staticmethod
    def _mark_id(thread_id: str) -> str:
        return f"MARK-{thread_id}"

    @staticmethod
    def _count(directory: Path) -> int:
        return len(list(directory.glob("*.json"))) if directory.exists() else 0

    @staticmethod
    def _append(path: Path, record: Mapping[str, Any]) -> dict[str, Any]:
        """Append exactly once; a repeated deterministic factory step is idempotent."""
        value = dict(record)
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
                raise ValueError(f"factory record unreadable: {path}") from error
            if isinstance(existing, dict):
                return existing
            raise ValueError(f"factory record is not a mapping: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        encoded = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        return value
