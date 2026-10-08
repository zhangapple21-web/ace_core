# E9 machine grading: count what the converter and lifecycle actually did.
# No judgment calls, only counts. A human (or a future grader) interprets.
import glob
import json
import os

ROOT = r"C:\tmp\ace_core"


def load_tasks():
    tasks = []
    for status in (
        "pending", "active", "review", "approved",
        "archived", "blocked", "rejected", "graveyard",
    ):
        for path in glob.glob(os.path.join(ROOT, "task_pool", status, "*.json")):
            try:
                with open(path, encoding="utf-8") as handle:
                    tasks.append(json.load(handle))
            except (OSError, ValueError):
                continue
    return tasks


def main():
    tasks = load_tasks()
    forged = [t for t in tasks if "question_forge" in (t.get("tags") or [])]
    by_status = {}
    for task in forged:
        by_status[task.get("status", "?")] = by_status.get(task.get("status", "?"), 0) + 1
    with_exp = 0
    for task in forged:
        task_id = task.get("task_id", "")
        for tier in ("pattern", "constraint", "lesson", "axiom", "observation"):
            if glob.glob(os.path.join(ROOT, "09_KNOWLEDGE", tier, "*%s*.json" % task_id)):
                with_exp += 1
                break
    report = {
        "forged_total": len(forged),
        "forged_by_status": by_status,
        "forged_with_experience": with_exp,
        "pool_total": len(tasks),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    out = os.path.join(
        os.environ.get("TEMP", r"C:\Users\Administrator\AppData\Local\Temp"),
        "opencode",
        "ace_E9_grade.json",
    )
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    print("written:", out)


if __name__ == "__main__":
    main()
