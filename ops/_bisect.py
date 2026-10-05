"""Bisect a timed-out slice down to the individual slow files.

Usage: python _bisect.py <out_dir> <per_file_seconds> <file> [<file> ...]
Each file runs alone so one hang is attributed to exactly one test module.
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
PER_FILE = int(sys.argv[2])
FILES = sys.argv[3:]

os.makedirs(OUT, exist_ok=True)
env = dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")

rows = []
for f in FILES:
    started = time.time()
    timed_out = False
    code = None
    try:
        proc = subprocess.run(
            [PY, "-m", "pytest", "-q", "--tb=no", "-p", "no:cacheprovider", f],
            cwd=ROOT, capture_output=True, timeout=PER_FILE, env=env)
        text = (proc.stdout or b"").decode("utf-8", "replace")
        code = proc.returncode
    except subprocess.TimeoutExpired as exc:
        text = (exc.stdout or b"").decode("utf-8", "replace")
        timed_out = True
    secs = round(time.time() - started, 1)
    counts = {}
    for line in reversed(text.strip().splitlines()):
        if ("passed" in line or "failed" in line) and "in " in line:
            for tok in ("passed", "failed", "error", "errors", "skipped"):
                for i, p in enumerate(line.split()):
                    if p.startswith(tok):
                        try:
                            counts[tok] = int(line.split()[i - 1])
                        except Exception:
                            pass
            break
    rows.append({"file": f, "seconds": secs, "timed_out": timed_out,
                 "returncode": code, "counts": counts,
                 "tail": text.strip().splitlines()[-3:] if text.strip() else []})
    print("%7.1fs %-9s %-58s %s" % (
        secs, "TIMEOUT" if timed_out else (counts or "?"),
        f.split("/")[-1][:58], counts))
    sys.stdout.flush()

with io.open(os.path.join(OUT, "bisect.json"), "w", encoding="utf-8") as fh:
    fh.write(json.dumps(rows, ensure_ascii=False, indent=1))
print("\nslow(>=20s)=%d  timeouts=%d" % (
    sum(1 for r in rows if r["seconds"] >= 20),
    sum(1 for r in rows if r["timed_out"])))
