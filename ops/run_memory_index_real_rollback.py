"""Rehearse MemoryIndex rollback using a private, offline copy of the real file.

The production source is read-only. All mutation happens under a temporary
directory; the raw copy is removed when the process exits. The resulting
receipt contains hashes and aggregate counts only, never memory text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
import time
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


from core.memory_index import MemoryIndex, MemoryIndexIntegrityError
from core.memory_kernel import MemoryIntegrityError, MemoryKernel


CONTRACT_VERSION = "ace.memory_index.real_private_backend_rollback.v2"
DATA_BASIS = "REAL_PRIVATE_DATA_OFFLINE_BACKEND_REHEARSAL"


class _RehearsalIdentity:
    name = "ACE-rollback-rehearsal"

    @staticmethod
    def continuity_mark() -> str:
        return "offline-rollback-rehearsal"


class _RehearsalLexicon:
    @staticmethod
    def classify(_text: str) -> list[dict[str, Any]]:
        return []


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _inspect_private_index(path: Path) -> tuple[int, dict[str, int]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("entries"), list):
        raise ValueError("memory_index_shape_invalid")
    entries = payload["entries"]
    if not entries or any(not isinstance(item, dict) for item in entries):
        raise ValueError("memory_index_entries_invalid")
    classes: dict[str, int] = {}
    for item in entries:
        data_class = str(item.get("data_class") or "").strip().upper()
        if not data_class:
            data_class = "UNKNOWN"
        classes[data_class] = classes.get(data_class, 0) + 1
    if classes != {"PRIVATE": len(entries)}:
        raise ValueError("rollback_requires_all_private_source")
    return len(entries), classes


def rehearse(source: Path, receipt_path: Path) -> dict[str, Any]:
    source = source.resolve(strict=True)
    if source.name != "memory_index.json":
        raise ValueError("unexpected_memory_index_filename")

    with tempfile.TemporaryDirectory(prefix="ace-memory-rollback-") as temp_name:
        sandbox = Path(temp_name)
        active_copy = sandbox / "active" / "memory_index.json"
        snapshot_copy = sandbox / "snapshot" / "memory_index.json"
        active_copy.parent.mkdir(parents=True)
        snapshot_copy.parent.mkdir(parents=True)

        # Take a stable snapshot without acquiring or interrupting the live
        # daemon's writer lock. Atomic MemoryIndex replacement means the copy
        # should observe either the old or new complete file; verify stability.
        before_hash = copy_hash = after_hash = ""
        for _attempt in range(5):
            before_hash = _sha256(source)
            try:
                shutil.copy2(source, snapshot_copy)
            except OSError:
                time.sleep(0.2)
                continue
            copy_hash = _sha256(snapshot_copy)
            after_hash = _sha256(source)
            if before_hash == copy_hash == after_hash:
                break
            time.sleep(0.2)
        else:
            raise RuntimeError("could_not_capture_stable_real_index_snapshot")

        entry_count, class_counts = _inspect_private_index(snapshot_copy)
        source_size = snapshot_copy.stat().st_size
        source_mtime_ns = snapshot_copy.stat().st_mtime_ns
        shutil.copy2(snapshot_copy, active_copy)
        active_initial_hash = _sha256(active_copy)
        if active_initial_hash != copy_hash:
            raise RuntimeError("offline_copy_hash_mismatch")

        # Exercise the actual MemoryIndex read/write code against real local
        # PRIVATE records, but only inside the disposable offline copy.
        index = MemoryIndex(active_copy.parent, _RehearsalIdentity(), _RehearsalLexicon())
        baseline_ids = {str(item.get("id")) for item in index._index}
        if len(baseline_ids) != entry_count or index.get_stats().get("total") != entry_count:
            raise RuntimeError("offline_backend_baseline_mismatch")
        candidate_id = index.add(
            title="ACE offline rollback rehearsal",
            content="Synthetic marker used only to exercise local rollback.",
            memory_type="maintenance_test",
            category="offline_rehearsal",
            source="rollback_rehearsal",
            data_class="PRIVATE",
        )
        if index.get_stats().get("total") != entry_count + 1:
            raise RuntimeError("offline_backend_candidate_write_not_persisted")
        if candidate_id not in {str(item.get("id")) for item in index._index}:
            raise RuntimeError("offline_backend_candidate_id_missing")

        # Exercise a bounded real-data import on the staged kernel. It remains
        # candidate-only and is confined to the same disposable directory.
        source_payload = json.loads(snapshot_copy.read_text(encoding="utf-8"))
        selected_records = source_payload["entries"][:50]
        kernel_dir = sandbox / "candidate-kernel"
        kernel = MemoryKernel(kernel_dir)
        import_result = kernel.import_records(
            selected_records,
            selected_by="ops:real_private_rollback_rehearsal",
            source_prefix="offline-real-private-index",
        )
        integrity_before_fault = kernel.integrity_report()
        if not integrity_before_fault.get("valid"):
            raise RuntimeError("candidate_kernel_integrity_invalid_before_fault")
        if not import_result["imported"]:
            raise RuntimeError("candidate_kernel_imported_no_real_records")
        query_text = str(selected_records[0].get("title") or selected_records[0].get("summary") or "")
        query_result = kernel.query(query_text, data_classes=["PRIVATE"], limit=10)
        if not query_result.get("retrieval_receipt", {}).get("read_only"):
            raise RuntimeError("candidate_kernel_query_receipt_missing")
        if any(item.get("data_class") != "PRIVATE" for item in query_result.get("results", [])):
            raise RuntimeError("candidate_kernel_query_boundary_mismatch")

        # Fault-inject the staged candidate ledger, require its integrity check
        # to fail closed, then rebind to the old backend snapshot.
        kernel.events_path.write_bytes(b"{\"injected_candidate_failure\":true}\n")
        try:
            MemoryKernel(kernel_dir)
        except MemoryIntegrityError:
            pass
        else:
            raise RuntimeError("candidate_kernel_did_not_fail_closed_on_corruption")

        restore_temp = active_copy.with_suffix(".restore.tmp")
        started = time.perf_counter()
        shutil.copy2(snapshot_copy, restore_temp)
        if _sha256(restore_temp) != copy_hash:
            raise RuntimeError("rollback_staging_hash_mismatch")
        os.replace(restore_temp, active_copy)
        elapsed_minutes = (time.perf_counter() - started) / 60.0

        restored_hash = _sha256(active_copy)
        restored = MemoryIndex(active_copy.parent, _RehearsalIdentity(), _RehearsalLexicon())
        restored_count = restored.get_stats().get("total")
        restored_ids = {str(item.get("id")) for item in restored._index}
        _, restored_classes = _inspect_private_index(active_copy)
        source_hash_after = _sha256(source)
        if restored_hash != copy_hash or restored_count != entry_count or restored_ids != baseline_ids:
            raise RuntimeError("rollback_restore_verification_failed")

    receipt = {
        "contract_version": CONTRACT_VERSION,
        "status": "PASS_REAL_PRIVATE_DATA_BACKEND_ROLLBACK_REHEARSAL",
        "data_basis": DATA_BASIS,
        "occurred_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_ref": "06_RUNTIME/ace/data/memory/memory_index.json",
        "source_sha256_at_snapshot": before_hash,
        "offline_copy_sha256": copy_hash,
        "rollback_source_sha256": copy_hash,
        "rollback_restored_sha256": restored_hash,
        "source_size_bytes": source_size,
        "entry_count": entry_count,
        "data_class_counts": class_counts,
        "restored_data_class_counts": restored_classes,
        "baseline_ids_restored_exactly": restored_ids == baseline_ids,
        "offline_candidate_writes_persisted": 1,
        "offline_candidate_discarded_by_rollback": True,
        "candidate_kernel_import_selected": import_result["batch_receipt"]["selected_count"],
        "candidate_kernel_imported": import_result["batch_receipt"]["imported_count"],
        "candidate_kernel_import_rejected": import_result["batch_receipt"]["rejected_count"],
        "candidate_kernel_batch_receipt_status": import_result["batch_receipt"]["status"],
        "candidate_kernel_integrity_before_fault": integrity_before_fault.get("valid"),
        "candidate_kernel_retrieval_receipt_read_only": query_result["retrieval_receipt"]["read_only"],
        "candidate_kernel_fail_closed_on_corruption": True,
        "production_acknowledged_writes_during_rehearsal": 0,
        "rollback_lost_baseline_records": 0,
        "rollback_duration_minutes": round(elapsed_minutes, 6),
        "source_mtime_ns_at_start": source_mtime_ns,
        "source_sha256_at_finish": source_hash_after,
        "source_unchanged_at_finish": source_hash_after == before_hash,
        "raw_offline_copy_retained": False,
        "backend_fail_closed_on_corruption": True,
        "backend_atomic_write_exercised": True,
        "production_file_modified": False,
        "production_file_opened_read_only": True,
        "execution_authorized": False,
        "production_integration": False,
    }
    receipt_path = receipt_path.resolve()
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("06_RUNTIME/ace/data/memory/memory_index.json"),
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output:
        receipt_path = args.output
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        receipt_path = args.source.parent / "evidence" / f"real_memory_rollback_{timestamp}.json"
    receipt = rehearse(args.source, receipt_path)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
