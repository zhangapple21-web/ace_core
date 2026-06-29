"""
Civilization Status Monitor（文明指标监控器）

职责：
- 每天自动统计文明指标
- 输出 civilization_status.md
- 包含：知识数量/重复率/演化率/废弃率/验证率/假说比例/事实比例/平均证据等级

设计原则：
- append-only：每天生成新报告，不覆盖历史
- 可比较：指标可跨天比较
- 可追溯：每个指标都有计算依据
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class CivilizationStatus:
    """
    文明状态监控器

    核心指标：
    - knowledge_count: 知识总数
    - duplicate_rate: 重复率
    - evolution_rate: 演化率
    - deprecated_rate: 废弃率
    - validated_rate: 验证率
    - hypothesis_ratio: 假说比例
    - fact_ratio: 事实比例
    - avg_confidence: 平均置信度
    """

    def __init__(self, data_dir: str, output_dir: str):
        """
        初始化文明状态监控器

        Args:
            data_dir: 数据目录
            output_dir: 输出目录
        """
        self.data_dir = Path(data_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def compute_status(self) -> Dict[str, Any]:
        """
        计算文明状态指标

        Returns:
            文明状态报告
        """
        now = datetime.now()
        report_date = now.strftime("%Y-%m-%d")

        status = {
            "generated_at": now.isoformat(),
            "report_date": report_date,
            "metrics": {},
            "details": {},
        }

        # 1. 统计经验库
        experiences_stats = self._compute_experiences_stats()
        status["metrics"].update(experiences_stats["metrics"])
        status["details"]["experiences"] = experiences_stats["details"]

        # 2. 统计词库
        lexicon_stats = self._compute_lexicon_stats()
        status["metrics"].update(lexicon_stats["metrics"])
        status["details"]["lexicon"] = lexicon_stats["details"]

        # 3. 统计演化链
        evolution_stats = self._compute_evolution_stats()
        status["metrics"].update(evolution_stats["metrics"])
        status["details"]["evolution"] = evolution_stats["details"]

        # 4. 统计假设
        assumptions_stats = self._compute_assumptions_stats()
        status["metrics"].update(assumptions_stats["metrics"])
        status["details"]["assumptions"] = assumptions_stats["details"]

        # 5. 综合计算
        self._compute_overall(status)

        # 6. 生成报告文件
        self._generate_report_file(status)

        return status

    def _compute_experiences_stats(self) -> Dict[str, Any]:
        """统计经验库指标"""
        experiences_file = self.data_dir / "09_KNOWLEDGE" / "experiences.json"

        if not experiences_file.exists():
            return {"metrics": {}, "details": {"error": "经验库文件不存在"}}

        try:
            with open(experiences_file, "r", encoding="utf-8") as f:
                experiences = json.load(f)

            if not isinstance(experiences, list):
                return {"metrics": {}, "details": {"error": "经验库格式错误"}}

            total = len(experiences)

            # 按状态统计
            status_counts = {}
            confidence_sum = 0
            validated_count = 0
            rejected_count = 0
            superseded_count = 0
            hypothesis_count = 0
            fact_count = 0
            evidence_count = 0

            for exp in experiences:
                if not isinstance(exp, dict):
                    continue

                status = exp.get("status", "UNKNOWN")
                status_counts[status] = status_counts.get(status, 0) + 1

                confidence = exp.get("confidence", 0)
                confidence_sum += confidence

                if status == "VALIDATED":
                    validated_count += 1
                elif status == "REJECTED":
                    rejected_count += 1
                elif status == "SUPERSEDED":
                    superseded_count += 1
                elif status == "HYPOTHESIS":
                    hypothesis_count += 1
                elif status == "FACT":
                    fact_count += 1
                elif status == "EVIDENCE":
                    evidence_count += 1

            avg_confidence = confidence_sum / total if total > 0 else 0

            return {
                "metrics": {
                    "experiences_total": total,
                    "experiences_validated_rate": validated_count / total if total > 0 else 0,
                    "experiences_deprecated_rate": (rejected_count + superseded_count) / total if total > 0 else 0,
                    "experiences_hypothesis_ratio": hypothesis_count / total if total > 0 else 0,
                    "experiences_fact_ratio": fact_count / total if total > 0 else 0,
                    "experiences_avg_confidence": avg_confidence,
                },
                "details": {
                    "total": total,
                    "status_counts": status_counts,
                    "by_status": {
                        "FACT": fact_count,
                        "EVIDENCE": evidence_count,
                        "HYPOTHESIS": hypothesis_count,
                        "VALIDATED": validated_count,
                        "REJECTED": rejected_count,
                        "SUPERSEDED": superseded_count,
                    },
                    "avg_confidence": round(avg_confidence, 4),
                },
            }

        except Exception as e:
            logger.error(f"计算经验库指标失败: {e}")
            return {"metrics": {}, "details": {"error": str(e)}}

    def _compute_lexicon_stats(self) -> Dict[str, Any]:
        """统计词库指标"""
        lexicon_file = self.data_dir / "06_RUNTIME" / "ace" / "data" / "memory" / "lexicon.json"

        if not lexicon_file.exists():
            return {"metrics": {}, "details": {"error": "词库文件不存在"}}

        try:
            with open(lexicon_file, "r", encoding="utf-8") as f:
                lexicon = json.load(f)

            concepts = lexicon.get("concepts", {})
            total = len(concepts)

            # 统计孤立概念（无related引用）
            orphan_count = 0
            for name, concept in concepts.items():
                if isinstance(concept, dict):
                    related = concept.get("related", [])
                    if not related:
                        orphan_count += 1

            orphan_rate = orphan_count / total if total > 0 else 0

            return {
                "metrics": {
                    "lexicon_total": total,
                    "lexicon_orphan_rate": orphan_rate,
                },
                "details": {
                    "total": total,
                    "orphan_count": orphan_count,
                    "orphan_rate": round(orphan_rate, 4),
                },
            }

        except Exception as e:
            logger.error(f"计算词库指标失败: {e}")
            return {"metrics": {}, "details": {"error": str(e)}}

    def _compute_evolution_stats(self) -> Dict[str, Any]:
        """统计演化链指标"""
        evolution_file = self.data_dir / "09_KNOWLEDGE" / "evolution.json"

        if not evolution_file.exists():
            return {"metrics": {}, "details": {"error": "演化链文件不存在"}}

        try:
            with open(evolution_file, "r", encoding="utf-8") as f:
                evolutions = json.load(f)

            if not isinstance(evolutions, list):
                return {"metrics": {}, "details": {"error": "演化链格式错误"}}

            total = len(evolutions)

            return {
                "metrics": {
                    "evolution_total": total,
                },
                "details": {
                    "total": total,
                },
            }

        except Exception as e:
            logger.error(f"计算演化链指标失败: {e}")
            return {"metrics": {}, "details": {"error": str(e)}}

    def _compute_assumptions_stats(self) -> Dict[str, Any]:
        """统计假设指标"""
        assumptions_file = self.data_dir / "08_GOVERNANCE" / "assumptions" / "assumptions_db.jsonl"

        if not assumptions_file.exists():
            return {"metrics": {}, "details": {"error": "假设文件不存在"}}

        try:
            total = 0
            avg_confidence = 0
            active_count = 0

            with open(assumptions_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        assumption = json.loads(line.strip())
                        total += 1
                        confidence = assumption.get("confidence", 0)
                        avg_confidence += confidence

                        if assumption.get("status") == "hypothesis":
                            active_count += 1
                    except Exception:
                        continue

            avg_confidence = avg_confidence / total if total > 0 else 0

            return {
                "metrics": {
                    "assumptions_total": total,
                    "assumptions_avg_confidence": avg_confidence,
                },
                "details": {
                    "total": total,
                    "active": active_count,
                    "avg_confidence": round(avg_confidence, 4),
                },
            }

        except Exception as e:
            logger.error(f"计算假设指标失败: {e}")
            return {"metrics": {}, "details": {"error": str(e)}}

    def _compute_overall(self, status: Dict[str, Any]):
        """计算综合指标"""
        metrics = status["metrics"]

        # 计算总知识数
        total_knowledge = (
            metrics.get("experiences_total", 0)
            + metrics.get("lexicon_total", 0)
            + metrics.get("evolution_total", 0)
        )

        # 计算平均置信度（加权）
        exp_confidence = metrics.get("experiences_avg_confidence", 0)
        exp_weight = metrics.get("experiences_total", 0)

        ass_confidence = metrics.get("assumptions_avg_confidence", 0)
        ass_weight = metrics.get("assumptions_total", 0)

        total_weight = exp_weight + ass_weight
        overall_confidence = (exp_confidence * exp_weight + ass_confidence * ass_weight) / total_weight if total_weight > 0 else 0

        # 计算文明健康度
        health_score = 0
        factors = []

        # 验证率高 = 健康
        validated_rate = metrics.get("experiences_validated_rate", 0)
        health_score += validated_rate * 30
        factors.append(f"验证率: {validated_rate:.2f} × 30")

        # 废弃率低 = 健康
        deprecated_rate = metrics.get("experiences_deprecated_rate", 0)
        health_score += (1 - deprecated_rate) * 20
        factors.append(f"废弃率: {(1-deprecated_rate):.2f} × 20")

        # 孤立概念少 = 健康
        orphan_rate = metrics.get("lexicon_orphan_rate", 0)
        health_score += (1 - orphan_rate) * 20
        factors.append(f"孤立概念率: {(1-orphan_rate):.2f} × 20")

        # 事实比例高 = 健康
        fact_ratio = metrics.get("experiences_fact_ratio", 0)
        health_score += fact_ratio * 15
        factors.append(f"事实比例: {fact_ratio:.2f} × 15")

        # 置信度高 = 健康
        health_score += overall_confidence * 15
        factors.append(f"置信度: {overall_confidence:.2f} × 15")

        status["metrics"].update({
            "total_knowledge": total_knowledge,
            "overall_confidence": overall_confidence,
            "civilization_health_score": health_score,
        })

        status["details"]["overall"] = {
            "total_knowledge": total_knowledge,
            "overall_confidence": round(overall_confidence, 4),
            "health_score": round(health_score, 2),
            "health_factors": factors,
            "health_level": self._get_health_level(health_score),
        }

    def _get_health_level(self, score: float) -> str:
        """获取健康等级"""
        if score >= 80:
            return "🟢 优秀 (Excellent)"
        elif score >= 60:
            return "🟡 良好 (Good)"
        elif score >= 40:
            return "🟠 一般 (Fair)"
        else:
            return "🔴 较差 (Poor)"

    def _generate_report_file(self, status: Dict[str, Any]):
        """生成文明状态报告文件"""
        report_date = status["report_date"]
        report_file = self.output_dir / f"civilization_status_{report_date}.md"

        metrics = status["metrics"]
        details = status["details"]

        content = f"""# 文明状态报告

