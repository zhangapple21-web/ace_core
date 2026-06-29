"""
Evidence Registry（证据登记处）

核心职责：
    Evidence 本身是独立的对象，不是知识的附属字段。

    很多知识共用同一个 Evidence。

证据属性：
    - id: 唯一标识
    - source: 来源（文件/URL/对话/观察）
    - content: 证据内容
    - confidence: 证据本身的置信度
    - timestamp: 证据产生时间
    - hash: 内容哈希（防篡改）
    - author: 证据提供者
    - references: 引用此证据的知识列表

设计原则：
    - 证据独立存储，知识只引用证据ID
    - 证据有自己的置信度，和知识的置信度分开
    - 一个证据可以被多个知识引用
    - 证据不可删除，只能标记为失效
"""

import json
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class Evidence:
    """证据对象"""
    id: str
    source: str           # 来源类型: file/url/dialog/observation/experiment
    content: str          # 证据内容
    confidence: float = 1.0  # 证据本身的置信度
    timestamp: str = ""     # 证据产生时间
    hash: str = ""          # 内容哈希
    author: str = ""        # 证据提供者
    source_location: str = ""  # 来源位置（文件路径/URL）
    referenced_by: List[str] = field(default_factory=list)  # 引用此证据的知识ID列表
    is_active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


