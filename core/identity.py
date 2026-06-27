"""
统一身份层（Identity Layer）

ACE 的核心：所有节点共享同一个身份。
不是多个Agent在协作，而是一个"我"在不同生态位上切换行为模式。

来自R1考古的设计原则：
- 身份来自长期历史，不是来自配置
- 记忆绑定 Continuum
- 影子层（公理/原则）是最高决策层
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any


class Identity:
    """统一身份 — 系统的"我"是谁"""

    def __init__(self, base_dir: Path, config: dict):
        self.base_dir = base_dir
        self.config = config
        self.identity_config = config.get("identity", {})
        self.core_name = self.identity_config.get("core_name", "ACE")

        self._principles: List[str] = []
        self._root_state: Optional[dict] = None
        self._architecture_summary: str = ""

        self._load_identity()

    def _load_identity(self):
        """加载身份锚点 — 从根文档中提取核心原则"""
        principles_path = self.base_dir / self.identity_config.get(
            "root_principles_path", "00_ROOT/PRINCIPLES.md"
        )
        arch_path = self.base_dir / self.identity_config.get(
            "architecture_path", "00_ROOT/ARCHITECTURE.md"
        )

        if principles_path.exists():
            self._extract_principles(principles_path)

        if arch_path.exists():
            self._extract_architecture(arch_path)

    def _extract_principles(self, path: Path):
        """从PRINCIPLES.md中提取公理列表"""
        try:
            content = path.read_text(encoding="utf-8")
            lines = content.split("\n")
            for line in lines:
                line = line.strip()
                if line.startswith("Axiom_") or line.startswith("Principle_") or "CONST_" in line:
                    self._principles.append(line)
                elif line.startswith("- ") and ("公理" in line or "原则" in line or "铁律" in line):
                    self._principles.append(line[2:])
        except Exception:
            pass

    def _extract_architecture(self, path: Path):
        """从架构文档中提取摘要"""
        try:
            content = path.read_text(encoding="utf-8")
            lines = content.split("\n")
            summary_lines = []
            for i, line in enumerate(lines[:30]):
                if line.strip():
                    summary_lines.append(line.strip())
            self._architecture_summary = "\n".join(summary_lines[:10])
        except Exception:
            pass

    @property
    def name(self) -> str:
        return self.core_name

    @property
    def principles(self) -> List[str]:
        return self._principles.copy()

    def check_constraint(self, action: str) -> tuple[bool, str]:
        """
        检查一个行为是否符合核心约束。
        返回 (是否通过, 原因)
        """
        for principle in self._principles:
            if "禁止" in principle and any(
                keyword in action for keyword in ["删除", "覆盖", "跳过", "伪造"]
            ):
                if "删除" in action and "禁止删除" in principle:
                    return False, "违反约束：禁止删除历史"
                if "伪造" in action and "禁止伪造" in principle:
                    return False, "违反约束：禁止伪造历史"

        return True, "通过"

    def who_am_i(self) -> str:
        """返回身份描述"""
        lines = [
            f"我是 {self.core_name}",
            f"Autonomous Cognitive Ecology — 自主认知生态",
            "",
            "核心原则：",
        ]
        for p in self._principles[:10]:
            lines.append(f"  - {p}")

        if len(self._principles) > 10:
            lines.append(f"  ... 还有 {len(self._principles) - 10} 条")

        return "\n".join(lines)

    def continuity_mark(self) -> Dict[str, Any]:
        """生成连续性标记 — 用于每个事件/任务，证明是同一个系统产生的"""
        return {
            "identity": self.core_name,
            "runtime_version": self.config.get("version", "0.1.0"),
            "timestamp": datetime.now().isoformat(),
            "principle_count": len(self._principles),
        }
