"""
二进制感官（Binary Sensor）— ACE 的逆向工程感官层

从 ReVa 和 android-reverse-engineering-skill 考古提取的灵魂骨架：

1. 工具驱动（Tool-Driven）：不是一次性输出所有结果，而是提供一组小工具
   让分析者（人或Agent）按需探索，减少上下文消耗
2. 阶段式工作流（Phase-based Workflow）：指纹 → 依赖检查 → 反编译 →
   结构分析 → 深度分析 → 报告生成，每阶段有明确的输入输出
3. 自动依赖安装（Auto Bootstrap）：缺什么工具自动装，不需要手动配环境
4. 增量改进（Incremental Improvement）：每次分析都改进数据库
   （重命名变量、修正类型、添加注释），越分析越清晰
5. 证据链（Evidence Chain）：所有结论都有地址、字符串、交叉引用等证据

与 ACE 现有系统的关系：
- 类比 DiskScanner（文件系统扫描）→ BinarySensor（二进制结构扫描）
- 类比 Lexicon（文本概念）→ BinaryLexicon（二进制结构模式）
- 类比 LocalArchaeologist（本地考古）→ BinaryArchaeologist（二进制考古）
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..identity import Identity
from ..lexicon import Lexicon
from ..memory_index import MemoryIndex


class BinarySensor:
    """
    二进制感官 — ACE 理解二进制结构的入口

    设计原则（从 ReVa 考古提取）：
    1. 小工具哲学：18+ 个专业工具，每个做一件事
    2. 上下文控制：分页、限制返回数量、按需获取
    3. 证据优先：所有结论都带地址、引用、上下文
    4. 增量改进：分析过程中不断改进数据库（命名、类型、注释）

    阶段工作流（从 android-reverse-engineering-skill 考古提取）：
    - Phase 0: Fingerprint（快速指纹，判断类型和框架）
    - Phase 1: Dependencies（依赖检查和自动安装）
    - Phase 2: Decompile（反编译，多引擎可选）
    - Phase 3: Structure（结构分析：包、类、函数、字符串）
    - Phase 4: Deep Analysis（深度分析：数据流、调用链、加密识别）
    - Phase 5: Report（结构化报告，沉淀到词库）
    """

    def __init__(
        self,
        base_dir: Path,
        identity: Identity,
        lexicon: Lexicon,
        memory_index: MemoryIndex,
    ):
        self.base_dir = base_dir
        self.identity = identity
        self.lexicon = lexicon
        self.memory_index = memory_index

        self.data_dir = base_dir / "06_RUNTIME" / "ace" / "data" / "binary_sense"
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self._providers: Dict[str, "ToolProvider"] = {}
        self._analysis_sessions: Dict[str, Dict[str, Any]] = {}
        self._error_log: List[Dict[str, Any]] = []

        self._register_default_providers()

    def _register_default_providers(self) -> None:
        """注册默认工具提供者"""
        pass

    def register_provider(self, name: str, provider: "ToolProvider") -> None:
        """注册一个工具提供者"""
        self._providers[name] = provider
        provider.register_tools()

    def list_tools(self) -> List[Dict[str, Any]]:
        """列出所有可用工具"""
        tools = []
        for provider_name, provider in self._providers.items():
            for tool in provider.get_tools():
                tool_copy = dict(tool)
                tool_copy["provider"] = provider_name
                tools.append(tool_copy)
        return tools

    def call_tool(self, tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
        """调用一个工具"""
        for provider in self._providers.values():
            result = provider.call_tool(tool_name, args)
            if result.get("success") is not None:
                return result
        return {"success": False, "error": f"Tool not found: {tool_name}"}

    def create_analysis_session(
        self,
        target_path: str,
        session_type: str = "auto",
    ) -> str:
        """
        创建一个分析会话

        来源：ReVa 的 project/program 管理模式
        - 每个目标文件有独立的分析上下文
        - 分析结果增量累积
        - 会话可暂停和恢复
        """
        session_id = str(uuid.uuid4())[:8]
        session = {
            "id": session_id,
            "target_path": target_path,
            "type": session_type,
            "status": "created",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "findings": [],
            "tools_called": 0,
            "phase": 0,
        }
        self._analysis_sessions[session_id] = session
        return session_id

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """获取分析会话"""
        return self._analysis_sessions.get(session_id)

    def update_session(
        self, session_id: str, **updates
    ) -> Optional[Dict[str, Any]]:
        """更新分析会话"""
        if session_id not in self._analysis_sessions:
            return None
        session = self._analysis_sessions[session_id]
        session.update(updates)
        session["updated_at"] = datetime.now().isoformat()
        return session

    def add_finding(
        self,
        session_id: str,
        finding_type: str,
        description: str,
        evidence: Optional[List[Dict[str, Any]]] = None,
        confidence: float = 0.5,
    ) -> None:
        """
        添加发现到会话

        设计原则（从 ReVa deep-analysis skill 考古提取）：
        - 每个发现都必须有证据（地址、字符串、交叉引用）
        - 置信度分级（0-1），证据越充分置信度越高
        - 发现类型标准化：string_pattern、crypto_indicator、network_behavior 等
        """
        if session_id not in self._analysis_sessions:
            return
        finding = {
            "id": str(uuid.uuid4())[:8],
            "type": finding_type,
            "description": description,
            "evidence": evidence or [],
            "confidence": confidence,
            "found_at": datetime.now().isoformat(),
        }
        self._analysis_sessions[session_id]["findings"].append(finding)
        self._analysis_sessions[session_id]["updated_at"] = datetime.now().isoformat()

    def log_error(self, message: str, error: Optional[Exception] = None) -> None:
        """记录错误（不阻塞主循环）"""
        entry = {
            "timestamp": datetime.now().isoformat(),
            "message": message,
            "error": str(error) if error else None,
        }
        self._error_log.insert(0, entry)
        self._error_log = self._error_log[:50]

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        tool_count = sum(len(p.get_tools()) for p in self._providers.values())
        return {
            "providers": len(self._providers),
            "tools": tool_count,
            "active_sessions": len(self._analysis_sessions),
            "errors": len(self._error_log),
        }

    def export_findings(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        导出会话发现，用于沉淀到词库和经验库

        这是 ACE 与其他逆向工具的本质区别：
        - 别人：分析完就完了，结果在报告里
        - ACE：分析完提取结构模式，存入词库，下次遇到相似结构直接识别
        """
        session = self._analysis_sessions.get(session_id)
        if not session:
            return None

        findings = session.get("findings", [])
        patterns = self._extract_patterns(findings)

        return {
            "session_id": session_id,
            "target": session["target_path"],
            "finding_count": len(findings),
            "patterns_extracted": len(patterns),
            "patterns": patterns,
            "exported_at": datetime.now().isoformat(),
        }

    def _extract_patterns(self, findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        从发现中提取可复用的结构模式

        这是二进制感官的核心价值：
        不是记录具体的分析结果，而是提取"结构模式"存入词库
        以后看到相似结构，系统能自动识别
        """
        patterns = []
        finding_types = {}

        for f in findings:
            ftype = f["type"]
            if ftype not in finding_types:
                finding_types[ftype] = []
            finding_types[ftype].append(f)

        for ftype, type_findings in finding_types.items():
            if len(type_findings) >= 2:
                pattern = {
                    "pattern_type": ftype,
                    "occurrence_count": len(type_findings),
                    "avg_confidence": sum(f["confidence"] for f in type_findings) / len(type_findings),
                    "examples": [f["description"][:100] for f in type_findings[:3]],
                    "evidence_types": list(set(
                        e.get("type", "unknown")
                        for f in type_findings
                        for e in f.get("evidence", [])
                    )),
                }
                patterns.append(pattern)

        return patterns
