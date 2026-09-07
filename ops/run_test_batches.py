"""Run pytest in bounded batches and persist exit evidence.

This is a diagnostic helper only; it never starts ACE runtime services and does
not alter production state.  Each batch is a fresh subprocess so a lost
terminal session cannot erase the evidence from earlier batches.
"""
from __future__ import annotations

import json
import argparse
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs" / "test_runs"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run pytest in resumable, persisted batches.")
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--timeout-seconds", type=int, default=90)
    parser.add_argument(
        "--include-slow-runtime-mainline",
        action="store_true",
        help="Include test_24h_runtime_mainline.py (normally delegated or run separately).",
    )
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    files = sorted((ROOT / "ops").glob("test_*.py"))
    if not args.include_slow_runtime_mainline:
        files = [path for path in files if path.name != "test_24h_runtime_mainline.py"]
    batch_size = args.batch_size
    records: list[dict] = []
    interrupted = False
    try:
        for index in range(0, len(files), batch_size):
            batch = files[index : index + batch_size]
            started = time.time()
            command = [sys.executable, "-m", "pytest", "-q", "-ra", "--durations=10", *map(str, batch)]
            try:
                result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=args.timeout_seconds)
                status = "completed"
                exit_code = result.returncode
                stdout = result.stdout[-12000:]
                stderr = result.stderr[-4000:]
            except subprocess.TimeoutExpired as exc:
                status = "timeout"
                exit_code = None
                stdout = (exc.stdout or "")[-12000:] if isinstance(exc.stdout, str) else ""
                stderr = (exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else ""
            record = {
                "batch": index // batch_size + 1,
                "files": [str(path.relative_to(ROOT)) for path in batch],
                "status": status,
                "exit_code": exit_code,
                "duration_seconds": round(time.time() - started, 3),
                "stdout_tail": stdout,
                "stderr_tail": stderr,
            }
            records.append(record)
            (OUT / f"batch_{record['batch']:02d}.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(json.dumps({k: record[k] for k in ("batch", "status", "exit_code", "duration_seconds")}, ensure_ascii=False), flush=True)
    except KeyboardInterrupt:
        interrupted = True
        print("{\"status\": \"interrupted\", \"exit_code\": 130}", flush=True)
    summary = {
        "total_batches": len(records),
        "completed": sum(r["status"] == "completed" for r in records),
        "failed": sum(r["status"] == "completed" and r["exit_code"] != 0 for r in records),
        "timeouts": sum(r["status"] == "timeout" for r in records),
        "interrupted": interrupted,
        "records": records,
    }
    (OUT / "batch_summary_20260831.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    if interrupted:
        return 130
    return 1 if summary["failed"] or summary["timeouts"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

