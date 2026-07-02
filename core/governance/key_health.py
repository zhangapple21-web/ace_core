"""
Key Health（Key 健康度）

核心职责：
    每个 Key 都有自己的健康档案。
    不再是随机轮询，而是根据健康度调度。

    每个 Key 跟踪：
        - success_count: 成功次数
        - failure_count: 失败次数
        - success_rate: 成功率
        - avg_latency: 平均延迟
        - last_success: 最后成功时间
        - last_failure: 最后失败时间
        - last_failure_reason: 最后失败原因
        - failure_streak: 连续失败次数
        - health_score: 健康评分（0~100）
        - quota_remaining: 剩余额度（如果可获取）

    设计原则：
        - 每个 Key 独立统计
        - 连续失败自动降级
        - 成功率越高，权重越高
        - 证据可追溯
"""

import json
import logging
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class KeyHealthRecord:
    """单个 Key 的健康记录"""
    key_id: str                  # Key 标识符（不存完整 key，只存前缀+hash）
    provider: str                # 所属 Provider
    key_prefix: str = ""         # Key 前缀（用于展示）
    success_count: int = 0       # 成功次数
    failure_count: int = 0       # 失败次数
    total_requests: int = 0      # 总请求数
    success_rate: float = 0.0    # 成功率
    avg_latency_ms: float = 0.0  # 平均延迟
    p50_latency_ms: float = 0.0  # P50 延迟
    p95_latency_ms: float = 0.0  # P95 延迟
    last_success: str = ""       # 最后成功时间
    last_failure: str = ""       # 最后失败时间
    last_failure_reason: str = ""  # 最后失败原因
    failure_streak: int = 0      # 连续失败次数
    health_score: float = 100.0  # 健康评分（0~100）
    status: str = "healthy"      # healthy / degraded / unhealthy / suspended
    latencies: List[int] = field(default_factory=list)  # 最近延迟样本
    failure_reasons: Dict[str, int] = field(default_factory=dict)  # 失败原因分布
    first_seen: str = ""         # 首次出现时间
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key_id": self.key_id,
            "provider": self.provider,
            "key_prefix": self.key_prefix,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "total_requests": self.total_requests,
            "success_rate": round(self.success_rate, 2),
            "avg_latency_ms": round(self.avg_latency_ms, 1),
            "p50_latency_ms": round(self.p50_latency_ms, 1),
            "p95_latency_ms": round(self.p95_latency_ms, 1),
            "last_success": self.last_success,
            "last_failure": self.last_failure,
            "last_failure_reason": self.last_failure_reason,
            "failure_streak": self.failure_streak,
            "health_score": round(self.health_score, 1),
            "status": self.status,
            "first_seen": self.first_seen,
            "failure_reasons": self.failure_reasons,
            "meta": self.meta,
        }


