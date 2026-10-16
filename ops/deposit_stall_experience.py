"""Deposit the stalled-blocker experience into the canonical knowledge path.

Canonical daemon deposition path is 09_KNOWLEDGE/ (per AGENTS.md); this writes
one constraint experience recording the defect, the counterexample, and the
boundary that escalation must never open the admission gate.
"""
import hashlib
import json
import pathlib
import sys
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).resolve().parent.parent
NOW = datetime.now(timezone.utc)
STAMP = NOW.astimezone().strftime("%Y%m%d%H%M%S")

experience = {
    "experience_id": f"EXP-STALL-{STAMP}",
    "source_task_id": "RQ-ADMISSION-STALL-ROOT-CAUSE",
    "experience_type": "constraint",
    "conclusion": (
        "连续无进展的阻塞必须切换动作，而不只是切换状态字符串。"
        "状态在 consecutive>=3 饱和后长期不变即为停滞，应路由到既有审查链路，"
        "且同一 blocker_fingerprint 只允许产生一项审查任务。"
    ),
    "evidence": [
        {
            "content": (
                "原始 data_admission_recovery.py 用 consecutive >= 3 决定 "
                "RECOVERY_VERIFICATION_DUE，counter 达到 5508 时 recovery_status 与 "
                "next_action 与第 3 次完全相同，状态饱和后不再携带任何进展信息。"
            ),
            "source": "core/data_admission_recovery.py@HEAD",
        },
        {
            "content": (
                "反例证明（同一脚本、同一输入 5421 次观测）：原始代码 distinct_actions 只有 1 个"
                "（研究动作）；修复后出现 escalate_stalled_blocker_to_admission_and_experience_review，"
                "脚本在原始代码 exit=1、修复后 exit=0。"
            ),
            "source": "ops/counterexample_admission_stall.py",
        },
        {
            "content": (
                "回归证据：py -3 -m pytest ops 得 6 failed, 1822 passed；"
                "该 6 项失败在 pristine HEAD 独立复现（6 failed, 104 passed），"
                "且均不 import 本次改动模块，属既有环境问题而非回归。"
            ),
            "source": "py -3 -m pytest ops",
        },
        {
            "content": (
                "live ledger 实测 consecutive_unchanged_observations=5508，"
                "blocker_fingerprint=558570ea8d86a88a7e597f6965fe331b86510894688191f1ae27bf9cf68d1721；"
                "五项核心操作 qualified_sources 为空，准入门保持关闭。"
            ),
            "source": "06_RUNTIME/ace/data/stock_data_evidence/data_admission_recovery_latest.json",
        },
    ],
    "constraints_updated": [
        "数据准入停滞：同一 blocker_fingerprint 只允许一项有效审查任务（幂等）；fingerprint 实质变化才开启新周期。",
        "停滞升级绝不打开准入门、绝不伪造数据源、绝不生成推荐，也不制造有效学习目标。",
        "长期无进展必须触发动作切换（进入既有 Admission/Experience 审查），而不是重复已证明无效的研究动作。",
    ],
    "related_concepts": ["data_admission_stall", "autonomy_action_switch", "idempotent_escalation"],
    "tags": ["data-admission", "stalled", "constraint", "action-switch"],
    "reference_count": 0,
}

# Routed through ExperienceDeposition instead of writing the dict directly.
#
# The hand-written write made this a fifth writer into 09_KNOWLEDGE that
# no lane work had caught, because a census that looks for callers of
# deposit() sees none here. The cost was concrete rather than cosmetic:
# no depositing_lane, no entry in the deposition index, and a record
# find_related cannot reach. The record content is unchanged - only the
# write path is - so the lane, the index and the read side now come from the
# canonical API instead of being maintained by hand.
sys.path.insert(0, str(ROOT))
from core.experience_deposition import ExperienceDeposition

deposition = ExperienceDeposition(str(ROOT / "09_KNOWLEDGE"))
staged = type(
    "EscalationTask",
    (),
    {
        "task_id": experience["source_task_id"],
        "title": experience["experience_id"],
        "hypothesis": experience["conclusion"],
        "evidence": experience["evidence"],
        "tags": experience["tags"],
        "data_class": "STRUCTURE",
    },
)()
record = deposition.deposit(
    task=staged,
    experience_type=experience["experience_type"],
    conclusion=experience["conclusion"],
    constraints_updated=experience["constraints_updated"],
    related_concepts=experience["related_concepts"],
    lane="stall-escalation",
)
target = (ROOT / "09_KNOWLEDGE" / "constraint" / f"{record.experience_id}.json")
print("WROTE", target)
# The canonical path names the file, and may place it under a different type
# directory than requested (an unverified long-term rule is downgraded to
# pattern). Read the bytes of what deposit actually wrote, found by glob,
# rather than by a guessed name.
written = sorted((ROOT / "09_KNOWLEDGE").rglob(f"{record.experience_id}.json"))
if written:
    print("sha256", hashlib.sha256(written[0].read_bytes()).hexdigest())
else:
    print("sha256 <not found on disk>")

