"""Run every test of the two hanging modules one at a time, with a per-case cap.

Purpose is attribution, not a green run: the goal is to name which cases hang so
they can be reported as a known environment limit rather than as "the suite does
not finish". Each case is independent, so a hang costs one case, not the module.

Usage: python _percase.py <out.json> <per_case_seconds> <ids_file> [<ids_file> ...]
"""
import io
import json
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PY = sys.executable
OUT = sys.argv[1]
PER = int(sys.argv[2])
env = dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")

rows = []
all_ids = []
for f in sys.argv[3:]:
    all_ids += [l.strip() for l in io.open(f, encoding="utf-8") if l.strip()]

print("cases: %d, per-case cap %ds" % (len(all_ids), PER))
sys.stdout.flush()

for i, tid in enumerate(all_ids, 1):
    started = time.time()
    timed_out = False
    try:
        proc = subprocess.run(
            [PY, "-m", "pytest", "-q", "--tb=no", "-p", "no:cacheprovider", tid],
            cwd=ROOT, capture_output=True, timeout=PER, env=env)
        text = (proc.stdout or b"").decode("utf-8", "replace")
        code = proc.returncode
    except subprocess.TimeoutExpired as exc:
        text = (exc.stdout or b"").decode("utf-8", "replace")
        code = None
        timed_out = True
    secs = round(time.time() - started, 1)
    verdict = "HANG" if timed_out else ("PASS" if code == 0 else "FAIL")
    rows.append({"id": tid, "seconds": secs, "verdict": verdict,
                 "returncode": code})
    if verdict != "PASS" or secs >= 5:
        print("%4d/%d %8.1fs %-4s %s" % (i, len(all_ids), secs, verdict, tid))
        sys.stdout.flush()
    with io.open(OUT, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(rows, ensure_ascii=False, indent=1))

passed = sum(1 for r in rows if r["verdict"] == "PASS")
failed = sum(1 for r in rows if r["verdict"] == "FAIL")
hung = sum(1 for r in rows if r["verdict"] == "HANG")
print("\nPASS=%d FAIL=%d HANG=%d TOTAL=%d" % (passed, failed, hung, len(rows)))
for r in rows:
    if r["verdict"] != "PASS":
        print("  %-4s %8.1fs %s" % (r["verdict"], r["seconds"], r["id"]))
