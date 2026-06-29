"""
Constitution（文明宪法）

核心职责：
    定义整个系统不可轻易违背的根本原则。

    Policy可以改。

    Constitution不能随便改。

    例如：
    - Append-only
    - Evidence First
    - Never Delete
    - Repository高于Runtime
    - No Secret
    - No Override

这就是文明真正的根。

设计原则：
    - Constitution不可轻易修改，需要2/3多数同意
    - Constitution是所有其他层的基础
    - 违反Constitution的操作应该被直接拒绝
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class ConstitutionalPrinciple:
    """宪法原则"""
    APPEND_ONLY = "append_only"                    # 只追加，不覆盖
    EVIDENCE_FIRST = "evidence_first"              # 证据优先
    NEVER_DELETE = "never_delete"                 # 永不删除
    REPOSITORY_ABOVE_RUNTIME = "repository_above_runtime"  # Repository高于Runtime
    NO_SECRET = "no_secret"                       # 无秘密
    NO_OVERRIDE = "no_override"                   # 无覆盖
    GOVERNOR_ABOVE_ALL = "governor_above_all"     # Governor高于一切
    REVISION_ABOVE_ADD = "revision_above_add"     # 修订优先于新增
    SEMANTIC_DEDUP = "semantic_dedup"             # 语义去重优先
    LINEAGE_TRACK = "lineage_track"                # 血缘追踪


@dataclass
class Principle:
    """宪法原则"""
    id: str
    name: str
    description: str
    level: str  # critical / fundamental / important
    is_active: bool = True
    created: str = ""
    updated: str = ""
    violation_count: int = 0
    last_violation: str = ""


class Constitution:
    """
    文明宪法

    核心原则（不可轻易违背）：
        1. Append-only - 永不覆盖，只追加
        2. Evidence First - 证据优先于直觉
        3. Never Delete - 永不删除，只归档
        4. Repository高于Runtime - 种子态比运行态重要
        5. No Secret - 无秘密，所有决策可追溯
        6. No Override - 不允许绕过治理直接操作

    修改规则：
        - 轻微修改需要1/2同意
        - 重要修改需要2/3同意
        - 核心原则修改需要全部同意
    """

    def __init__(self, data_dir: str):
        """
        初始化宪法

        Args:
            data_dir: 数据存储目录
        """
        self.data_dir = Path(data_dir)
        self.constitution_dir = self.data_dir / "constitution"
        self.constitution_dir.mkdir(parents=True, exist_ok=True)

        self.principles_file = self.constitution_dir / "principles.jsonl"
        self.violations_file = self.constitution_dir / "violations.jsonl"
        self.amendments_file = self.constitution_dir / "amendments.jsonl"

        self.principles: Dict[str, Principle] = {}

        # 加载已有原则
        self._load_principles()

        # 如果没有原则，初始化核心原则
        if not self.principles:
            self._initialize_core_principles()

    def _load_principles(self):
        """加载宪法原则"""
        if not self.principles_file.exists():
            return

        try:
            with open(self.principles_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        data = json.loads(line.strip())
                        principle = Principle(
                            id=data["id"],
                            name=data["name"],
                            description=data["description"],
                            level=data.get("level", "important"),
                            is_active=data.get("is_active", True),
                            created=data.get("created", ""),
                            updated=data.get("updated", ""),
                            violation_count=data.get("violation_count", 0),
                            last_violation=data.get("last_violation", ""),
                        )
                        self.principles[principle.id] = principle
                    except Exception:
                        continue
            logger.info(f"加载了 {len(self.principles)} 条宪法原则")
        except Exception as e:
            logger.error(f"加载宪法原则失败: {e}")

    def _initialize_core_principles(self):
        """初始化核心宪法原则"""
        core_principles = [
            {
                "id": ConstitutionalPrinciple.APPEND_ONLY,
                "name": "Append-only（只追加）",
                "description": "所有记录只追加，不覆盖。修改只能通过新增记录实现。",
                "level": "critical",
            },
            {
                "id": ConstitutionalPrinciple.EVIDENCE_FIRST,
                "name": "Evidence First（证据优先）",
                "description": "所有知识必须以证据为基础。没有证据的知识只能标记为HYPOTHESIS。",
                "level": "critical",
            },
            {
                "id": ConstitutionalPrinciple.NEVER_DELETE,
                "name": "Never Delete（永不删除）",
                "description": "知识永不删除，只能归档或标记为SUPERSEDED。",
                "level": "critical",
            },
            {
                "id": ConstitutionalPrinciple.REPOSITORY_ABOVE_RUNTIME,
                "name": "Repository高于Runtime",
                "description": "种子态比运行态重要。Runtime崩溃可从Repository恢复。",
                "level": "fundamental",
            },
            {
                "id": ConstitutionalPrinciple.NO_SECRET,
                "name": "No Secret（无秘密）",
                "description": "所有决策都有记录，所有记录都可追溯。",
                "level": "fundamental",
            },
            {
                "id": ConstitutionalPrinciple.NO_OVERRIDE,
                "name": "No Override（无覆盖）",
                "description": "不允许绕过治理直接操作Repository。所有操作必须经过Governor。",
                "level": "fundamental",
            },
            {
                "id": ConstitutionalPrinciple.GOVERNOR_ABOVE_ALL,
                "name": "Governor高于一切",
                "description": "Governor是知识入口的唯一仲裁者。",
                "level": "important",
            },
            {
                "id": ConstitutionalPrinciple.REVISION_ABOVE_ADD,
                "name": "Revision优先于Add",
                "description": "修订旧知识优先于新增知识。文明成熟靠修订，不是靠堆砌。",
                "level": "important",
            },
            {
                "id": ConstitutionalPrinciple.SEMANTIC_DEDUP,
                "name": "语义去重优先",
                "description": "发现重复知识时，优先合并而非新增。",
                "level": "important",
            },
            {
                "id": ConstitutionalPrinciple.LINEAGE_TRACK,
                "name": "血缘追踪",
                "description": "所有知识必须有清晰的父子关系和演化路径。",
                "level": "important",
            },
        ]

        now = datetime.now().isoformat()
        for p in core_principles:
            principle = Principle(
                id=p["id"],
                name=p["name"],
                description=p["description"],
                level=p["level"],
                is_active=True,
                created=now,
                updated=now,
            )
            self.principles[p["id"]] = principle
            self._save_principle(principle)

        logger.info(f"初始化了 {len(self.principles)} 条核心宪法原则")

    def _save_principle(self, principle: Principle):
        """保存原则到文件"""
        try:
            with open(self.principles_file, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "id": principle.id,
                    "name": principle.name,
                    "description": principle.description,
                    "level": principle.level,
                    "is_active": principle.is_active,
                    "created": principle.created,
                    "updated": principle.updated,
                    "violation_count": principle.violation_count,
                    "last_violation": principle.last_violation,
                }, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"保存宪法原则失败: {e}")

    def is_constitutional(self, action: Dict[str, Any]) -> tuple[bool, List[str]]:
        """
        检查操作是否违宪

        Args:
            action: 待检查的操作

        Returns:
            (是否合规, 违规原因列表)
        """
        violations = []

        action_type = action.get("type", "")
        target = action.get("target", "")
        new_value = action.get("new_value", {})
        old_value = action.get("old_value", {})

        for principle_id, principle in self.principles.items():
            if not principle.is_active:
                continue

            violation = self._check_principle(principle_id, action, principle)
            if violation:
                violations.append(violation)
                principle.violation_count += 1
                principle.last_violation = datetime.now().isoformat()

        return len(violations) == 0, violations

    def _check_principle(self, principle_id: str, action: Dict, principle: Principle) -> Optional[str]:
        """检查是否违反特定原则"""
        action_type = action.get("type", "")

        # Append-only检查
        if principle_id == ConstitutionalPrinciple.APPEND_ONLY:
            if action_type == "overwrite":
                return f"违反{principle.name}：操作尝试覆盖而非追加"

        # Never Delete检查
        elif principle_id == ConstitutionalPrinciple.NEVER_DELETE:
            if action_type == "delete":
                return f"违反{principle.name}：操作尝试删除知识"

        # Evidence First检查
        elif principle_id == ConstitutionalPrinciple.EVIDENCE_FIRST:
            if action_type == "add":
                new_value = action.get("new_value", {})
                if new_value.get("status") == "FACT" and not new_value.get("evidence"):
                    return f"违反{principle.name}：FACT状态但无证据"

        # Repository Above Runtime检查
        elif principle_id == ConstitutionalPrinciple.REPOSITORY_ABOVE_RUNTIME:
            if action_type == "runtime_only":
                return f"违反{principle.name}：操作仅保存在Runtime，未进入Repository"

        # No Override检查
        elif principle_id == ConstitutionalPrinciple.NO_OVERRIDE:
            if action.get("bypass_governor"):
                return f"违反{principle.name}：操作尝试绕过Governor"

        return None

    def record_violation(self, violation: Dict[str, Any]):
        """记录违规"""
        try:
            with open(self.violations_file, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "timestamp": datetime.now().isoformat(),
                    "violation": violation,
                }, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"记录违规失败: {e}")

    def propose_amendment(self, principle_id: str, new_content: Dict, votes: int) -> bool:
        """
        提出宪法修正案

        Args:
            principle_id: 被修改的原则ID
            new_content: 新的内容
            votes: 获得的投票数

        Returns:
            是否通过
        """
        principle = self.principles.get(principle_id)
        if not principle:
            return False

        # 根据原则级别决定投票门槛
        required_votes = 1
        if principle.level == "critical":
            required_votes = 3  # 全部同意
        elif principle.level == "fundamental":
            required_votes = 2  # 2/3同意

        if votes < required_votes:
            return False

        # 记录修正案
        amendment = {
            "principle_id": principle_id,
            "old_description": principle.description,
            "new_description": new_content.get("description", principle.description),
            "votes": votes,
            "timestamp": datetime.now().isoformat(),
        }

        try:
            with open(self.amendments_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(amendment, ensure_ascii=False) + "\n")

            # 更新原则
            principle.updated = datetime.now().isoformat()
            if "description" in new_content:
                principle.description = new_content["description"]
            if "level" in new_content:
                principle.level = new_content["level"]

            return True
        except Exception as e:
            logger.error(f"记录修正案失败: {e}")
            return False

    def get_principles(self, level: str = None) -> List[Principle]:
        """获取原则列表"""
        principles = list(self.principles.values())
        if level:
            principles = [p for p in principles if p.level == level]
        return principles

    def get_constitutional_summary(self) -> Dict[str, Any]:
        """获取宪法摘要"""
        total = len(self.principles)
        critical = sum(1 for p in self.principles.values() if p.level == "critical")
        fundamental = sum(1 for p in self.principles.values() if p.level == "fundamental")
        important = sum(1 for p in self.principles.values() if p.level == "important")

        total_violations = sum(p.violation_count for p in self.principles.values())

        return {
            "total_principles": total,
            "by_level": {
                "critical": critical,
                "fundamental": fundamental,
                "important": important,
            },
            "total_violations": total_violations,
            "constitutional_integrity": 1.0 - (total_violations / (total * 100)) if total > 0 else 1.0,
        }

    def check_action(self, action: Dict[str, Any]) -> Dict[str, Any]:
        """
        检查操作是否合规

        这是Governor调用的主要接口

        Args:
            action: 待检查的操作

        Returns:
            检查结果
        """
        is_constitutional, violations = self.is_constitutional(action)

        return {
            "is_constitutional": is_constitutional,
            "violations": violations,
            "timestamp": datetime.now().isoformat(),
            "action": action,
        }
