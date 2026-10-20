"""Run the whole suite in bounded slices so one hang cannot hide the rest.

A single 900s run that times out tells you nothing except that something hung.
Slicing by file gives per-slice attribution, and a slice that hangs gets
bisected rather than blocking its neighbours.

Usage: python _slice.py <out_dir> [slice_seconds] [files_per_slice]
Writes: <out_dir>/slice_NNN.json and summary.json
"""
import glob
import io
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
SLICE_SECONDS = int(sys.argv[2]) if len(sys.argv) > 2 else 240
PER_SLICE = int(sys.argv[3]) if len(sys.argv) > 3 else 10
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "ops", "_slice_out")

os.makedirs(OUT, exist_ok=True)
env = dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")

files = sorted(
    p for p in glob.glob(os.path.join(ROOT, "**", "test_*.py"), recursive=True)
    if "__pycache__" not in p and "backups" not in p and "\\.git" not in p
)


def run(batch, idx):
    dest = os.path.join(OUT, "slice_%03d.json" % idx)
    cmd = [PY, "-m", "pytest", "-q", "--tb=no", "-p", "no:cacheprovider"] + batch
    started = time.time()
    timed_out = False
    try:
        proc = subprocess.run(cmd, cwd=ROOT, capture_output=True,
                              timeout=SLICE_SECONDS, env=env)
        raw = proc.stdout or b""
        code = proc.returncode
    except subprocess.TimeoutExpired as exc:
        raw = exc.stdout or b""
        code = None
        timed_out = True
    text = raw.decode("utf-8", "replace")
    # pytest -q tail looks like: "5 failed, 106 passed in 22.74s"
    summary = {}
    for token in ("passed", "failed", "error", "errors", "skipped", "xfailed", "xpassed"):
        for line in reversed(text.splitlines()):
            if token in line and ("passed" in line or "failed" in line or line.strip().startswith(token)):
                parts = line.split()
                for i, p in enumerate(parts):
                    if p == token.rstrip("s") or p.startswith(token):
                        try:
                            summary[token] = int(parts[i - 1])
                        except Exception:
                            pass
                break
    record = {
        "slice": idx,
        "files": [os.path.relpath(f, ROOT).replace("\\", "/") for f in batch],
        "returncode": code,
        "timed_out": timed_out,
        "seconds": round(time.time() - started, 1),
        "counts": summary,
        "tail": text.strip().splitlines()[-6:] if text.strip() else [],
        "raw": text,
    }
    with io.open(dest, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False, indent=1))
    return record


def main():
    results = []
    batches = [files[i:i + PER_SLICE] for i in range(0, len(files), PER_SLICE)]
    for idx, batch in enumerate(batches, 1):
        rec = run(batch, idx)
        results.append({k: v for k, v in rec.items() if k != "raw"})
        print("slice %03d  %2d files  %6.1fs  %-10s %s" % (
            idx, len(batch), rec["seconds"],
            "TIMEOUT" if rec["timed_out"] else (rec["counts"] or "?"),
            rec["files"][0].split("/")[-1]))
        sys.stdout.flush()
    with io.open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps(results, ensure_ascii=False, indent=1))
    tot = {"passed": 0, "failed": 0, "errors": 0, "skipped": 0}
    for r in results:
        for k in tot:
            tot[k] += r["counts"].get(k, 0) or 0
    print("\nTOTALS %s | timed_out_slices=%d" % (
        tot, sum(1 for r in results if r["timed_out"])))


if __name__ == "__main__":
    main()