class EvidenceRegistry:
    """
    证据登记处

    核心能力：
        - 注册新证据
        - 查询证据
        - 管理证据引用
        - 验证证据完整性
    """

    def __init__(self, data_dir: str):
        """
        初始化证据登记处

        Args:
            data_dir: 数据存储目录
        """
        self.data_dir = Path(data_dir)
        self.evidence_dir = self.data_dir / "evidence"
        self.evidence_dir.mkdir(parents=True, exist_ok=True)

        self.registry_file = self.evidence_dir / "evidence_registry.jsonl"
        self.evidences: Dict[str, Evidence] = {}

        # 加载已有证据
        self._load_evidences()

    def _load_evidences(self):
        """加载已有证据"""
        if not self.registry_file.exists():
            return

        try:
            with open(self.registry_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        data = json.loads(line.strip())
                        evidence = Evidence(
                            id=data["id"],
                            source=data["source"],
                            content=data["content"],
                            confidence=data.get("confidence", 1.0),
                            timestamp=data.get("timestamp", ""),
                            hash=data.get("hash", ""),
                            author=data.get("author", ""),
                            source_location=data.get("source_location", ""),
                            referenced_by=data.get("referenced_by", []),
                            is_active=data.get("is_active", True),
                            metadata=data.get("metadata", {}),
                        )
                        self.evidences[evidence.id] = evidence
                    except Exception:
                        continue
            logger.info(f"加载了 {len(self.evidences)} 个证据")
        except Exception as e:
            logger.error(f"加载证据失败: {e}")

    def register(
        self,
        source: str,
        content: str,
        confidence: float = 1.0,
        author: str = "",
        source_location: str = "",
        metadata: Dict[str, Any] = None
    ) -> Evidence:
        """
        注册新证据

        Args:
            source: 来源类型
            content: 证据内容
            confidence: 证据置信度
            author: 提供者
            source_location: 来源位置
            metadata: 元数据

        Returns:
            注册的证据对象
        """
        if metadata is None:
            metadata = {}

        # 计算内容哈希
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()

        # 检查是否已存在相同内容的证据
        for existing in self.evidences.values():
            if existing.hash == content_hash and existing.is_active:
                logger.info(f"证据已存在: {existing.id}")
                return existing

        # 生成ID
        evidence_id = f"EVI-{datetime.now().strftime('%Y%m%d%H%M%S')}-{len(self.evidences) + 1:04d}"

        evidence = Evidence(
            id=evidence_id,
            source=source,
            content=content,
            confidence=confidence,
            timestamp=datetime.now().isoformat(),
            hash=content_hash,
            author=author,
            source_location=source_location,
            metadata=metadata,
        )

        self.evidences[evidence_id] = evidence
        self._save_evidence(evidence)

        logger.info(f"注册新证据: {evidence_id}")
        return evidence

    def _save_evidence(self, evidence: Evidence):
        """保存证据到文件"""
        try:
            with open(self.registry_file, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "id": evidence.id,
                    "source": evidence.source,
                    "content": evidence.content,
                    "confidence": evidence.confidence,
                    "timestamp": evidence.timestamp,
                    "hash": evidence.hash,
                    "author": evidence.author,
                    "source_location": evidence.source_location,
                    "referenced_by": evidence.referenced_by,
                    "is_active": evidence.is_active,
                    "metadata": evidence.metadata,
                }, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"保存证据失败: {e}")

    def get(self, evidence_id: str) -> Optional[Evidence]:
        """获取证据"""
        return self.evidences.get(evidence_id)

    def get_by_content(self, content: str) -> Optional[Evidence]:
        """根据内容查找证据"""
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        for evidence in self.evidences.values():
            if evidence.hash == content_hash and evidence.is_active:
                return evidence
        return None

    def add_reference(self, evidence_id: str, knowledge_id: str) -> bool:
        """
        添加证据引用

        Args:
            evidence_id: 证据ID
            knowledge_id: 引用此证据的知识ID

        Returns:
            是否成功
        """
        evidence = self.evidences.get(evidence_id)
        if not evidence:
            logger.warning(f"证据不存在: {evidence_id}")
            return False

        if knowledge_id not in evidence.referenced_by:
            evidence.referenced_by.append(knowledge_id)
            # append-only: 写入更新
            self._save_evidence(evidence)

        return True

    def validate(self, evidence_id: str) -> Dict[str, Any]:
        """
        验证证据完整性

        Args:
            evidence_id: 证据ID

        Returns:
            验证结果
        """
        evidence = self.evidences.get(evidence_id)
        if not evidence:
            return {"valid": False, "reason": "证据不存在"}

        result = {
            "valid": True,
            "evidence_id": evidence_id,
            "checks": {},
        }

        # 检查哈希是否匹配
        content_hash = hashlib.sha256(evidence.content.encode("utf-8")).hexdigest()
        hash_valid = content_hash == evidence.hash
        result["checks"]["hash_valid"] = hash_valid
        if not hash_valid:
            result["valid"] = False

        # 检查置信度范围
        confidence_valid = 0 <= evidence.confidence <= 1
        result["checks"]["confidence_valid"] = confidence_valid
        if not confidence_valid:
            result["valid"] = False

        # 检查是否有来源
        has_source = bool(evidence.source)
        result["checks"]["has_source"] = has_source

        # 检查是否有时间戳
        has_timestamp = bool(evidence.timestamp)
        result["checks"]["has_timestamp"] = has_timestamp

        # 检查引用数
        reference_count = len(evidence.referenced_by)
        result["reference_count"] = reference_count

        return result

    def deactivate(self, evidence_id: str, reason: str = "") -> bool:
        """
        停用证据（不删除，只标记）

        Args:
            evidence_id: 证据ID
            reason: 停用原因

        Returns:
            是否成功
        """
        evidence = self.evidences.get(evidence_id)
        if not evidence:
            return False

        evidence.is_active = False
        evidence.metadata["deactivation_reason"] = reason
        evidence.metadata["deactivated_at"] = datetime.now().isoformat()

        self._save_evidence(evidence)
        return True

    def search(self, keyword: str, limit: int = 10) -> List[Evidence]:
        """
        搜索证据

        Args:
            keyword: 关键词
            limit: 返回数量限制

        Returns:
            匹配的证据列表
        """
        results = []
        keyword_lower = keyword.lower()

        for evidence in self.evidences.values():
            if not evidence.is_active:
                continue

            # 在内容中搜索
            if keyword_lower in evidence.content.lower():
                results.append(evidence)
                if len(results) >= limit:
                    break

            # 在来源位置中搜索
            elif keyword_lower in evidence.source_location.lower():
                results.append(evidence)
                if len(results) >= limit:
                    break

        return results

    def get_stats(self) -> Dict[str, Any]:
        """获取证据统计"""
        active = sum(1 for e in self.evidences.values() if e.is_active)
        inactive = len(self.evidences) - active

        # 按来源类型统计
        source_types = {}
        for evidence in self.evidences.values():
            if evidence.is_active:
                source_types[evidence.source] = source_types.get(evidence.source, 0) + 1

        # 计算总引用数
        total_references = sum(len(e.referenced_by) for e in self.evidences.values() if e.is_active)
        avg_references = total_references / active if active > 0 else 0

        return {
            "total_evidences": len(self.evidences),
            "active_evidences": active,
            "inactive_evidences": inactive,
            "source_types": source_types,
            "total_references": total_references,
            "avg_references_per_evidence": round(avg_references, 2),
        }

    def get_top_referenced(self, limit: int = 10) -> List[Evidence]:
        """获取被引用最多的证据"""
        active_evidences = [e for e in self.evidences.values() if e.is_active]
        active_evidences.sort(key=lambda e: len(e.referenced_by), reverse=True)
        return active_evidences[:limit]
