"""
经验沉积系统 — 任务完成后的知识沉淀

每当任务从 approved/ 进入 archived/ 时，自动生成一条经验记录。

经验记录不独立存在，必须关联到：
  - 来源任务
  - 证据
  - 约束更新（如果有）
  - 词库概念（如果有）

经验分类（同时也是认知等级，不得混用）：
  - axiom: 公理 — VERIFIED_FACT，必须有独立验证收据
  - constraint: 约束 — RULE，必须有独立验证收据
  - pattern: 模式 — EVIDENCE，反复出现的结构，仍是可复核证据
  - lesson: 教训 — COUNTEREXAMPLE，失败或被废弃的经验
  - observation: 观察 — OBSERVATION，弱结论，供参考

升级闸门：一次执行结果在拿到 ``verified_outcome_receipt``（由
``core.outcome_receipt.OutcomeReceiptRecorder`` 产生，至少两份独立证据组）
之前只能停在 observation/pattern；未经独立验证的观察不得成为长期规则。
"""

import hashlib
import json
import os
import re
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
from .mirror_constitution import DATA_CLASSES, validate_data_boundary

# 经验类型 -> 认知等级。等级不可凭“证据条数”跳级。
EPISTEMIC_STATUS = {
    "observation": "OBSERVATION",
    "pattern": "EVIDENCE",
    "lesson": "COUNTEREXAMPLE",
    "constraint": "RULE",
    "axiom": "VERIFIED_FACT",
}

# 只有这两个等级属于“长期规则”，因此必须经过独立验证闸门。
LONG_TERM_TYPES = ("axiom", "constraint")

# 未验证时允许降级到的最高等级。
MAX_UNVERIFIED_TYPE = "pattern"


class Experience:
    """经验记录"""

    EXPERIENCE_TYPES = ["axiom", "constraint", "pattern", "lesson", "observation"]

    def __init__(
        self,
        experience_id: str,
        source_task_id: str,
        experience_type: str,
        conclusion: str,
        evidence: List[Dict],
        constraints_updated: List[str],
        related_concepts: List[str],
        tags: Optional[List[str]] = None,
        created_at: Optional[str] = None,
        data_class: str = "PRIVATE",
        epistemic_status: Optional[str] = None,
        verification: Optional[Dict] = None,
        downgrade_reason: str = "",
    ):
        self.experience_id = experience_id
        self.source_task_id = source_task_id
        self.experience_type = experience_type if experience_type in self.EXPERIENCE_TYPES else "observation"
        self.conclusion = conclusion
        self.evidence = evidence
        self.constraints_updated = constraints_updated
        self.related_concepts = related_concepts
        self.tags = tags or []
        classification = str(data_class or "PRIVATE").strip().upper()
        self.data_class = classification if classification in DATA_CLASSES else "PRIVATE"
        self.created_at = created_at or datetime.now().isoformat()
        self.reference_count = 0
        self.last_used_at = self.created_at
        self.epistemic_status = epistemic_status or EPISTEMIC_STATUS.get(self.experience_type, "OBSERVATION")
        self.verification = dict(verification or {})
        self.downgrade_reason = downgrade_reason

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experience_id": self.experience_id,
            "source_task_id": self.source_task_id,
            "experience_type": self.experience_type,
            "epistemic_status": self.epistemic_status,
            "conclusion": self.conclusion,
            "evidence": self.evidence,
            "constraints_updated": self.constraints_updated,
            "related_concepts": self.related_concepts,
            "tags": self.tags,
            "data_class": self.data_class,
            "created_at": self.created_at,
            "reference_count": self.reference_count,
            "last_used_at": self.last_used_at,
            "verification": self.verification,
            "downgrade_reason": self.downgrade_reason,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Experience":
        value = dict(data)
        reference_count = int(value.pop("reference_count", 0) or 0)
        last_used_at = value.pop("last_used_at", None)
        experience = cls(**value)
        experience.reference_count = reference_count
        experience.last_used_at = last_used_at or experience.created_at
        return experience

    def touch(self):
        self.last_used_at = datetime.now().isoformat()
        self.reference_count += 1


