"""Record a read-only data-admission recovery assessment from existing evidence."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.data_admission_recovery import DataAdmissionRecovery


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    data_dir = root / "06_RUNTIME" / "ace" / "data"
    matrix_path = data_dir / "stock_data_evidence" / "A_SHARE_DATA_CAPABILITY_MATRIX.json"
    try:
        matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "MATRIX_UNAVAILABLE", "reason": type(error).__name__}, ensure_ascii=False))
        return 2
    report = DataAdmissionRecovery(data_dir).build(matrix)
    print(json.dumps({
        "status": report["recovery_status"],
        "phase_two_status": report["phase_two_status"],
        "unresolved_operations": report["unresolved_operations"],
        "path": str(DataAdmissionRecovery(data_dir).path),
        "side_effects": report["side_effects"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

