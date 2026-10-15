"""First: what does the house already have, what is missing, and why tasks fail.

The owner's instruction before every action: look at what the house has, what it
lacks, and what causes failure. So the inventory comes before the build.
"""
import json
import sys
from pathlib import Path

ROOT = Path(r"C:\tmp/ace_core")
out = []


def show(t):
    out.append("")
    out.append("=== " + t)


# ------------------------------------------------- what the house has
show("free-zone windows and what each one emits")
emitters = {
    "autonomous_adjudication": ("core/autonomous_adjudication.py", "receipts in 08_GOVERNANCE/autonomous_adjudication/receipts"),
    "dead_component_watch": ("ops/dead_component_watch.py", "08_GOVERNANCE/structural_integrity/dead_components_snapshot.json"),
    "external_reviewer": ("core/free_zone_external_reviewer.py", "07_SANDBOX/.../reports/external_review/*.json + bridge receipts"),
    "tombstoning": ("ops/process_blocked_backlog.py", "09_KNOWLEDGE/lesson via deposit(lane=)"),
    "roundtable": ("core/free_zone_roundtable.py", "07_SANDBOX/.../reports/roundtable/*.json -> distillation"),
}
for name, (src, sink) in emitters.items():
    path = ROOT / src
    exists = path.exists()
    calls_deposit = False
    if exists:
        text = path.read_text(encoding="utf-8", errors="ignore")
        calls_deposit = "deposit(" in text
    out.append(f"  {name:26s} exists={exists}  writes_into_knowledge={calls_deposit}")
    out.append(f"      sink: {sink}")

show("knowledge substrate state")
lesson_dir = ROOT / "09_KNOWLEDGE" / "lesson"
lessons = sorted(lesson_dir.glob("*.json")) if lesson_dir.is_dir() else []
by_day: dict[str, int] = {}
for p in lessons:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        by_day[str(d.get("created_at", ""))[:10]] = by_day.get(str(d.get("created_at", ""))[:10], 0) + 1
    except Exception:
        pass
out.append(f"  lesson records: {len(lessons)}  by_day={by_day}")
lanes: dict[str, int] = {}
for p in lessons:
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        lanes[str(d.get("depositing_lane", "?"))] = lanes.get(str(d.get("depositing_lane", "?")), 0) + 1
    except Exception:
        pass
out.append(f"  by depositing lane: {lanes}")

# ------------------------------------------------- what is missing
show("the missing socket: emitters that never call deposit")
for name, (src, _) in emitters.items():
    path = ROOT / src
    if not path.exists():
        continue
    text = path.read_text(encoding="utf-8", errors="ignore")
    if "deposit(" not in text:
        out.append(f"  {name}: no deposit call -> its learning never reaches 09_KNOWLEDGE")

Path(r"C:\tmp/ops_inventory.txt").write_text("\n".join(out), encoding="utf-8")
print("\n".join(out))