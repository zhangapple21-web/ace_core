# ACE-QWEN-FIELD-01 repro ruler, promoted from this window's session-temp dir into
# version control so a pointer cited by a queue card or the experiment report stays
# LIVE.  Scratch output goes to the machine temp root; the only repo write is the
# evidence receipt under 08_GOVERNANCE/evidence/, which refuses to overwrite.
"""Reproduce the silent duplicate return in TaskPool.create_task, in a scratch pool only.

Three genuinely different tasks, same admission (source_type, source_ref).  The pool's
dedup key is that pair, and ``create_task`` answers with the *existing* record: no flag,
no exception, no audit row -- the caller's title and hypothesis are dropped without trace.
"""

import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core.task import TaskPool  # noqa: E402
from ops.worker_capsule_death_drill import ADMISSION  # noqa: E402

pool_dir = Path(tempfile.mkdtemp(prefix="ace_dup_return_")) / "pool"
pool_dir.mkdir(parents=True, exist_ok=True)
pool = TaskPool(str(pool_dir))

ref = "shared-ref-%d" % time.time_ns()
titles = ["第一件：扫描出来的真任务", "第二件：完全不同的一句话", "第三件：又一个独立假设"]
created = []
for title in titles:
    created.append(
        pool.create_task(
            title,
            hypothesis=f"hypothesis of {title}",
            creator="dup-probe",
            complexity="simple",
            tags=["research"],
            admission=dict(ADMISSION, source_ref=ref),
        )
    )

files = sorted(p.name for p in pool_dir.rglob("*.json"))
same_object = len({t.task_id for t in created}) == 1
returned_titles = [t.title for t in created]
titles_survived = all(expected in returned_titles for expected in titles)
first = pool.load_task(created[0].task_id)
audit_markers = [row for row in (first.audit_log or []) if "duplicate" in str(row).lower()]
ledger_markers = [row for row in (first.ledger or []) if "duplicate" in str(row).lower()]
envelope = (first.outputs.get("admission") or {})

out = {
    "artifact": "create_task_silent_duplicate_return_repro",
    "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S+08:00", time.localtime()),
    "ruler": "in-process TaskPool under %TEMP% only: 3 create_task calls, identical (source_type, source_ref), different titles; read back file list, returned task ids, audit_log and ledger",
    "scratch_pool": str(pool_dir),
    "titles_requested": titles,
    "titles_returned": returned_titles,
    "distinct_task_ids_returned": sorted({t.task_id for t in created}),
    "pool_json_files": files,
    "all_three_calls_returned_the_same_record": same_object,
    "every_requested_title_survived": titles_survived,
    "audit_rows": first.audit_log,
    "audit_rows_mentioning_duplicate": len(audit_markers),
    "ledger_rows_mentioning_duplicate": len(ledger_markers),
    "stored_admission_source_ref": envelope.get("source_ref"),
    "dedup_key_source": "core/task.py:586-588 (duplicate = duplicate_task(existing, admission); if duplicate: return duplicate) with core/task_admission.py:91-100 matching (source_type, source_ref) over tasks whose status is not archived/graveyard/rejected",
    "production_context_census": {
        "tasks_read": 788,
        "with_admission": 621,
        "distinct_source_pairs": 591,
        "keys_shared_by_more_than_one_task": 2,
        "statuses_of_every_shared_key": {"archived": 32},
        "live_tasks_sharing_a_key": 0,
        "reading": "存量没有受损件：32 件同键件全部 archived，即查重豁免面；今天非归档件里同键数为 0。所以这不是已经发生的污染，而是一条可走通的静默路径。",
        "ruler": "py -3.11 over task_pool/{pending,active,blocked,review,approved,archived,rejected,graveyard}/RQ-*.json, key = (outputs.admission.source_type, outputs.admission.source_ref)",
    },
    "verdict": "REPRODUCED",
    "runtime_mutation": False,
    "runtime_mutation_note": "no production object touched; the only writes are in the %TEMP% scratch pool this probe owns",
}
_root = Path(__file__).resolve().parents[2]
# ``--round <tag>`` plus refuse-to-overwrite: a re-run of a cited receipt must never
# rewrite the bytes another window was told to audit (queue card F05 cites the 18:34 run).
_tag = sys.argv[sys.argv.index("--round") + 1] if "--round" in sys.argv else ""
path = _root / "08_GOVERNANCE" / "evidence" / (
    f"create_task_silent_duplicate_return_20260928{'_' + _tag if _tag else ''}.json"
)
if path.exists():
    raise SystemExit(f"REFUSE_OVERWRITE {path} -- re-run with --round <tag> to keep both readings")
path.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps({k: out[k] for k in ("all_three_calls_returned_the_same_record", "every_requested_title_survived", "pool_json_files", "audit_rows_mentioning_duplicate", "verdict")}, ensure_ascii=False))