**报告日期**: {report_date}
**生成时间**: {status["generated_at"]}
**健康等级**: {details["overall"]["health_level"]}

---

## 一、综合指标

| 指标 | 值 |
|------|-----|
| 总知识数 | {metrics["total_knowledge"]} |
| 总体置信度 | {round(metrics["overall_confidence"] * 100, 2)}% |
| 文明健康度 | {round(metrics["civilization_health_score"], 2)} |

### 健康度计算因子

{chr(10).join(f"- {f}" for f in details["overall"]["health_factors"])}

---

## 二、经验库指标

| 指标 | 值 |
|------|-----|
| 经验总数 | {metrics["experiences_total"]} |
| 验证率 | {round(metrics["experiences_validated_rate"] * 100, 2)}% |
| 废弃率 | {round(metrics["experiences_deprecated_rate"] * 100, 2)}% |
| 假说比例 | {round(metrics["experiences_hypothesis_ratio"] * 100, 2)}% |
| 事实比例 | {round(metrics["experiences_fact_ratio"] * 100, 2)}% |
| 平均置信度 | {round(metrics["experiences_avg_confidence"] * 100, 2)}% |

### 状态分布

| 状态 | 数量 |
|------|------|
| FACT | {details["experiences"]["by_status"]["FACT"]} |
| EVIDENCE | {details["experiences"]["by_status"]["EVIDENCE"]} |
| HYPOTHESIS | {details["experiences"]["by_status"]["HYPOTHESIS"]} |
| VALIDATED | {details["experiences"]["by_status"]["VALIDATED"]} |
| REJECTED | {details["experiences"]["by_status"]["REJECTED"]} |
| SUPERSEDED | {details["experiences"]["by_status"]["SUPERSEDED"]} |

