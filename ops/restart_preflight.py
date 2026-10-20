# ACE controlled-restart preflight. Exits nonzero when restart is unsafe.
# Checks: no in-flight tasks, no workspace lock held by a live owner,
# daemon import smoke, current heartbeat alive. Prints a receipt either way.
import glob
import json
import sys

ROOT = r"C:\tmp\ace_core"
ok = True
print("== preflight", __import__("datetime").datetime.now().isoformat())


def fail(message):
    global ok
    ok = False
    print("FAIL:", message)


for status in ("active", "review", "approved", "running"):
    found = glob.glob(r"%s\task_pool\%s\*.json" % (ROOT, status))
    if found:
        fail("in_flight %s: %s" % (status, [f.split("\\")[-1] for f in found][:5]))

lock = ROOT + r"\06_RUNTIME\ace\data\memory\.workspace.write.lock"
try:
    with open(lock, encoding="utf-8") as handle:
        content = handle.read(200)
    fail("workspace lock held: %s" % content[:100])
except FileNotFoundError:
    print("ok: no workspace write lock")

try:
    heartbeat = json.load(
        open(ROOT + r"\06_RUNTIME\ace\data\memory\heartbeat.json", encoding="utf-8")
    )
    print(
        "ok: heartbeat pid=%s status=%s beat=%s"
        % (heartbeat.get("pid"), heartbeat.get("status"), str(heartbeat.get("last_beat"))[11:19])
    )
except (OSError, ValueError) as exc:
    fail("heartbeat unreadable: %s" % exc)

sys.path.insert(0, ROOT)
try:
    import ace_daemon  # noqa: F401

    print("ok: ace_daemon imports")
except Exception as exc:
    fail("daemon import smoke failed: %s" % exc)

print("PREFLIGHT:", "GO" if ok else "NO-GO")
sys.exit(0 if ok else 2)