class KeyHealthManager:
    """
    Key 健康度管理器

    负责跟踪和评估每个 Key 的健康状态。
    """

    def __init__(self, data_dir: str):
        self.data_dir = Path(data_dir)
        self.health_dir = self.data_dir / "key_health"
        self.health_dir.mkdir(parents=True, exist_ok=True)
        self.records_file = self.health_dir / "key_health.jsonl"
        self._index_file = self.health_dir / "index.json"

        self._records: Dict[str, KeyHealthRecord] = {}
        self._load()

    def _load(self):
        """加载健康记录"""
        if not self.records_file.exists():
            return

        # 只加载每个 key_id 的最新一条（因为是 append-only）
        latest = {}
        try:
            with open(self.records_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        data = json.loads(line.strip())
                        key_id = data["key_id"]
                        latest[key_id] = data
                    except Exception:
                        continue

            for key_id, data in latest.items():
                record = KeyHealthRecord(
                    key_id=data["key_id"],
                    provider=data.get("provider", ""),
                    key_prefix=data.get("key_prefix", ""),
                    success_count=data.get("success_count", 0),
                    failure_count=data.get("failure_count", 0),
                    total_requests=data.get("total_requests", 0),
                    success_rate=data.get("success_rate", 0.0),
                    avg_latency_ms=data.get("avg_latency_ms", 0.0),
                    p50_latency_ms=data.get("p50_latency_ms", 0.0),
                    p95_latency_ms=data.get("p95_latency_ms", 0.0),
                    last_success=data.get("last_success", ""),
                    last_failure=data.get("last_failure", ""),
                    last_failure_reason=data.get("last_failure_reason", ""),
                    failure_streak=data.get("failure_streak", 0),
                    health_score=data.get("health_score", 100.0),
                    status=data.get("status", "healthy"),
                    failure_reasons=data.get("failure_reasons", {}),
                    first_seen=data.get("first_seen", ""),
                    meta=data.get("meta", {}),
                )
                self._records[key_id] = record

            logger.info(f"加载了 {len(self._records)} 个 Key 的健康记录")
        except Exception as e:
            logger.error(f"加载 Key 健康记录失败: {e}")

    def _save(self, record: KeyHealthRecord):
        """追加保存一条记录"""
        try:
            with open(self.records_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"保存 Key 健康记录失败: {e}")

    def _key_id(self, api_key: str, provider: str) -> str:
        """生成 Key 标识符（不存完整 key）"""
        import hashlib
        raw = f"{provider}:{api_key[:8]}:{len(api_key)}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()[:10]

    def _update_health_score(self, record: KeyHealthRecord):
        """计算健康评分"""
        if record.total_requests == 0:
            record.health_score = 100.0
            record.status = "healthy"
            return

        # 基础分 = 成功率 * 100
        score = record.success_rate * 100

        # 连续失败惩罚
        if record.failure_streak >= 3:
            score -= (record.failure_streak - 2) * 10

        # 延迟惩罚（超过 10s 开始扣分）
        if record.avg_latency_ms > 10000:
            score -= min(20, (record.avg_latency_ms - 10000) / 1000)

        score = max(0.0, min(100.0, score))
        record.health_score = score

        # 状态判定
        if record.failure_streak >= 5 or score < 20:
            record.status = "suspended"
        elif record.failure_streak >= 2 or score < 60:
            record.status = "unhealthy"
        elif record.success_rate < 0.8 or score < 80:
            record.status = "degraded"
        else:
            record.status = "healthy"

    def record_success(self, provider: str, api_key: str, latency_ms: int):
        """记录一次成功"""
        key_id = self._key_id(api_key, provider)

        if key_id not in self._records:
            now = datetime.now().isoformat()
            self._records[key_id] = KeyHealthRecord(
                key_id=key_id,
                provider=provider,
                key_prefix=api_key[:10] + "..." if len(api_key) > 10 else api_key,
                first_seen=now,
            )

        record = self._records[key_id]
        now = datetime.now().isoformat()

        record.success_count += 1
        record.total_requests += 1
        record.failure_streak = 0
        record.last_success = now

        # 更新延迟统计（保留最近 100 个样本）
        record.latencies.append(latency_ms)
        if len(record.latencies) > 100:
            record.latencies = record.latencies[-100:]

        if record.latencies:
            record.avg_latency_ms = statistics.mean(record.latencies)
            sorted_lats = sorted(record.latencies)
            record.p50_latency_ms = sorted_lats[len(sorted_lats) // 2]
            p95_idx = int(len(sorted_lats) * 0.95)
            record.p95_latency_ms = sorted_lats[min(p95_idx, len(sorted_lats) - 1)]

        # 更新成功率
        if record.total_requests > 0:
            record.success_rate = record.success_count / record.total_requests

        self._update_health_score(record)
        self._save(record)

        return record

    def record_failure(self, provider: str, api_key: str,
                       latency_ms: int, reason: str = ""):
        """记录一次失败"""
        key_id = self._key_id(api_key, provider)

        if key_id not in self._records:
            now = datetime.now().isoformat()
            self._records[key_id] = KeyHealthRecord(
                key_id=key_id,
                provider=provider,
                key_prefix=api_key[:10] + "..." if len(api_key) > 10 else api_key,
                first_seen=now,
            )

        record = self._records[key_id]
        now = datetime.now().isoformat()

        record.failure_count += 1
        record.total_requests += 1
        record.failure_streak += 1
        record.last_failure = now
        record.last_failure_reason = reason[:100] if reason else ""

        # 失败原因统计
        if reason:
            short_reason = reason[:50]
            record.failure_reasons[short_reason] = record.failure_reasons.get(short_reason, 0) + 1

        # 更新成功率
        if record.total_requests > 0:
            record.success_rate = record.success_count / record.total_requests

        self._update_health_score(record)
        self._save(record)

        return record

    def get_key_health(self, provider: str, api_key: str) -> Optional[KeyHealthRecord]:
        """获取指定 Key 的健康状态"""
        key_id = self._key_id(api_key, provider)
        return self._records.get(key_id)

    def get_provider_keys(self, provider: str) -> List[KeyHealthRecord]:
        """获取某个 Provider 的所有 Key 健康记录"""
        return [r for r in self._records.values() if r.provider == provider]

    def get_sorted_keys(self, provider: str = None,
                        min_health: float = 0) -> List[KeyHealthRecord]:
        """
        按健康度排序的 Key 列表

        Args:
            provider: 可选，按 Provider 过滤
            min_health: 最小健康分

        Returns:
            按健康度降序排列的 Key 记录
        """
        records = list(self._records.values())
        if provider:
            records = [r for r in records if r.provider == provider]
        if min_health > 0:
            records = [r for r in records if r.health_score >= min_health]

        records.sort(key=lambda r: r.health_score, reverse=True)
        return records

    def get_health_summary(self, provider: str = None) -> Dict[str, Any]:
        """获取健康度摘要"""
        records = list(self._records.values())
        if provider:
            records = [r for r in records if r.provider == provider]

        if not records:
            return {"total_keys": 0, "avg_health": 0.0}

        avg_health = sum(r.health_score for r in records) / len(records)
        by_status = {}
        for r in records:
            by_status[r.status] = by_status.get(r.status, 0) + 1

        total_requests = sum(r.total_requests for r in records)
        total_success = sum(r.success_count for r in records)
        total_failure = sum(r.failure_count for r in records)
        overall_success_rate = total_success / total_requests if total_requests > 0 else 0.0

        return {
            "total_keys": len(records),
            "avg_health": round(avg_health, 1),
            "by_status": by_status,
            "total_requests": total_requests,
            "total_success": total_success,
            "total_failure": total_failure,
            "overall_success_rate": round(overall_success_rate * 100, 1),
        }

    def generate_markdown_report(self) -> str:
        """生成 Markdown 格式的 Key 健康报告"""
        summary = self.get_health_summary()
        all_keys = self.get_sorted_keys()

        lines = []
        lines.append("# Key Health Report")
        lines.append("")
        lines.append(f"**生成时间**: {datetime.now().isoformat()}")
        lines.append("")

        # 摘要
        lines.append("## 总体摘要")
        lines.append("")
        lines.append(f"| 指标 | 值 |")
        lines.append(f"|------|-----|")
        lines.append(f"| Key 总数 | {summary['total_keys']} |")
        lines.append(f"| 平均健康度 | {summary['avg_health']}% |")
        lines.append(f"| 总请求数 | {summary['total_requests']} |")
        lines.append(f"| 总成功率 | {summary['overall_success_rate']}% |")
        lines.append(f"| healthy | {summary['by_status'].get('healthy', 0)} |")
        lines.append(f"| degraded | {summary['by_status'].get('degraded', 0)} |")
        lines.append(f"| unhealthy | {summary['by_status'].get('unhealthy', 0)} |")
        lines.append(f"| suspended | {summary['by_status'].get('suspended', 0)} |")
        lines.append("")

        # Key 列表
        lines.append("## Key 列表（按健康度排序）")
        lines.append("")
        lines.append("| # | Provider | Key 前缀 | 健康度 | 状态 | 成功率 | 平均延迟 | 连续失败 |")
        lines.append("|---|----------|----------|--------|------|--------|----------|----------|")

        for i, k in enumerate(all_keys[:20], 1):
            status_icon = {
                "healthy": "🟢",
                "degraded": "🟡",
                "unhealthy": "🟠",
                "suspended": "🔴",
            }.get(k.status, "⚪")
            lines.append(
                f"| {i} | {k.provider} | `{k.key_prefix}` | "
                f"{k.health_score:.0f}% | {status_icon} {k.status} | "
                f"{k.success_rate*100:.0f}% | {k.avg_latency_ms:.0f}ms | "
                f"{k.failure_streak} |"
            )

        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("> **每个 Key 都有独立的健康档案，调度时优先选择健康的 Key。**")

        return "\n".join(lines)
