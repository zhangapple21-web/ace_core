"""Run a live-refresh rehearsal against a temporary copy of benchmark evidence.

This script is intentionally a real file (rather than stdin) because Windows
multiprocessing needs an importable __main__ when source batches are isolated.
It never writes to the production evidence directory.
"""

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.stock_data_reliability import StockDataBenchmark


def main() -> None:
    source = Path(__file__).resolve().parent.parent / "06_RUNTIME" / "ace" / "data" / "stock_data_evidence" / "stock_data_benchmark_latest.json"
    with tempfile.TemporaryDirectory() as directory:
        evidence_dir = Path(directory)
        shutil.copy2(source, evidence_dir / "stock_data_benchmark_latest.json")
        run = StockDataBenchmark(str(evidence_dir)).refresh_live_operations(rounds=1)
        matrix = json.loads((evidence_dir / "A_SHARE_DATA_CAPABILITY_MATRIX.json").read_text(encoding="utf-8"))
        phase = matrix["phase_two_admission"]
        print(json.dumps({
            "isolated": True,
            "incremental_refresh": run["incremental_refresh"],
            "source_operations": {
                source: run["summary"]["sources"].get(source, {}).get("operation_quality", {})
                for source in ("pytdx", "sina")
            },
            "phase_two": {
                operation: phase["core_operations"][operation]
                for operation in ("quote", "minute_kline_1m", "index")
            },
            "overall": phase["status"],
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()

