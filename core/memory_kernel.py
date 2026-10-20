"""ACE 记忆内核（Governed Memory Kernel）。

这个模块把现有的结构化记忆、经验沉积和 Hindsight 风格检索收敛到一条
可恢复、可审计、可替换的治理链上。它不是另一套聊天记忆，也不授予
模型、窗口或检索器执行权。

设计边界：
* 候选、事实、经验和能力使用不同的生命周期；Candidate 不等于 Accepted。
* 任何记录都保留来源、证据、时间、数据分级和状态；UNKNOWN 不被填平。
* 冲突通过新事件和状态标记保留，不覆盖历史；遗忘只归档，不删除。
* JSONL 事件账本是可恢复的事实来源，快照只是加速读取的物化视图。
* 记忆查询是只读的；查询不会偷偷晋升、执行、改路由或把结果写成事实。
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import islice
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence

from .hindsight_memory_adapter import HindsightStyleRetriever
from .mirror_constitution import (
    DATA_CLASSES,
    contains_credential_like_content,
    validate_data_boundary,
)


CONTRACT_VERSION = "ace.memory_kernel.v1"
EVENT_VERSION = "ace.memory_kernel.event.v1"
MAX_IMPORT_BATCH_RECORDS = 50

MEMORY_TYPES = {
    "WORKING",
    "EPISODIC",
    "SEMANTIC",
    "PROCEDURAL",
    "OBSERVATION",
    "EXPERIENCE",
    "CAPABILITY_CANDIDATE",
    "CAPABILITY_ACCEPTED",
    "UNKNOWN",
}
EPISTEMIC_STATUSES = {
    "UNKNOWN",
    "CANDIDATE",
    "VERIFIED",
    "CONFLICTED",
    "SUPERSEDED",
    "ARCHIVED",
}
LIFECYCLE_STATES = {"ACTIVE", "COLD", "ARCHIVED", "SUPERSEDED"}
POLARITIES = {"SUPPORTED", "CONTRADICTED", "UNKNOWN"}
_KNOWN_EVENT_TYPES = {
    "CAPTURED",
    "SUPPORT_ADDED",
    "VERIFIED",
    "PROMOTED",
    "STATUS_CHANGED",
    "SUPERSEDED",
    "ARCHIVED",
    "IMPORT_BATCH_STARTED",
    "IMPORT_BATCH_COMPLETED",
    "IMPORT_BATCH_REJECTED",
}

_REF_RE = re.compile(r"^[^\x00\r\n]{1,4096}$")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _normalise_text(value: Any, *, limit: int = 20000) -> str:
    return str(value or "").strip()[:limit]


def _normalise_refs(values: Optional[Iterable[Any]]) -> list[str]:
    refs: list[str] = []
    for value in values or []:
        ref = str(value or "").strip()
        if ref and _REF_RE.match(ref) and ref not in refs:
            refs.append(ref)
    return refs


def _parse_time(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        text = str(value).strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _event_id() -> str:
    return "ME-" + uuid.uuid4().hex[:20].upper()


class MemoryIntegrityError(RuntimeError):
    """事件链损坏时 fail-closed，避免把不完整记忆当成连续记忆。"""


@dataclass(frozen=True)
class MemoryQuery:
    """跨窗口检索的显式边界；不把调用者的默认环境当作记忆范围。"""

    text: str
    bank: str = "ace"
    scope: Optional[str] = None
    data_classes: Optional[Sequence[str]] = None
    statuses: Optional[Sequence[str]] = None
    after: Optional[str] = None
    before: Optional[str] = None
    as_of: Optional[str] = None
    limit: int = 20


class MemoryKernel:
    """统一的、可恢复的 ACE 记忆治理内核。

    ``root`` 应位于 ACE 的治理记忆目录，例如 ``02_MEMORY/kernel``。
    调用方可用 ``capture`` 收纳候选，用 ``verify`` 收纳有独立收据的
    事实，用 ``promote_capability`` 接收闭环实验成果；没有这些显式动作，
    记录永远不会自动变成 Accepted。
    """

    def __init__(self, root: Path | str, *, bank: str = "ace"):
        self.root = Path(root)
        self.bank = str(bank or "ace").strip() or "ace"
        self.root.mkdir(parents=True, exist_ok=True)
        self.events_path = self.root / "events.jsonl"
        self.snapshot_path = self.root / "snapshot.json"
        self.receipts_dir = self.root / "receipts"
        self.receipts_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._records: dict[str, dict[str, Any]] = {}
        self._events: list[dict[str, Any]] = []
        self._last_event_hash = "GENESIS"
        self._integrity = {"valid": True, "errors": [], "events": 0}
        self._load()

    # ------------------------------------------------------------------
    # Durable event ledger and recovery
    # ------------------------------------------------------------------
    def _load(self) -> None:
        with self._lock:
            self._records = {}
            self._events = []
            self._last_event_hash = "GENESIS"
            errors: list[str] = []
            if self.events_path.exists():
                try:
                    lines = self.events_path.read_text(encoding="utf-8").splitlines()
                except OSError as exc:
                    raise MemoryIntegrityError(f"memory_events_unreadable:{exc}") from exc
                for line_no, line in enumerate(lines, start=1):
                    if not line.strip():
                        continue
                    try:
                        event = json.loads(line)
                    except json.JSONDecodeError as exc:
                        errors.append(f"event_json_invalid:{line_no}")
                        break
                    if not self._verify_event(event, self._last_event_hash):
                        errors.append(f"event_hash_invalid:{line_no}")
                        break
                    self._events.append(event)
                    self._last_event_hash = event["event_hash"]
                    self._apply_event(event)
            self._integrity = {
                "valid": not errors,
                "errors": errors,
                "events": len(self._events),
                "last_event_hash": self._last_event_hash,
            }
            if errors:
                raise MemoryIntegrityError(";".join(errors))
            self._write_snapshot()

    @staticmethod
    def _event_hash(event: Mapping[str, Any]) -> str:
        body = {key: value for key, value in event.items() if key != "event_hash"}
        return _sha(body)

    @classmethod
    def _verify_event(cls, event: Any, previous_hash: str) -> bool:
        if not isinstance(event, Mapping):
            return False
        required = {"event_version", "event_id", "event_type", "occurred_at", "previous_event_hash", "payload", "event_hash"}
        if not required.issubset(event):
            return False
        if event.get("event_version") != EVENT_VERSION:
            return False
        if event.get("event_type") not in _KNOWN_EVENT_TYPES:
            return False
        if event.get("previous_event_hash") != previous_hash:
            return False
        return event.get("event_hash") == cls._event_hash(event)

    def _append_event(self, event_type: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        event = {
            "event_version": EVENT_VERSION,
            "event_id": _event_id(),
            "event_type": str(event_type),
            "occurred_at": _utc_now(),
            "previous_event_hash": self._last_event_hash,
            "payload": dict(payload),
        }
        event["event_hash"] = self._event_hash(event)
        serialized = _canonical(event) + "\n"
        self.events_path.parent.mkdir(parents=True, exist_ok=True)
        with self.events_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        self._events.append(event)
        self._last_event_hash = event["event_hash"]
        self._apply_event(event)
        self._write_snapshot()
        return event

    def _write_snapshot(self) -> None:
        payload = {
            "contract_version": CONTRACT_VERSION,
            "bank": self.bank,
            "updated_at": _utc_now(),
            "last_event_hash": self._last_event_hash,
            "integrity": dict(self._integrity),
            "records": list(self._records.values()),
        }
        fd, tmp_name = tempfile.mkstemp(prefix="memory-snapshot-", suffix=".tmp", dir=str(self.root))
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, self.snapshot_path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    def _apply_event(self, event: Mapping[str, Any]) -> None:
        event_type = event.get("event_type")
        payload = event.get("payload") or {}
        memory_id = payload.get("memory_id")
        if event_type == "CAPTURED":
            record = dict(payload.get("record") or {})
            if record.get("id"):
                self._records[str(record["id"])] = record
        elif event_type == "SUPPORT_ADDED" and memory_id in self._records:
            record = self._records[memory_id]
            record["support_count"] = int(record.get("support_count", 0)) + 1
            for item in payload.get("evidence_refs") or []:
                if item not in record.setdefault("evidence_refs", []):
                    record["evidence_refs"].append(item)
            for item in payload.get("evidence_hashes") or []:
                if item not in record.setdefault("evidence_hashes", []):
                    record["evidence_hashes"].append(item)
            record["updated_at"] = event.get("occurred_at")
        elif event_type in {"VERIFIED", "PROMOTED", "STATUS_CHANGED"} and memory_id in self._records:
            record = self._records[memory_id]
            changes = dict(payload.get("changes") or {})
            record.update(changes)
            record["updated_at"] = event.get("occurred_at")
        elif event_type == "SUPERSEDED" and memory_id in self._records:
            record = self._records[memory_id]
            record.update(
                {
                    "epistemic_status": "SUPERSEDED",
                    "lifecycle_state": "SUPERSEDED",
                    "superseded_by": payload.get("replacement_id"),
                    "supersede_reason": payload.get("reason", ""),
                    "updated_at": event.get("occurred_at"),
                }
            )
        elif event_type == "ARCHIVED" and memory_id in self._records:
            record = self._records[memory_id]
            record.update(
                {
                    "epistemic_status": "ARCHIVED",
                    "lifecycle_state": "ARCHIVED",
                    "archive_reason": payload.get("reason", ""),
                    "updated_at": event.get("occurred_at"),
                }
            )

    # ------------------------------------------------------------------
    # Record validation and capture
    # ------------------------------------------------------------------
    @staticmethod
    def _validate_common(*, data_class: str, content: str, source_refs: Sequence[str], evidence_refs: Sequence[str], memory_type: str) -> None:
        if memory_type not in MEMORY_TYPES:
            raise ValueError(f"memory_type_invalid:{memory_type}")
        boundary = validate_data_boundary({"data_class": data_class}, target="INTERNAL", payload=content)
        if not boundary.get("valid"):
            raise ValueError("memory_data_boundary_invalid:" + ",".join(boundary.get("errors", [])))
        if contains_credential_like_content(content):
            raise ValueError("memory_credential_like_content_rejected")
        if memory_type != "WORKING" and not source_refs:
            raise ValueError("memory_source_refs_required")
        if any(not _REF_RE.match(ref) for ref in [*source_refs, *evidence_refs]):
            raise ValueError("memory_ref_invalid")

    def _make_record(
        self,
        *,
        content: str,
        title: str,
        memory_type: str,
        claim_key: str,
        data_class: str,
        source_refs: Sequence[str],
        evidence_refs: Sequence[str],
        scope: Optional[str],
        tags: Sequence[str],
        polarity: str,
        valid_from: Optional[str],
        valid_to: Optional[str],
        retention_until: Optional[str],
        metadata: Optional[Mapping[str, Any]],
    ) -> dict[str, Any]:
        content_hash = _sha(content)
        memory_id = "MEM-" + _sha(
            {
                "bank": self.bank,
                "claim_key": claim_key,
                "memory_type": memory_type,
                "content_hash": content_hash,
                "polarity": polarity,
            }
        )[:20].upper()
        now = _utc_now()
        status = "UNKNOWN" if not evidence_refs else "CANDIDATE"
        return {
            "id": memory_id,
            "contract_version": CONTRACT_VERSION,
            "bank": self.bank,
            "scope": str(scope or self.bank),
            "memory_type": memory_type,
            "claim_key": claim_key,
            "title": title,
            "content": content,
            "summary": content[:240],
            "content_sha256": content_hash,
            "data_class": data_class,
            "epistemic_status": status,
            "lifecycle_state": "ACTIVE",
            "polarity": polarity,
            "source_refs": list(source_refs),
            "evidence_refs": list(evidence_refs),
            "evidence_hashes": sorted({_sha(ref) for ref in evidence_refs}),
            "support_count": 1 if evidence_refs else 0,
            "created_at": now,
            "updated_at": now,
            "valid_from": valid_from or now,
            "valid_to": valid_to,
            "last_confirmed_at": None,
            "retention_until": retention_until,
            "confidence": 0.0,
            "retrieval_count": 0,
            "last_used_at": None,
            "supersedes": None,
            "superseded_by": None,
            "tags": sorted({str(tag).strip() for tag in tags if str(tag).strip()}),
            "metadata": dict(metadata or {}),
            "authority": {
                "execution_authorized": False,
                "production_integration": False,
                "promotion": False,
            },
        }

    def _active_for_claim(self, claim_key: str) -> list[dict[str, Any]]:
        return [
            record
            for record in self._records.values()
            if record.get("claim_key") == claim_key
            and record.get("lifecycle_state") not in {"ARCHIVED", "SUPERSEDED"}
        ]

    def capture(
        self,
        *,
        content: str,
        title: str = "",
        memory_type: str = "OBSERVATION",
        claim_key: Optional[str] = None,
        data_class: str = "PRIVATE",
        source_refs: Optional[Iterable[Any]] = None,
        evidence_refs: Optional[Iterable[Any]] = None,
        scope: Optional[str] = None,
        tags: Optional[Iterable[Any]] = None,
        polarity: str = "SUPPORTED",
        valid_from: Optional[str] = None,
        valid_to: Optional[str] = None,
        retention_until: Optional[str] = None,
        metadata: Optional[Mapping[str, Any]] = None,
    ) -> dict[str, Any]:
        """收纳一个候选记忆；缺证据时明确保持 UNKNOWN。"""

        content = _normalise_text(content)
        title = _normalise_text(title, limit=500)
        memory_type = str(memory_type or "UNKNOWN").strip().upper()
        data_class = str(data_class or "").strip().upper()
        polarity = str(polarity or "UNKNOWN").strip().upper()
        if not content:
            raise ValueError("memory_content_required")
        if data_class not in DATA_CLASSES:
            raise ValueError("memory_data_class_invalid")
        if polarity not in POLARITIES:
            raise ValueError("memory_polarity_invalid")
        source_list = _normalise_refs(source_refs)
        evidence_list = _normalise_refs(evidence_refs)
        tag_list = [str(tag).strip() for tag in (tags or []) if str(tag).strip()]
        metadata_map = dict(metadata or {})
        if contains_credential_like_content(
            {
                "title": title,
                "tags": tag_list,
                "metadata": metadata_map,
                "source_refs": source_list,
                "evidence_refs": evidence_list,
            }
        ):
            raise ValueError("memory_credential_like_content_rejected")
        try:
            json.dumps(metadata_map, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError) as exc:
            raise ValueError("memory_metadata_not_json_serializable") from exc
        key = _normalise_text(claim_key or title or content[:160], limit=500)
        self._validate_common(
            data_class=data_class,
            content=content,
            source_refs=source_list,
            evidence_refs=evidence_list,
            memory_type=memory_type,
        )
        with self._lock:
            record = self._make_record(
                content=content,
                title=title,
                memory_type=memory_type,
                claim_key=key,
                data_class=data_class,
                source_refs=source_list,
                evidence_refs=evidence_list,
                scope=scope,
                tags=tag_list,
                polarity=polarity,
                valid_from=valid_from,
                valid_to=valid_to,
                retention_until=retention_until,
                metadata=metadata_map,
            )
            existing = self._records.get(record["id"])
            if existing:
                if evidence_list:
                    new_evidence = [ref for ref in evidence_list if ref not in existing.get("evidence_refs", [])]
                    if new_evidence:
                        self._append_event(
                            "SUPPORT_ADDED",
                            {
                                "memory_id": record["id"],
                                "evidence_refs": new_evidence,
                                "evidence_hashes": [_sha(ref) for ref in new_evidence],
                            },
                        )
                return dict(self._records[record["id"]])

            conflicts = [
                item
                for item in self._active_for_claim(key)
                if item.get("polarity") in {"SUPPORTED", "CONTRADICTED"}
                and polarity in {"SUPPORTED", "CONTRADICTED"}
                and item.get("polarity") != polarity
            ]
            if conflicts:
                record["epistemic_status"] = "CONFLICTED"
                for prior in conflicts:
                    self._append_event(
                        "STATUS_CHANGED",
                        {
                            "memory_id": prior["id"],
                            "changes": {
                                "epistemic_status": "CONFLICTED",
                                "conflict_group": key,
                            },
                        },
                    )
                record["conflict_group"] = key
            self._append_event("CAPTURED", {"memory_id": record["id"], "record": record})
            return dict(self._records[record["id"]])

    def import_records(
        self,
        records: Iterable[Mapping[str, Any]],
        *,
        selected_by: str,
        source_prefix: str = "import",
    ) -> dict[str, Any]:
        """显式、限量地迁移候选，并在同一哈希链中记录批次收据。

        ``selected_by`` 是调用方声明的选择责任标识；当前系统没有独立身份
        认证，因此收据不会把这个字段伪称为已认证的真人身份。
        """

        actor = str(selected_by or "").strip()
        if not actor or len(actor) > 120 or contains_credential_like_content(actor):
            raise ValueError("memory_import_selected_by_invalid")
        prefix = _normalise_text(source_prefix or "import", limit=160)
        batch_id = "MB-" + uuid.uuid4().hex.upper()
        batch = list(islice(iter(records), MAX_IMPORT_BATCH_RECORDS + 1))
        selected_hashes = []
        for index, raw in enumerate(batch):
            try:
                fingerprint_input = dict(raw) if isinstance(raw, Mapping) else {"index": index, "type": type(raw).__name__}
                selected_hashes.append(_sha(fingerprint_input))
            except (TypeError, ValueError):
                selected_hashes.append(_sha({"index": index, "type": type(raw).__name__, "serialization_error": True}))
        batch_fingerprint = _sha({"source_prefix": prefix, "record_hashes": selected_hashes})

        if len(batch) > MAX_IMPORT_BATCH_RECORDS:
            rejected_event = self._append_event(
                "IMPORT_BATCH_REJECTED",
                {
                    "batch_id": batch_id,
                    "selected_by": actor,
                    "source_prefix": prefix,
                    "reason": "record_limit_exceeded",
                    "limit": MAX_IMPORT_BATCH_RECORDS,
                    "observed_count_at_least": len(batch),
                    "sampled_record_hashes": selected_hashes,
                    "batch_fingerprint": batch_fingerprint,
                    "records_written": 0,
                },
            )
            raise ValueError(
                f"memory_import_batch_limit_exceeded:{MAX_IMPORT_BATCH_RECORDS}:{batch_id}:{rejected_event['event_hash']}"
            )

        started_event = self._append_event(
            "IMPORT_BATCH_STARTED",
            {
                "batch_id": batch_id,
                "selected_by": actor,
                "source_prefix": prefix,
                "selected_count": len(batch),
                "selected_record_hashes": selected_hashes,
                "batch_fingerprint": batch_fingerprint,
                "selection_identity_authenticated": False,
            },
        )

        imported: list[str] = []
        rejected: list[dict[str, Any]] = []
        for raw in batch:
            if not isinstance(raw, Mapping):
                rejected.append({"reason": "record_not_mapping"})
                continue
            try:
                related_event_id = str(raw.get("related_event_id") or "").strip()
                if related_event_id:
                    claim_key = related_event_id
                else:
                    # A legacy title is not a stable event/claim identity:
                    # repeated titles can describe distinct times and sources.
                    # Keep each imported row independently auditable until a
                    # governed consolidation step explicitly relates them.
                    claim_key = "legacy-import:" + _sha(
                        {
                            "source_prefix": prefix,
                            "source_id": str(raw.get("id") or ""),
                            "record": dict(raw),
                        }
                    )[:32]
                source_path = str(raw.get("source_path") or "").strip()
                source_refs = raw.get("source_refs") or []
                evidence_refs = raw.get("evidence_refs") or []
                if isinstance(source_refs, str):
                    source_refs = [source_refs]
                if isinstance(evidence_refs, str):
                    evidence_refs = [evidence_refs]
                if not source_refs and source_path:
                    source_refs = [source_path]
                if not evidence_refs and source_path:
                    evidence_refs = [source_path]
                record = self.capture(
                    content=str(raw.get("content") or raw.get("summary") or "").strip(),
                    title=str(raw.get("title") or ""),
                    memory_type={
                        "note": "SEMANTIC",
                        "project": "EPISODIC",
                        "feedback": "EXPERIENCE",
                        "reference": "SEMANTIC",
                    }.get(str(raw.get("type") or "").lower(), "UNKNOWN"),
                    claim_key=claim_key,
                    data_class=str(raw.get("data_class") or "PRIVATE").upper(),
                    source_refs=source_refs or [f"{prefix}:{raw.get('id', 'unknown')}"],
                    evidence_refs=evidence_refs,
                    tags=raw.get("tags") or [],
                    polarity=str(raw.get("polarity") or "UNKNOWN").upper(),
                    metadata={
                        "imported_from": {
                            "id": str(raw.get("id") or ""),
                            "type": str(raw.get("type") or ""),
                            "created_at": str(raw.get("created_at") or ""),
                            "updated_at": str(raw.get("updated_at") or ""),
                        }
                    },
                )
                imported.append(record["id"])
            except (TypeError, ValueError) as exc:
                rejected.append({"id": raw.get("id"), "reason": str(exc)})

        completed_event = self._append_event(
            "IMPORT_BATCH_COMPLETED",
            {
                "batch_id": batch_id,
                "started_event_hash": started_event["event_hash"],
                "selected_count": len(batch),
                "imported_count": len(imported),
                "rejected_count": len(rejected),
                "imported_memory_ids": imported,
                "rejection_reasons": dict(Counter(str(item.get("reason") or "unknown") for item in rejected)),
                "result": "PASS" if not rejected else "PARTIAL",
                "promotion_status": "CANDIDATE_ONLY",
                "execution_authorized": False,
                "production_integration": False,
            },
        )
        batch_receipt = {
            "batch_id": batch_id,
            "status": "COMPLETED",
            "selected_by": actor,
            "selection_identity_authenticated": False,
            "source_prefix": prefix,
            "selected_count": len(batch),
            "selected_record_hashes": selected_hashes,
            "batch_fingerprint": batch_fingerprint,
            "imported_count": len(imported),
            "rejected_count": len(rejected),
            "result": "PASS" if not rejected else "PARTIAL",
            "started_at": started_event["occurred_at"],
            "completed_at": completed_event["occurred_at"],
            "started_event_hash": started_event["event_hash"],
            "completed_event_hash": completed_event["event_hash"],
        }
        return {
            "contract_version": CONTRACT_VERSION,
            "imported": imported,
            "rejected": rejected,
            "batch_receipt": batch_receipt,
            "promotion_status": "CANDIDATE_ONLY",
            "execution_authorized": False,
            "production_integration": False,
        }

    def list_import_batches(self) -> list[dict[str, Any]]:
        """从可校验的事件链重建批次状态；无完成事件的批次显示为 INCOMPLETE。"""

        batches: dict[str, dict[str, Any]] = {}
        for event in self._events:
            event_type = str(event.get("event_type") or "")
            payload = event.get("payload") or {}
            batch_id = str(payload.get("batch_id") or "")
            if not batch_id:
                continue
            if event_type == "IMPORT_BATCH_STARTED":
                batches[batch_id] = {
                    **dict(payload),
                    "status": "INCOMPLETE",
                    "started_event_hash": event.get("event_hash"),
                    "started_at": event.get("occurred_at"),
                }
            elif event_type == "IMPORT_BATCH_COMPLETED" and batch_id in batches:
                batches[batch_id].update(
                    {
                        **dict(payload),
                        "status": "COMPLETED",
                        "completed_event_hash": event.get("event_hash"),
                        "completed_at": event.get("occurred_at"),
                    }
                )
            elif event_type == "IMPORT_BATCH_REJECTED":
                batches[batch_id] = {
                    **dict(payload),
                    "status": "REJECTED",
                    "completed_event_hash": event.get("event_hash"),
                    "completed_at": event.get("occurred_at"),
                }
        return list(batches.values())

    # ------------------------------------------------------------------
    # Explicit verification, promotion and lifecycle changes
    # ------------------------------------------------------------------
    @staticmethod
    def _verification_ok(receipt: Mapping[str, Any]) -> bool:
        required = ("receipt_id", "source_refs", "result", "reviewer")
        if not all(str(receipt.get(field) or "").strip() for field in required):
            return False
        refs = receipt.get("source_refs")
        return isinstance(refs, (list, tuple)) and bool(_normalise_refs(refs)) and str(receipt.get("result")).upper() in {"PASS", "VERIFIED"}

    def verify(self, memory_id: str, verification_receipt: Mapping[str, Any]) -> dict[str, Any]:
        """只接受可回读的独立验证收据；不接受模型的自我声明。"""

        if not isinstance(verification_receipt, Mapping) or not self._verification_ok(verification_receipt):
            raise ValueError("memory_verification_receipt_incomplete")
        with self._lock:
            record = self._records.get(str(memory_id))
            if not record:
                raise KeyError(f"memory_not_found:{memory_id}")
            if record.get("epistemic_status") in {"CONFLICTED", "SUPERSEDED", "ARCHIVED"}:
                raise ValueError("memory_not_verifiable_in_current_state")
            evidence_refs = _normalise_refs(verification_receipt.get("source_refs"))
            changes = {
                "epistemic_status": "VERIFIED",
                "last_confirmed_at": _utc_now(),
                "confidence": min(1.0, max(float(record.get("confidence", 0.0)), 0.75)),
                "verification_receipt": {
                    "receipt_id": str(verification_receipt["receipt_id"]),
                    "source_refs": evidence_refs,
                    "result": str(verification_receipt["result"]).upper(),
                    "reviewer": str(verification_receipt["reviewer"]),
                    "verified_at": str(verification_receipt.get("verified_at") or _utc_now()),
                },
            }
            self._append_event("VERIFIED", {"memory_id": str(memory_id), "changes": changes})
            return dict(self._records[str(memory_id)])

    def promote_capability(self, memory_id: str, evolution_receipt: Mapping[str, Any]) -> dict[str, Any]:
        """把能力候选接入经验晋升门；没有闭环证据就拒绝。"""

        required = {
            "decision",
            "baseline",
            "change",
            "test",
            "evaluation",
            "compare",
            "painful_review",
            "independent_evidence_groups",
        }
        if not isinstance(evolution_receipt, Mapping) or not required.issubset(evolution_receipt):
            raise ValueError("capability_promotion_receipt_incomplete")
        if str(evolution_receipt.get("decision", "")).upper() != "PROMOTE":
            raise ValueError("capability_promotion_decision_not_promote")
        evidence_groups = evolution_receipt.get("independent_evidence_groups")
        if not isinstance(evidence_groups, (list, tuple)) or len(evidence_groups) < 2:
            raise ValueError("capability_independent_evidence_groups_incomplete")
        review = evolution_receipt.get("painful_review")
        if not isinstance(review, Mapping) or not all(str(review.get(k) or "").strip() for k in ("cost", "impact", "counterfactual", "recurrence_risk", "lesson", "reuse_conditions")):
            raise ValueError("capability_painful_review_incomplete")
        with self._lock:
            record = self._records.get(str(memory_id))
            if not record:
                raise KeyError(f"memory_not_found:{memory_id}")
            if record.get("memory_type") != "CAPABILITY_CANDIDATE":
                raise ValueError("memory_is_not_capability_candidate")
            if record.get("epistemic_status") != "VERIFIED":
                raise ValueError("capability_requires_verified_memory")
            changes = {
                "memory_type": "CAPABILITY_ACCEPTED",
                "epistemic_status": "VERIFIED",
                "confidence": 1.0,
                "promotion_receipt": {
                    "decision": "PROMOTE",
                    "baseline": dict(evolution_receipt["baseline"]) if isinstance(evolution_receipt["baseline"], Mapping) else evolution_receipt["baseline"],
                    "change": dict(evolution_receipt["change"]) if isinstance(evolution_receipt["change"], Mapping) else evolution_receipt["change"],
                    "test": dict(evolution_receipt["test"]) if isinstance(evolution_receipt["test"], Mapping) else evolution_receipt["test"],
                    "evaluation": dict(evolution_receipt["evaluation"]) if isinstance(evolution_receipt["evaluation"], Mapping) else evolution_receipt["evaluation"],
                    "compare": dict(evolution_receipt["compare"]) if isinstance(evolution_receipt["compare"], Mapping) else evolution_receipt["compare"],
                    "independent_evidence_groups": [
                        list(group) if isinstance(group, (list, tuple)) else group
                        for group in evidence_groups
                    ],
                    "painful_review": dict(review),
                },
            }
            self._append_event("PROMOTED", {"memory_id": str(memory_id), "changes": changes})
            return dict(self._records[str(memory_id)])

    def supersede(self, memory_id: str, replacement_id: str, *, reason: str) -> dict[str, Any]:
        if not str(reason or "").strip():
            raise ValueError("supersede_reason_required")
        with self._lock:
            if memory_id not in self._records or replacement_id not in self._records:
                raise KeyError("memory_supersede_target_missing")
            self._append_event(
                "SUPERSEDED",
                {"memory_id": str(memory_id), "replacement_id": str(replacement_id), "reason": str(reason).strip()},
            )
            return dict(self._records[str(memory_id)])

    def archive(self, memory_id: str, *, reason: str) -> dict[str, Any]:
        if not str(reason or "").strip():
            raise ValueError("archive_reason_required")
        with self._lock:
            if memory_id not in self._records:
                raise KeyError(f"memory_not_found:{memory_id}")
            self._append_event("ARCHIVED", {"memory_id": str(memory_id), "reason": str(reason).strip()})
            return dict(self._records[str(memory_id)])

    # ------------------------------------------------------------------
    # Read-only retrieval and recovery projections
    # ------------------------------------------------------------------
    def _query_records(self, query: MemoryQuery) -> list[dict[str, Any]]:
        classes = {str(item).upper() for item in (query.data_classes or DATA_CLASSES)}
        statuses = {str(item).upper() for item in (query.statuses or EPISTEMIC_STATUSES)}
        invalid_classes = classes - DATA_CLASSES
        invalid_statuses = statuses - EPISTEMIC_STATUSES
        if invalid_classes:
            raise ValueError("memory_query_data_class_invalid:" + ",".join(sorted(invalid_classes)))
        if invalid_statuses:
            raise ValueError("memory_query_status_invalid:" + ",".join(sorted(invalid_statuses)))
        after = _parse_time(query.after)
        before = _parse_time(query.before)
        as_of = _parse_time(query.as_of)
        selected = []
        for record in self._records.values():
            if record.get("bank") != query.bank:
                continue
            if query.scope and record.get("scope") != query.scope:
                continue
            if record.get("data_class") not in classes:
                continue
            if record.get("epistemic_status") not in statuses:
                continue
            created = _parse_time(record.get("created_at"))
            if after and (not created or created <= after):
                continue
            if before and (not created or created >= before):
                continue
            if as_of:
                valid_from = _parse_time(record.get("valid_from"))
                valid_to = _parse_time(record.get("valid_to"))
                if valid_from and valid_from > as_of:
                    continue
                if valid_to and valid_to < as_of:
                    continue
            selected.append(dict(record))
        return selected

    def query(
        self,
        text: str,
        *,
        scope: Optional[str] = None,
        data_classes: Optional[Sequence[str]] = None,
        statuses: Optional[Sequence[str]] = None,
        after: Optional[str] = None,
        before: Optional[str] = None,
        as_of: Optional[str] = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """多路检索的只读入口；不自动 touch、晋升或写回未来行为。"""

        with self._lock:
            query = MemoryQuery(
                text=str(text or "").strip(),
                bank=self.bank,
                scope=scope,
                data_classes=data_classes,
                statuses=statuses,
                after=after,
                before=before,
                as_of=as_of,
                limit=max(1, min(int(limit), 100)),
            )
            candidates = self._query_records(query)
            result = HindsightStyleRetriever(candidates).retrieve(
                query.text,
                limit=query.limit,
                after=query.after,
                before=query.before,
            )
            result.update(
                {
                    "contract_version": CONTRACT_VERSION,
                    "retrieval_mode": "GOVERNED_MULTI_STRATEGY_READ_ONLY",
                    "bank": self.bank,
                    "scope": scope,
                    "as_of": as_of,
                    "candidate_count": len(candidates),
                    "execution_authorized": False,
                    "production_integration": False,
                    "promotion": False,
                    "source_of_truth": "ACE_MEMORY_KERNEL_EVENT_LEDGER",
                    "retrieval_receipt": {
                        "receipt_id": "RET-" + _sha(
                            {
                                "bank": self.bank,
                                "scope": scope,
                                "query": query.text,
                                "result_ids": [item.get("memory_id") for item in result.get("results", [])],
                                "integrity": self._last_event_hash,
                            }
                        )[:20].upper(),
                        "query_sha256": _sha(query.text),
                        "result_ids": [item.get("memory_id") for item in result.get("results", [])],
                        "generated_at": _utc_now(),
                        "read_only": True,
                    },
                    "integrity": self.integrity_report(),
                }
            )
            return result

    def apply_retention(self, *, now: Optional[str] = None) -> dict[str, Any]:
        """应用保留期；只把记录降为 COLD，不删除或覆盖历史。"""

        moment = _parse_time(now) or datetime.now(timezone.utc)
        changed: list[str] = []
        with self._lock:
            for record in list(self._records.values()):
                if record.get("lifecycle_state") != "ACTIVE":
                    continue
                expires = _parse_time(record.get("retention_until"))
                if not expires or expires > moment:
                    continue
                self._append_event(
                    "STATUS_CHANGED",
                    {
                        "memory_id": record["id"],
                        "changes": {
                            "lifecycle_state": "COLD",
                            "retention_applied_at": moment.isoformat().replace("+00:00", "Z"),
                        },
                    },
                )
                changed.append(record["id"])
        return {
            "contract_version": CONTRACT_VERSION,
            "changed": changed,
            "deleted": [],
            "execution_authorized": False,
            "production_integration": False,
        }

    def project_current_state(self, *, scope: Optional[str] = None, limit: int = 50) -> dict[str, Any]:
        """跨窗口恢复投影：事实、候选、冲突和未知分开呈现。"""

        with self._lock:
            records = [
                dict(item)
                for item in self._records.values()
                if item.get("bank") == self.bank
                and (scope is None or item.get("scope") == scope)
                and item.get("lifecycle_state") not in {"ARCHIVED", "SUPERSEDED"}
            ]
            records.sort(
                key=lambda item: item.get("last_confirmed_at") or item.get("updated_at") or "",
                reverse=True,
            )
            records.sort(
                key=lambda item: {
                    "VERIFIED": 0,
                    "CANDIDATE": 1,
                    "UNKNOWN": 2,
                    "CONFLICTED": 3,
                }.get(item.get("epistemic_status"), 4)
            )
            selected = records[: max(1, min(int(limit), 200))]
            return {
                "contract_version": CONTRACT_VERSION,
                "bank": self.bank,
                "scope": scope,
                "verified": [item for item in selected if item.get("epistemic_status") == "VERIFIED"],
                "candidates": [item for item in selected if item.get("epistemic_status") == "CANDIDATE"],
                "unknowns": [item for item in selected if item.get("epistemic_status") == "UNKNOWN"],
                "conflicts": [item for item in selected if item.get("epistemic_status") == "CONFLICTED"],
                "next_review": [item["id"] for item in selected if item.get("epistemic_status") in {"UNKNOWN", "CONFLICTED"}],
                "authority": {"execution_authorized": False, "production_integration": False, "promotion": False},
                "integrity": self.integrity_report(),
            }

    def integrity_report(self) -> dict[str, Any]:
        return {
            "valid": bool(self._integrity.get("valid")),
            "errors": list(self._integrity.get("errors", [])),
            "events": len(self._events),
            "records": len(self._records),
            "last_event_hash": self._last_event_hash,
            "snapshot": str(self.snapshot_path),
            "event_ledger": str(self.events_path),
        }

    def stats(self) -> dict[str, Any]:
        by_type: dict[str, int] = {}
        by_status: dict[str, int] = {}
        by_lifecycle: dict[str, int] = {}
        for record in self._records.values():
            for target, key in ((by_type, "memory_type"), (by_status, "epistemic_status"), (by_lifecycle, "lifecycle_state")):
                value = str(record.get(key) or "UNKNOWN")
                target[value] = target.get(value, 0) + 1
        return {
            "contract_version": CONTRACT_VERSION,
            "records": len(self._records),
            "events": len(self._events),
            "by_type": by_type,
            "by_status": by_status,
            "by_lifecycle": by_lifecycle,
            "integrity": self.integrity_report(),
        }


__all__ = [
    "CONTRACT_VERSION",
    "EPISTEMIC_STATUSES",
    "EVENT_VERSION",
    "LIFECYCLE_STATES",
    "MEMORY_TYPES",
    "MemoryIntegrityError",
    "MemoryKernel",
    "MemoryQuery",
    "POLARITIES",
]