class ExperienceDeposition:
    """
    经验沉积器 — 负责将任务产出转化为可复用的知识

    目录结构：
    09_KNOWLEDGE/
        axiom/        公理
        constraint/   约束
        pattern/      模式
        lesson/       教训
        observation/  观察
        index.json    全局索引
    """

    EXPERIENCE_DIRS = {
        "axiom": "axiom",
        "constraint": "constraint",
        "pattern": "pattern",
        "lesson": "lesson",
        "observation": "observation",
    }

    def __init__(self, knowledge_dir: str):
        self.knowledge_dir = Path(knowledge_dir)
        self.index_path = self.knowledge_dir / "index.json"
        self._ensure_dirs()

    def _ensure_dirs(self):
        for subdir in self.EXPERIENCE_DIRS.values():
            (self.knowledge_dir / subdir).mkdir(parents=True, exist_ok=True)
        if not self.index_path.exists():
            self._save_index({})

    def _load_index(self) -> Dict:
        if self.index_path.exists():
            with open(self.index_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_index(self, index: Dict):
        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _experience_id(source_task_id: str, experience_type: str) -> str:
        """Return a stable, filesystem-safe identity for one deposition kind."""
        identity = f"{source_task_id}|{experience_type}"
        safe_task_id = re.sub(r"[^A-Za-z0-9._-]+", "_", source_task_id).strip("._-")
        safe_task_id = (safe_task_id or "task")[:48]
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
        return f"EXP-{safe_task_id}-{experience_type}-{digest}"

    @staticmethod
    def _load_experience(path: Path) -> Optional[Experience]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                value = json.load(f)
            return Experience.from_dict(value) if isinstance(value, dict) else None
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return None

    def _find_existing(self, source_task_id: str, experience_type: str) -> Optional[Experience]:
        """Find current or legacy deposition without creating a duplicate."""
        index = self._load_index()
        for experience_id, record in index.items():
            if not isinstance(record, dict):
                continue
            if (
                record.get("source_task") != source_task_id
                or record.get("type") != experience_type
            ):
                continue
            path = Path(record.get("path", ""))
            experience = self._load_experience(path)
            if (
                experience
                and experience.source_task_id == source_task_id
                and experience.experience_type == experience_type
            ):
                return experience

        subdir = self.EXPERIENCE_DIRS.get(experience_type, "observation")
        for path in sorted((self.knowledge_dir / subdir).glob("EXP-*.json")):
            experience = self._load_experience(path)
            if (
                experience
                and experience.source_task_id == source_task_id
                and experience.experience_type == experience_type
            ):
                return experience
        return None


    @staticmethod
    def _verification_state(task) -> Dict[str, Any]:
        """Read the existing outcome-receipt proof instead of inferring trust."""
        outputs = getattr(task, "outputs", None)
        outputs = outputs if isinstance(outputs, dict) else {}
        receipt = outputs.get("verified_outcome_receipt")
        if not isinstance(receipt, dict) or receipt.get("status") != "VERIFIED":
            return {"status": "UNVERIFIED", "reason": "no_verified_outcome_receipt"}
        groups = int(receipt.get("independent_evidence_groups", 0) or 0)
        refs = [str(ref).strip() for ref in receipt.get("evidence_refs", []) if str(ref).strip()]
        if groups < 2 or len(refs) < 2:
            return {
                "status": "UNVERIFIED",
                "reason": "independent_evidence_required",
                "independent_evidence_groups": groups,
            }
        return {
            "status": "VERIFIED",
            "verifier": str(receipt.get("verifier", "")),
            "verified_at": str(receipt.get("verified_at", "")),
            "result_ref": str(receipt.get("result_ref", "")),
            "verification_ref": str(receipt.get("verification_ref", "")),
            "independent_evidence_groups": groups,
            "evidence_refs": refs,
        }

    def _persist_experience(self, experience: Experience, path: Path) -> None:
        """Persist one experience record atomically, then refresh the index."""
        temporary = path.with_suffix(".json.tmp")
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(experience.to_dict(), handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        self._index_experience(experience, path)

    def _index_experience(self, experience: Experience, path: Path) -> None:
        index = self._load_index()
        index[experience.experience_id] = {
            "path": str(path),
            "type": experience.experience_type,
            "epistemic_status": experience.epistemic_status,
            "conclusion": experience.conclusion[:100],
            "source_task": experience.source_task_id,
        }
        self._save_index(index)

    def deposit(
        self,
        task,
        experience_type: Optional[str] = None,
        conclusion: Optional[str] = None,
        constraints_updated: Optional[List[str]] = None,
        related_concepts: Optional[List[str]] = None,
    ) -> Experience:
        """
        将任务转化为经验记录并沉积

        未经独立验证的执行结果不会成为长期规则：``axiom``/``constraint``
        会降到 ``pattern``，并在记录里留下降级原因与验证缺口。
        """
        if experience_type is None:
            if task.guardian_decision in Experience.EXPERIENCE_TYPES:
                experience_type = task.guardian_decision
            else:
                experience_type = "observation"
        if experience_type not in Experience.EXPERIENCE_TYPES:
            experience_type = "observation"

        resolved_conclusion = conclusion or task.hypothesis or task.title

        existing = self._find_existing(task.task_id, experience_type)
        if existing is not None:
            return existing

        verification = self._verification_state(task)
        downgrade_reason = ""
        if experience_type in LONG_TERM_TYPES and verification["status"] != "VERIFIED":
            downgrade_reason = "downgraded_from_{}:{}".format(
                experience_type, verification.get("reason", "unverified")
            )
            experience_type = MAX_UNVERIFIED_TYPE

        exp_id = self._experience_id(task.task_id, experience_type)

        evidence = []
        for ev in (task.evidence or [])[:10]:
            if isinstance(ev, dict):
                evidence.append({
                    "content": ev.get("content", "")[:300],
                    "source": ev.get("source", ""),
                })

        exp = Experience(
            experience_id=exp_id,
            source_task_id=task.task_id,
            experience_type=experience_type,
            conclusion=resolved_conclusion,
            evidence=evidence,
            constraints_updated=constraints_updated or [],
            related_concepts=related_concepts or [],
            tags=task.tags + [experience_type],
            data_class=getattr(task, "data_class", "PRIVATE"),
            verification=verification,
            downgrade_reason=downgrade_reason,
        )

        boundary = validate_data_boundary({"data_class": exp.data_class}, target="INTERNAL")
        if not boundary["valid"]:
            raise ValueError("experience_data_boundary_invalid:" + ",".join(boundary["errors"]))

        subdir = self.EXPERIENCE_DIRS.get(experience_type, "observation")
        exp_path = self.knowledge_dir / subdir / f"{exp_id}.json"
        if exp_path.exists():
            concurrent = self._load_experience(exp_path)
            if (
                not concurrent
                or concurrent.source_task_id != task.task_id
                or concurrent.experience_type != experience_type
            ):
                raise RuntimeError(f"experience_identity_collision:{exp_id}")
            return concurrent

        try:
            self._persist_experience(exp, exp_path)
        except FileExistsError:
            concurrent = self._load_experience(exp_path)
            if (
                not concurrent
                or concurrent.source_task_id != task.task_id
                or concurrent.experience_type != experience_type
            ):
                raise RuntimeError(f"experience_identity_collision:{exp_id}")
            return concurrent

        return exp

    def deposit_from_task(self, task, lexicon=None) -> Optional[Experience]:
        """
        根据 Guardian 判决自动选择经验类型并沉积

        guardian_decision 映射：
          axiom → axiom
          constraint → constraint
          experience → pattern
          discard → lesson
        """
        decision = task.guardian_decision or "observation"

        type_map = {
            "axiom": "axiom",
            "constraint": "constraint",
            "experience": "pattern",
            "discard": "lesson",
        }
        exp_type = type_map.get(decision, "observation")

        related = []
        if lexicon:
            for kw in task.title.split()[:5]:
                kw = kw.strip()
                if len(kw) >= 2:
                    c = lexicon.get_concept(kw)
                    if c:
                        related.append(c["name"])

        constraints = []
        if exp_type == "constraint":
            constraints.append(f"来自任务: {task.task_id}")
            if task.hypothesis:
                constraints.append(task.hypothesis)

        return self.deposit(
            task=task,
            experience_type=exp_type,
            constraints_updated=constraints,
            related_concepts=related,
        )

    def get_all(self, experience_type: Optional[str] = None, limit: int = 50) -> List[Experience]:
        """获取所有经验记录"""
        experiences = []
        types_to_check = [experience_type] if experience_type else list(self.EXPERIENCE_DIRS.keys())

        for etype in types_to_check:
            subdir = self.EXPERIENCE_DIRS.get(etype, "observation")
            exp_dir = self.knowledge_dir / subdir
            if not exp_dir.exists():
                continue
            for fpath in exp_dir.glob("EXP-*.json"):
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    experiences.append(Experience.from_dict(data))
                except Exception:
                    pass

        experiences.sort(key=lambda e: e.reference_count, reverse=True)
        return experiences[:limit]

    def find_related(self, keyword: str, limit: int = 10) -> List[Experience]:
        """根据关键词查找相关经验"""
        all_exp = self.get_all(limit=200)
        results = []
        kw = keyword.lower()
        for exp in all_exp:
            score = 0
            if kw in exp.conclusion.lower():
                score += 3
            if kw in exp.source_task_id.lower():
                score += 2
            for tag in exp.tags:
                if kw in tag.lower():
                    score += 1
            if score > 0:
                exp.touch()
                results.append((score, exp))
        results.sort(key=lambda x: -x[0])
        selected = [e for _, e in results[:limit]]
        # Reuse is the only thing that turns a stored record into knowledge ACE
        # actually kept.  Persist the reference so a later audit can prove the
        # loop closed instead of inferring it from a file count.
        for exp in selected:
            self._record_reuse(exp)
        return selected

    def _record_reuse(self, experience: Experience) -> None:
        """Persist reference_count/last_used_at for a reused experience."""
        index = self._load_index()
        path_text = ""
        for record in index.values():
            if isinstance(record, dict) and record.get("source_task") == experience.source_task_id:
                if record.get("type") == experience.experience_type:
                    path_text = str(record.get("path", ""))
                    break
        if not path_text:
            subdir = self.EXPERIENCE_DIRS.get(experience.experience_type, "observation")
            candidate = self.knowledge_dir / subdir / f"{experience.experience_id}.json"
            path_text = str(candidate) if candidate.is_file() else ""
        if not path_text:
            return
        try:
            self._persist_experience(experience, Path(path_text))
        except OSError:
            # A reuse counter must never break the research path that reused it.
            return

    def get_stats(self) -> Dict[str, Any]:
        """获取经验库统计"""
        stats = {}
        total = 0
        for etype, subdir in self.EXPERIENCE_DIRS.items():
            count = len(list((self.knowledge_dir / subdir).glob("EXP-*.json")))
            stats[etype] = count
            total += count
        return {"total": total, "by_type": stats}
