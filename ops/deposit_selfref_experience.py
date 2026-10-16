"""Deposit the second experience: self-referential verification starves review.

Records the measured finding (43.2% vs 10.0% non-convergence) and the two
defects this escalation shipped with, so the constraint survives a window
change.  Canonical daemon deposition path is 09_KNOWLEDGE/.
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
    "experience_id": f"EXP-SELFREF-{STAMP}",
    "source_task_id": "RQ-20261016-001",
    "experience_type": "constraint",
    "conclusion": (
        "任务的 verification_method 若指向自身记录（自我指涉），复审只能重新发现出生时那条证据，"
        "必然撞上 unchanged_review_count 上限并熔断。要让研究收敛，验证必须指向任务之外的可测量对象。"
    ),
    "evidence": [
        {
            "content": (
                "实测 1,510 个池内任务：verification_kind=self_referential 375 个其中 162 个 "
                "terminal_non_convergent = 43.2%；external_object 968 个其中 97 个 = 10.0%。"
                "自我指涉类死亡率是外部对象类的 4.3 倍。"
            ),
            "source": "task_pool/**/RQ-*.json 全量统计 (ops/inspect_verification_kind.py)",
        },
        {
            "content": (
                "按 creator 统计：observation_to_task 422 个任务中 172 个 terminal (40.8%，168 进 graveyard)；"
                "file_scanner 535 个中仅 9 个 (1.7%)。差别在证据可达性，不在任务量。"
            ),
            "source": "ops/inspect_evidence_paths.py",
        },
        {
            "content": (
                "对照实例：RQ-20261016-002(observation_to_task) verification='Re-observe the runtime "
                "condition'，researcher 只找到 1 条证据（就是 admission 里那条），5 轮后熔断；"
                "RQ-20261016-003(file_scanner) verification='Recheck the source file'，"
                "1 轮即收到 5 条 memory 证据并归档。"
            ),
            "source": "ops/inspect_task_evidence_contrast.py",
        },
        {
            "content": (
                "第二缺陷：熔断后的复审停在 blocked，而 create_task 的去重会把它当作同一 admission "
                "intent 的 duplicate 返回，导致后续升级永远复用这个死任务、修正后的复审永不执行。"
                "修复：按已熔断数量提升 operation_intent 代数(gen2...)，使替换任务可被区分。"
            ),
            "source": "ops/test_data_admission_stall_escalation.py",
        },
    ],
    "constraints_updated": [
        "新任务的 verification_method 必须指向任务之外的可测量对象；自我指涉的验证方式不得作为升级任务的验收方式。",
        "同一 blocker_fingerprint 的复审一旦熔断，必须允许以更高代数重建，否则修正后的路径被死任务永久挡住。",
        "幂等与可重建必须同时成立：重复调用不产生重复任务，熔断后仍能产生且仅产生一个替换任务。",
    ],
    "related_concepts": [
        "self_referential_verification",
        "non_convergent_review",
        "admission_generation",
        "data_admission_stall",
    ],
    "tags": ["data-admission", "stalled", "constraint", "convergence", "verification-method"],
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
    lane="selfref-escalation",
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