---

## 三、词库指标

| 指标 | 值 |
|------|-----|
| 概念总数 | {metrics["lexicon_total"]} |
| 孤立概念率 | {round(metrics["lexicon_orphan_rate"] * 100, 2)}% |
| 孤立概念数 | {details["lexicon"]["orphan_count"]} |

---

## 四、演化链指标

| 指标 | 值 |
|------|-----|
| 演化链总数 | {metrics["evolution_total"]} |

---

## 五、假设指标

| 指标 | 值 |
|------|-----|
| 假设总数 | {metrics["assumptions_total"]} |
| 平均置信度 | {round(metrics["assumptions_avg_confidence"] * 100, 2)}% |
| 活跃假设数 | {details["assumptions"]["active"]} |

---

## 六、建议

{self._generate_suggestions(metrics)}
"""

        try:
            with open(report_file, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info(f"文明状态报告已生成: {report_file}")
        except Exception as e:
            logger.error(f"生成文明状态报告失败: {e}")

    def _generate_suggestions(self, metrics: Dict[str, Any]) -> str:
        """生成建议"""
        suggestions = []

        validated_rate = metrics.get("experiences_validated_rate", 0)
        if validated_rate < 0.5:
            suggestions.append("⚠️ 验证率较低，建议加强知识验证流程")

        deprecated_rate = metrics.get("experiences_deprecated_rate", 0)
        if deprecated_rate > 0.3:
            suggestions.append("⚠️ 废弃率较高，建议清理无效知识")

        orphan_rate = metrics.get("lexicon_orphan_rate", 0)
        if orphan_rate > 0.3:
            suggestions.append("⚠️ 孤立概念较多，建议建立概念引用关系")

        health_score = metrics.get("civilization_health_score", 0)
        if health_score >= 80:
            suggestions.append("✅ 文明状态优秀，继续保持")
        elif health_score >= 60:
            suggestions.append("📈 文明状态良好，有提升空间")
        else:
            suggestions.append("🔧 文明状态需要改善，建议执行全面治理")

        if not suggestions:
            suggestions.append("✅ 各项指标正常")

        return chr(10).join(f"- {s}" for s in suggestions)
