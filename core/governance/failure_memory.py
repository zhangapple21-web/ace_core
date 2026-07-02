"""
Failure Memory（故障记忆）

核心职责：
    记住所有发生过的故障。
    让 Runtime 长记性，遇到同样的错误，
    直接从记忆里取答案，而不是每次重新调查。

    每条故障记忆包含：
        - signature: 故障签名（可复用的识别特征）
        - first_seen: 首次发现时间
        - last_seen: 最后一次出现时间
        - occurrence_count: 出现次数
        - classification: 故障分类（来自 FailureTaxonomy）
        - evidence: 证据链
        - root_cause: 根因（如果已确认）
        - fix: 修复方案（如果已知）
        - status: open / investigating / fixed / permanent

    设计原则：
        - Append-only: 只追加，不删除
        - Evidence First: 每个故障都必须有证据
        - Semantic Dedup: 相同故障自动合并计数
        - Lineage Track: 可追溯故障演化历史
"""

import json
import hashlib
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

from core.governance.failure_taxonomy import FailureTaxonomy, FailureClassification

logger = logging.getLogger(__name__)


@dataclass
class FailureRecord:
    """故障记录"""
    failure_id: str              # 故障唯一 ID
    signature: str               # 故障签名（用于去重）
    category: str                # 故障大类
    code: str                    # 故障代码
    first_seen: str              # 首次发现时间
    last_seen: str               # 最后一次出现时间
    occurrence_count: int = 1    # 出现次数
    severity: str = "warning"    # critical / warning / info
    status: str = "investigating"  # open / investigating / fixed / permanent
    root_cause: str = ""         # 根因
    fix: str = ""                # 修复方案
    actionable: bool = False     # 是否可行动
    evidence: List[Dict] = field(default_factory=list)  # 证据链
    affected_providers: List[str] = field(default_factory=list)  # 受影响的 Provider
    affected_models: List[str] = field(default_factory=list)    # 受影响的模型
    meta: Dict[str, Any] = field(default_factory=dict)  # 元数据


