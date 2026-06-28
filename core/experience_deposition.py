"""
经验沉积系统 — 任务完成后的知识沉淀

每当任务从 approved/ 进入 archived/ 时，自动生成一条经验记录。

经验记录不独立存在，必须关联到：
  - 来源任务
  - 证据
  - 约束更新（如果有）
  - 词库概念（如果有）

经验分类：
  - axiom: 公理（证据充分，无反例）
  - constraint: 约束（系统必须遵守的规则）
  - pattern: 模式（反复出现的结构）
  - lesson: 教训（失败或被废弃的经验）
  - observation: 观察（弱结论，供参考）
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional


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
    ):
        self.experience_id = experience_id
        self.source_task_id = source_task_id
        self.experience_type = experience_type if experience_type in self.EXPERIENCE_TYPES else "observation"
        self.conclusion = conclusion
        self.evidence = evidence
        self.constraints_updated = constraints_updated
        self.related_concepts = related_concepts
        self.tags = tags or []
        self.created_at = created_at or datetime.now().isoformat()
        self.reference_count = 0
        self.last_used_at = self.created_at

    def to_dict(self) -> Dict[str, Any]:
        return {
            "experience_id": self.experience_id,
            "source_task_id": self.source_task_id,
            "experience_type": self.experience_type,
            "conclusion": self.conclusion,
            "evidence": self.evidence,
            "constraints_updated": self.constraints_updated,
            "related_concepts": self.related_concepts,
            "tags": self.tags,
            "created_at": self.created_at,
            "reference_count": self.reference_count,
            "last_used_at": self.last_used_at,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "Experience":
        return cls(**data)

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
        """
        if experience_type is None:
            if task.guardian_decision in Experience.EXPERIENCE_TYPES:
                experience_type = task.guardian_decision
            else:
                experience_type = "observation"

        exp_id = f"EXP-{datetime.now().strftime('%Y%m%d%H%M%S')}"

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
            conclusion=conclusion or task.hypothesis or task.title,
            evidence=evidence,
            constraints_updated=constraints_updated or [],
            related_concepts=related_concepts or [],
            tags=task.tags + [experience_type],
        )

        subdir = self.EXPERIENCE_DIRS.get(experience_type, "observation")
        exp_path = self.knowledge_dir / subdir / f"{exp_id}.json"
        with open(exp_path, "w", encoding="utf-8") as f:
            json.dump(exp.to_dict(), f, ensure_ascii=False, indent=2)

        index = self._load_index()
        index[exp_id] = {
            "path": str(exp_path),
            "type": experience_type,
            "conclusion": exp.conclusion[:100],
            "source_task": task.task_id,
        }
        self._save_index(index)

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
        return [e for _, e in results[:limit]]

    def get_stats(self) -> Dict[str, Any]:
        """获取经验库统计"""
        stats = {}
        total = 0
        for etype, subdir in self.EXPERIENCE_DIRS.items():
            count = len(list((self.knowledge_dir / subdir).glob("EXP-*.json")))
            stats[etype] = count
            total += count
        return {"total": total, "by_type": stats}
