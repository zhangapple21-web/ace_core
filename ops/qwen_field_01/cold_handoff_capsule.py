# ACE-QWEN-FIELD-01 repro ruler, promoted from this window's session-temp dir into
# version control so a pointer cited by a queue card or the experiment report stays
# LIVE.  Scratch output goes to the machine temp root; the only repo write is the
# evidence receipt under 08_GOVERNANCE/evidence/, which refuses to overwrite.
"""Cold-handoff probe: can a different executor finish a task from the capsule alone?

This window wrote the capsule, so "the brief is clear" is not a claim this window
get to make.  The test is a fresh agent that has never seen this codebase or
this conversation: it gets the capsule text and nothing else, and must run the
task through to a submitted result using only what the capsule says.

    py -3.11 -m ops.qwen_field_01.cold_handoff_capsule new      # seed a scratch task, print the capsule
    py -3.11 -m ops.qwen_field_01.cold_handoff_capsule verify   # read the pool back after the handoff

Scratch pool under %TEMP% only; state is this session's state/ directory.
"""

import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
RUNTIME = Path(tempfile.gettempdir()) / "ace_qwen_field_01"
RUNTIME.mkdir(exist_ok=True)

REPO = Path(__file__).resolve().parents[2]
STATE = RUNTIME / "cold_handoff_state.json"
CST = timezone(timedelta(hours=8))
sys.path.insert(0, str(REPO))
sys.stdout.reconfigure(encoding="utf-8")

from core.ace_start import ace_start  # noqa: E402
from core.task import TaskPool  # noqa: E402
from core.worker_capsule import render_task_capsule  # noqa: E402

MODE = sys.argv[1] if len(sys.argv) > 1 else "new"

if MODE == "new":
    pool_dir = Path(tempfile.mkdtemp(prefix="ace_cold_handoff_")) / "pool"
    pool = TaskPool(str(pool_dir))
    task = pool.create_task(
        "冷接手：只凭胶囊文本把一句话写进文件并回交",
        hypothesis="胶囊自带回程命令，换一个从没读过代码的执行体也能独立交回",
        creator="cold-handoff-probe",
        complexity="simple",
        tags=["research"],
        admission={
            "source_type": "system_observation",
            "source_ref": "qwen-field-01-cold-handoff",
            "why_now": "the window that wrote the brief cannot grade its own clarity",
            "evidence": [
                {"source": "field-scan", "content": "任务面与回程端口都在 core/worker_capsule.py"},
            ],
            "expected_result": "review 状态下有可复算的 evidence 与 result",
            "verification_method": "读回任务记录",
            "risk": "scratch pool only",
            "estimated_scope": "one handoff",
        },
    )
    started = ace_start(pool, task.task_id, "cold-executor", lease_seconds=1800)
    assert started["status"] == "STARTED", started
    capsule = render_task_capsule(
        pool, task.task_id, claim_id=started["claim_id"], fencing_token=started["fencing_token"]
    )
    assert capsule["status"] == "CAPSULE_READY", capsule

    STATE.write_text(
        json.dumps(
            {
                "at": datetime.now(CST).isoformat(timespec="seconds"),
                "pool_dir": str(pool_dir),
                "task_id": task.task_id,
                "claim_id": started["claim_id"],
                "fencing_token": started["fencing_token"],
                "capsule_hash": capsule["capsule_hash"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    capsule_path = RUNTIME / "cold_handoff_capsule.txt"
    capsule_path.write_text(capsule["capsule_text"], encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "CAPSULE_SEEDED",
                "task_id": task.task_id,
                "pool_dir": str(pool_dir),
                "char_count": capsule["char_count"],
                "capsule_file": str(capsule_path),
            },
            ensure_ascii=False,
        )
    )
else:
    state = json.loads(STATE.read_text(encoding="utf-8"))
    pool = TaskPool(state["pool_dir"])
    stored = pool.load_task(state["task_id"])
    envelope = (stored.outputs.get("execution_discipline") or {}) if stored else {}
    ledger = envelope.get("evidence_ledger") or {}
    checkpoints = envelope.get("checkpoints") or []
    result = {
        "status": "READBACK",
        "task_status": getattr(stored, "status", None),
        "result_summary": (getattr(stored, "result", "") or "")[:200],
        "evidence": [str(item)[:160] for item in (getattr(stored, "evidence", []) or [])],
        "ledger_keys": {key: len(values or []) for key, values in ledger.items()},
        "checkpoints": [item.get("name") for item in checkpoints if isinstance(item, dict)],
        "checkpoint_capsule_hashes": [
            item.get("capsule_hash") for item in checkpoints if isinstance(item, dict)
        ],
        "capsule_hash_expected": state["capsule_hash"],
        "claim_cleared": not (getattr(stored, "claim_id", "") if stored else ""),
        "pending_now": len(pool.list_tasks(status="pending", limit=20)),
        "active_now": len(pool.list_tasks(status="active", limit=20)),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