class FailureMemory:
    """
    故障记忆库

    核心能力：
        1. 记录故障，自动去重（按签名）
        2. 按分类/严重程度/状态查询
        3. 已知故障快速识别
        4. 故障演化历史追踪
    """

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.memory_dir = self.data_dir / "failure_memory"
        self.memory_dir.mkdir(parents=True, exist_ok=True)

        self.failures_file = self.memory_dir / "failures.jsonl"
        self._index_file = self.memory_dir / "index.json"

        self._failures: Dict[str, FailureRecord] = {}
        self._load()

    def _load(self):
        """加载故障记忆"""
        if not self.failures_file.exists():
            return

        try:
            with open(self.failures_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        data = json.loads(line.strip())
                        record = FailureRecord(
                            failure_id=data["failure_id"],
                            signature=data["signature"],
                            category=data["category"],
                            code=data["code"],
                            first_seen=data["first_seen"],
                            last_seen=data["last_seen"],
                            occurrence_count=data.get("occurrence_count", 1),
                            severity=data.get("severity", "warning"),
                            status=data.get("status", "investigating"),
                            root_cause=data.get("root_cause", ""),
                            fix=data.get("fix", ""),
                            actionable=data.get("actionable", False),
                            evidence=data.get("evidence", []),
                            affected_providers=data.get("affected_providers", []),
                            affected_models=data.get("affected_models", []),
                            meta=data.get("meta", {}),
                        )
                        self._failures[record.failure_id] = record
                    except Exception:
                        continue
            logger.info(f"加载了 {len(self._failures)} 条故障记忆")
        except Exception as e:
            logger.error(f"加载故障记忆失败: {e}")

    def _save(self, record: FailureRecord):
        """追加保存一条故障记录"""
        try:
            with open(self.failures_file, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "failure_id": record.failure_id,
                    "signature": record.signature,
                    "category": record.category,
                    "code": record.code,
                    "first_seen": record.first_seen,
                    "last_seen": record.last_seen,
                    "occurrence_count": record.occurrence_count,
                    "severity": record.severity,
                    "status": record.status,
                    "root_cause": record.root_cause,
                    "fix": record.fix,
                    "actionable": record.actionable,
                    "evidence": record.evidence[-5:],  # 只存最近 5 条证据
                    "affected_providers": record.affected_providers,
                    "affected_models": record.affected_models,
                    "meta": record.meta,
                }, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"保存故障记忆失败: {e}")

    def _make_signature(self, classification: FailureClassification,
                        provider: str = "", model: str = "") -> str:
        """
        生成故障签名

        签名规则：
            同一 Provider + 同一故障代码 + 同一模型 = 同一故障
            跨 Provider 的同一故障代码 = 不同故障（因为可能原因不同）
        """
        raw = f"{provider}:{classification.code}:{model}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]

    def record_failure(self, classification: FailureClassification,
                       provider: str = "",
                       model: str = "",
                       evidence: Dict = None) -> FailureRecord:
        """
        记录一条故障

        如果是已知故障，增加计数并更新时间。
        如果是新故障，创建记录。

        Args:
            classification: 故障分类
            provider: 受影响的 Provider
            model: 受影响的模型
            evidence: 证据

        Returns:
            FailureRecord
        """
        signature = self._make_signature(classification, provider, model)
        failure_id = f"FAIL-{signature}"

        now = datetime.now().isoformat()

        if failure_id in self._failures:
            # 已知故障，更新
            record = self._failures[failure_id]
            record.occurrence_count += 1
            record.last_seen = now

            if provider and provider not in record.affected_providers:
                record.affected_providers.append(provider)
            if model and model not in record.affected_models:
                record.affected_models.append(model)

            if evidence:
                record.evidence.append(evidence)
                if len(record.evidence) > 20:
                    record.evidence = record.evidence[-20:]
        else:
            # 新故障
            record = FailureRecord(
                failure_id=failure_id,
                signature=signature,
                category=classification.category,
                code=classification.code,
                first_seen=now,
                last_seen=now,
                occurrence_count=1,
                severity=classification.severity,
                status="open",
                root_cause="",
                fix=classification.recommended_fix,
                actionable=classification.actionable,
                evidence=[evidence] if evidence else [],
                affected_providers=[provider] if provider else [],
                affected_models=[model] if model else [],
                meta={
                    "http_status": classification.http_status,
                    "raw_error": classification.raw_error[:200],
                },
            )
            self._failures[failure_id] = record

        self._save(record)
        return record

    def is_known_failure(self, classification: FailureClassification,
                         provider: str = "", model: str = "") -> Optional[FailureRecord]:
        """
        检查是否为已知故障

        Returns:
            如果已知，返回 FailureRecord；否则返回 None
        """
        signature = self._make_signature(classification, provider, model)
        failure_id = f"FAIL-{signature}"
        return self._failures.get(failure_id)

    def get_failure(self, failure_id: str) -> Optional[FailureRecord]:
        """根据 ID 获取故障记录"""
        return self._failures.get(failure_id)

    def get_all_failures(self, category: str = None,
                         severity: str = None,
                         status: str = None) -> List[FailureRecord]:
        """
        获取故障列表，可按条件过滤

        Args:
            category: 故障大类
            severity: 严重程度
            status: 状态

        Returns:
            故障记录列表（按最后出现时间倒序）
        """
        records = list(self._failures.values())

        if category:
            records = [r for r in records if r.category == category]
        if severity:
            records = [r for r in records if r.severity == severity]
        if status:
            records = [r for r in records if r.status == status]

        records.sort(key=lambda r: r.last_seen, reverse=True)
        return records

    def get_failure_stats(self) -> Dict[str, Any]:
        """获取故障统计"""
        total = len(self._failures)
        by_category = {}
        by_severity = {}
        by_status = {}

        for record in self._failures.values():
            by_category[record.category] = by_category.get(record.category, 0) + 1
            by_severity[record.severity] = by_severity.get(record.severity, 0) + 1
            by_status[record.status] = by_status.get(record.status, 0) + 1

        total_occurrences = sum(r.occurrence_count for r in self._failures.values())

        return {
            "total_failures": total,
            "total_occurrences": total_occurrences,
            "by_category": by_category,
            "by_severity": by_severity,
            "by_status": by_status,
            "open_count": by_status.get("open", 0),
            "investigating_count": by_status.get("investigating", 0),
            "fixed_count": by_status.get("fixed", 0),
            "critical_count": by_severity.get("critical", 0),
        }

    def update_failure(self, failure_id: str, **updates) -> Optional[FailureRecord]:
        """
        更新故障状态

        Args:
            failure_id: 故障 ID
            **updates: 要更新的字段（status, root_cause, fix 等）

        Returns:
            更新后的 FailureRecord
        """
        record = self._failures.get(failure_id)
        if not record:
            return None

        for key, value in updates.items():
            if hasattr(record, key):
                setattr(record, key, value)

        record.last_seen = datetime.now().isoformat()
        self._save(record)
        return record

    def generate_markdown_report(self) -> str:
        """生成 Markdown 格式的故障记忆报告"""
        stats = self.get_failure_stats()
        all_failures = self.get_all_failures()

        lines = []
        lines.append("# Failure Memory Report")
        lines.append("")
        lines.append(f"**生成时间**: {datetime.now().isoformat()}")
        lines.append("")

        # 统计概览
        lines.append("## 故障统计")
        lines.append("")
        lines.append(f"| 指标 | 值 |")
        lines.append(f"|------|-----|")
        lines.append(f"| 故障种类 | {stats['total_failures']} |")
        lines.append(f"| 总发生次数 | {stats['total_occurrences']} |")
        lines.append(f"| 关键故障 | {stats['critical_count']} |")
        lines.append(f"| 未修复 | {stats['open_count'] + stats['investigating_count']} |")
        lines.append(f"| 已修复 | {stats['fixed_count']} |")
        lines.append("")

        # 按分类
        lines.append("### 按分类")
        lines.append("")
        for cat, count in stats["by_category"].items():
            cat_name = FailureTaxonomy.get_all_categories().get(cat, cat)
            lines.append(f"- **{cat_name}**: {count} 种")
        lines.append("")

        # 故障列表
        lines.append("## 故障列表")
        lines.append("")
        lines.append("| 状态 | 严重度 | 故障代码 | 分类 | 次数 | 首次 | 最后 |")
        lines.append("|------|--------|----------|------|------|------|------|")

        for f in all_failures[:20]:
            status_icon = {"open": "🔴", "investigating": "🟡",
                          "fixed": "✅", "permanent": "⚫"}.get(f.status, "❓")
            sev_icon = {"critical": "🔴", "warning": "🟡", "info": "🟢"}.get(f.severity, "⚪")
            lines.append(
                f"| {status_icon} {f.status} | {sev_icon} {f.severity} | "
                f"{f.code} | {f.category} | {f.occurrence_count} | "
                f"{f.first_seen[:10]} | {f.last_seen[:10]} |"
            )

        lines.append("")
        lines.append("> **让 Runtime 长记性，遇到同样的错误，直接从记忆里取答案。**")

        return "\n".join(lines)
