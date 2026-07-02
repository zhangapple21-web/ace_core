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
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

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

        # 5. 连续性指标
        continuity_stats = self._compute_continuity_metrics()
        status["metrics"].update(continuity_stats["metrics"])
        status["details"]["continuity"] = continuity_stats["details"]

        # 6. 综合计算
        self._compute_overall(status)

        # 7. 趋势分析（与历史报告对比）
        self._compute_trends(status)

        # 8. 生成报告文件
        self._generate_report_file(status)

        return status

    def _compute_experiences_stats(self) -> Dict[str, Any]:
        """统计经验库指标

        修复字段映射（2026-07-02）：
        experiences.json 实际字段是 experience_id / source / date / conclusion /
        evidence / constraints_updated / related_concepts，没有 status / confidence。
        这里从 evidence 和 constraints_updated 推断 status，从 evidence 数量推断 confidence。
        """
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

                # 字段映射：优先用显式 status，没有则从 evidence 推断
                status = exp.get("status")
                if not status:
                    # 从 evidence 和 constraints_updated 推断 status
                    ev = exp.get("evidence", [])
                    ev_count = len(ev) if isinstance(ev, list) else (1 if ev else 0)
                    has_constraints = bool(exp.get("constraints_updated"))

                    if ev_count >= 3 and has_constraints:
                        status = "VALIDATED"
                    elif ev_count >= 1:
                        status = "EVIDENCE"
                    else:
                        status = "HYPOTHESIS"

                status_counts[status] = status_counts.get(status, 0) + 1

                # confidence 推断：从 evidence 数量
                confidence = exp.get("confidence")
                if confidence is None:
                    ev = exp.get("evidence", [])
                    ev_count = len(ev) if isinstance(ev, list) else (1 if ev else 0)
                    if ev_count >= 5:
                        confidence = 0.9
                    elif ev_count >= 3:
                        confidence = 0.7
                    elif ev_count >= 1:
                        confidence = 0.5
                    else:
                        confidence = 0.3
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

            # 计算 Loop Density（闭环密度）
            loop_density = 0.0
            try:
                import sys
                sys.path.insert(0, str(self.data_dir.parent))
                from core.experience_deposition import ExperienceDeposition
                ed = ExperienceDeposition(str(self.data_dir / "09_KNOWLEDGE"))
                ld = ed.get_loop_density()
                loop_density = ld.get("loop_density", 0.0)
            except Exception:
                pass

            return {
                "metrics": {
                    "experiences_total": total,
                    "experiences_validated_rate": validated_count / total if total > 0 else 0,
                    "experiences_deprecated_rate": (rejected_count + superseded_count) / total if total > 0 else 0,
                    "experiences_hypothesis_ratio": hypothesis_count / total if total > 0 else 0,
                    "experiences_fact_ratio": fact_count / total if total > 0 else 0,
                    "experiences_avg_confidence": avg_confidence,
                    "loop_density": loop_density,
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

    def _compute_continuity_metrics(self) -> Dict[str, Any]:
        """计算连续性指标

        三个指标：
        1. 血缘连通性（Lineage Connectivity）
        2. 记忆完整性（Memory Integrity）
        3. 标识一致性（Identity Consistency）
        """
        metrics = {}
        details = {}

        # 1. 血缘连通性
        lineage_result = self._compute_lineage_connectivity()
        metrics.update(lineage_result["metrics"])
        details["lineage_connectivity"] = lineage_result["details"]

        # 2. 记忆完整性
        memory_result = self._compute_memory_integrity()
        metrics.update(memory_result["metrics"])
        details["memory_integrity"] = memory_result["details"]

        # 3. 标识一致性
        identity_result = self._compute_identity_consistency()
        metrics.update(identity_result["metrics"])
        details["identity_consistency"] = identity_result["details"]

        # 综合连续性得分
        lineage_score = metrics.get("continuity_lineage_score", 0)
        memory_score = metrics.get("continuity_memory_score", 0)
        identity_score = metrics.get("continuity_identity_score", 0)

        overall_continuity = (lineage_score + memory_score + identity_score) / 3
        metrics["continuity_overall_score"] = overall_continuity
        details["overall"] = {
            "lineage_score": round(lineage_score, 4),
            "memory_score": round(memory_score, 4),
            "identity_score": round(identity_score, 4),
            "overall_score": round(overall_continuity, 4),
        }

        return {"metrics": metrics, "details": details}

    def _compute_lineage_connectivity(self) -> Dict[str, Any]:
        """计算血缘连通性

        优先使用 CivilizationGraph，降级使用词库 related 关系统计。
        """
        # 尝试使用 CivilizationGraph
        try:
            from core.governance.civilization_graph import CivilizationGraph

            graph = CivilizationGraph(str(self.data_dir))
            stats = graph.get_graph_stats()

            active_nodes = stats.get("active_nodes", 0)
            active_relations = stats.get("active_relations", 0)
            avg_degree = stats.get("average_degree", 0)

            if active_nodes > 0:
                relation_ratio = active_relations / active_nodes
                degree_score = min(avg_degree / 4.0, 1.0)
                ratio_score = min(relation_ratio / 2.0, 1.0)

                connectivity_score = (degree_score * 0.6 + ratio_score * 0.4)
                connectivity_score = min(max(connectivity_score, 0.0), 1.0)

                return {
                    "metrics": {
                        "continuity_lineage_score": connectivity_score,
                    },
                    "details": {
                        "source": "civilization_graph",
                        "active_nodes": active_nodes,
                        "active_relations": active_relations,
                        "average_degree": avg_degree,
                        "relation_node_ratio": round(relation_ratio, 4),
                        "degree_score": round(degree_score, 4),
                        "ratio_score": round(ratio_score, 4),
                        "score": round(connectivity_score, 4),
                    },
                }
        except Exception as e:
            logger.debug(f"CivilizationGraph 不可用，降级用词库统计: {e}")

        # 降级：用词库 related 关系统计
        try:
            lexicon_file = self.data_dir / "06_RUNTIME" / "ace" / "data" / "memory" / "lexicon.json"

            if not lexicon_file.exists():
                return {
                    "metrics": {"continuity_lineage_score": 0.0},
                    "details": {
                        "source": "fallback_lexicon",
                        "error": "词库文件不存在",
                        "score": 0.0,
                    },
                }

            with open(lexicon_file, "r", encoding="utf-8") as f:
                lexicon = json.load(f)

            concepts = lexicon.get("concepts", {})
            total = len(concepts)

            if total == 0:
                return {
                    "metrics": {"continuity_lineage_score": 0.0},
                    "details": {
                        "source": "fallback_lexicon",
                        "total_concepts": 0,
                        "connected_concepts": 0,
                        "score": 0.0,
                    },
                }

            connected_count = 0
            total_relations = 0
            for name, concept in concepts.items():
                if isinstance(concept, dict):
                    related = concept.get("related", [])
                    if related and len(related) > 0:
                        connected_count += 1
                        total_relations += len(related) if isinstance(related, list) else 0

            connectivity_score = connected_count / total
            avg_relations = total_relations / total if total > 0 else 0

            return {
                "metrics": {
                    "continuity_lineage_score": connectivity_score,
                },
                "details": {
                    "source": "fallback_lexicon",
                    "total_concepts": total,
                    "connected_concepts": connected_count,
                    "total_relations": total_relations,
                    "avg_relations_per_concept": round(avg_relations, 4),
                    "score": round(connectivity_score, 4),
                },
            }

        except Exception as e:
            logger.error(f"计算血缘连通性失败: {e}")
            return {
                "metrics": {"continuity_lineage_score": 0.0},
                "details": {"error": str(e), "score": 0.0},
            }

    def _compute_memory_integrity(self) -> Dict[str, Any]:
        """计算记忆完整性

        统计 02_MEMORY 目录的文件数、总大小、索引文件存在情况。
        """
        memory_dir = self.data_dir / "02_MEMORY"

        try:
            if not memory_dir.exists():
                return {
                    "metrics": {"continuity_memory_score": 0.1},
                    "details": {
                        "memory_dir_exists": False,
                        "total_files": 0,
                        "total_size_bytes": 0,
                        "index_exists": False,
                        "score": 0.1,
                        "note": "02_MEMORY 目录不存在，使用基础分",
                    },
                }

            total_files = 0
            total_size = 0
            index_exists = False

            for file_path in memory_dir.rglob("*"):
                if file_path.is_file():
                    total_files += 1
                    total_size += file_path.stat().st_size

                    name = file_path.name.lower()
                    if "index" in name or "catalog" in name or "manifest" in name:
                        index_exists = True

            base_score = 0.3

            if total_files > 0:
                import math
                file_score = min(math.log10(total_files + 1) / 2.0, 0.4)
            else:
                file_score = 0.0

            index_bonus = 0.3 if index_exists else 0.0

            integrity_score = base_score + file_score + index_bonus
            integrity_score = min(max(integrity_score, 0.0), 1.0)

            return {
                "metrics": {
                    "continuity_memory_score": integrity_score,
                },
                "details": {
                    "memory_dir_exists": True,
                    "total_files": total_files,
                    "total_size_bytes": total_size,
                    "total_size_human": self._human_readable_size(total_size),
                    "index_exists": index_exists,
                    "base_score": base_score,
                    "file_score": round(file_score, 4),
                    "index_bonus": index_bonus,
                    "score": round(integrity_score, 4),
                },
            }

        except Exception as e:
            logger.error(f"计算记忆完整性失败: {e}")
            return {
                "metrics": {"continuity_memory_score": 0.0},
                "details": {"error": str(e), "score": 0.0},
            }

    def _compute_identity_consistency(self) -> Dict[str, Any]:
        """计算标识一致性

        查找 identity.json，检查唯一ID、创建时间、名称等关键字段。
        """
        possible_paths = [
            self.data_dir / "02_MEMORY" / "identity.json",
            self.data_dir / "01_CORE" / "identity.json",
            self.data_dir / "identity.json",
        ]

        identity_file = None
        for path in possible_paths:
            if path.exists():
                identity_file = path
                break

        if identity_file is None:
            return {
                "metrics": {"continuity_identity_score": 0.0},
                "details": {
                    "identity_file_exists": False,
                    "checked_paths": [str(p) for p in possible_paths],
                    "checks": {},
                    "passed": 0,
                    "total": 3,
                    "score": 0.0,
                },
            }

        try:
            with open(identity_file, "r", encoding="utf-8") as f:
                identity = json.load(f)

            if not isinstance(identity, dict):
                return {
                    "metrics": {"continuity_identity_score": 0.0},
                    "details": {
                        "identity_file_exists": True,
                        "identity_file_path": str(identity_file),
                        "error": "identity.json 格式错误",
                        "score": 0.0,
                    },
                }

            checks = {
                "has_unique_id": False,
                "has_created_time": False,
                "has_name": False,
            }

            id_fields = ["id", "uuid", "identity_id", "unique_id", "civilization_id"]
            for field in id_fields:
                if field in identity and identity[field]:
                    checks["has_unique_id"] = True
                    break

            time_fields = ["created", "created_at", "birth_time", "inception", "born"]
            for field in time_fields:
                if field in identity and identity[field]:
                    checks["has_created_time"] = True
                    break

            name_fields = ["name", "title", "identity", "label"]
            for field in name_fields:
                if field in identity and identity[field]:
                    checks["has_name"] = True
                    break

            passed = sum(1 for v in checks.values() if v)
            total = len(checks)
            consistency_score = passed / total if total > 0 else 0.0

            return {
                "metrics": {
                    "continuity_identity_score": consistency_score,
                },
                "details": {
                    "identity_file_exists": True,
                    "identity_file_path": str(identity_file),
                    "checks": checks,
                    "passed": passed,
                    "total": total,
                    "score": round(consistency_score, 4),
                },
            }

        except Exception as e:
            logger.error(f"计算标识一致性失败: {e}")
            return {
                "metrics": {"continuity_identity_score": 0.0},
                "details": {"error": str(e), "score": 0.0},
            }

    def _human_readable_size(self, size_bytes: int) -> str:
        """将字节数转换为人类可读格式"""
        if size_bytes == 0:
            return "0 B"
        import math
        size_name = ("B", "KB", "MB", "GB", "TB")
        i = int(math.floor(math.log(size_bytes, 1024)))
        p = math.pow(1024, i)
        s = round(size_bytes / p, 2)
        return f"{s} {size_name[i]}"


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
| 闭环密度 | {round(metrics.get("loop_density", 0) * 100, 2)}% |

### 闭环密度解读

> 闭环密度（Loop Density）= 经验回流路径数 / 经验沉积路径数
> 0% = 纯单向沉积（经验存了从没人读）
> 100% = 完全闭环（每条经验都至少被读取过一次）
> 来源：R1 Shadow Layer 考古 + 闭环反馈协议（Closed-Loop Feedback Protocol）

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

## 六、趋势分析

{self._generate_trend_section(status)}

---

## 七、连续性指标

{self._generate_continuity_section(status)}

---

## 八、建议

{self._generate_suggestions(metrics)}
"""

        try:
            with open(report_file, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info(f"文明状态报告已生成: {report_file}")
        except Exception as e:
            logger.error(f"生成文明状态报告失败: {e}")

    def _load_history_metrics(self, max_days: int = 7) -> List[Dict[str, Any]]:
        """
        加载历史报告的指标数据

        从 journals 目录读取 civilization_status_*.md 文件，
        提取每日关键指标，用于趋势分析。

        Args:
            max_days: 最多加载多少天的历史数据

        Returns:
            按日期升序排列的历史指标列表
        """
        history = []
        try:
            report_files = sorted(
                self.output_dir.glob("civilization_status_*.md"),
                key=lambda p: p.name
            )

            for report_file in report_files[-max_days:]:
                date_match = re.search(r"(\d{4}-\d{2}-\d{2})", report_file.name)
                if not date_match:
                    continue
                report_date = date_match.group(1)

                try:
                    with open(report_file, "r", encoding="utf-8") as f:
                        content = f.read()

                    metrics = {"report_date": report_date}

                    patterns = {
                        "total_knowledge": r"总知识数\s*\|\s*([\d.]+)",
                        "civilization_health_score": r"文明健康度\s*\|\s*([\d.]+)",
                        "experiences_total": r"经验总数\s*\|\s*([\d.]+)",
                        "experiences_validated_rate": r"验证率\s*\|\s*([\d.]+)%",
                        "experiences_deprecated_rate": r"废弃率\s*\|\s*([\d.]+)%",
                        "experiences_hypothesis_ratio": r"假说比例\s*\|\s*([\d.]+)%",
                        "experiences_fact_ratio": r"事实比例\s*\|\s*([\d.]+)%",
                        "experiences_avg_confidence": r"平均置信度\s*\|\s*([\d.]+)%",
                        "lexicon_total": r"概念总数\s*\|\s*([\d.]+)",
                        "lexicon_orphan_rate": r"孤立概念率\s*\|\s*([\d.]+)%",
                        "evolution_total": r"演化链总数\s*\|\s*([\d.]+)",
                        "assumptions_total": r"假设总数\s*\|\s*([\d.]+)",
                        "assumptions_avg_confidence": r"平均置信度\s*\|\s*([\d.]+)%",
                        "overall_confidence": r"总体置信度\s*\|\s*([\d.]+)%",
                    }

                    for key, pattern in patterns.items():
                        match = re.search(pattern, content)
                        if match:
                            val_str = match.group(1)
                            try:
                                if "%" in pattern or "rate" in key or "ratio" in key or "confidence" in key:
                                    metrics[key] = float(val_str) / 100 if key not in ["civilization_health_score"] else float(val_str)
                                else:
                                    metrics[key] = float(val_str) if "." in val_str else int(val_str)
                            except ValueError:
                                pass

                    if len(metrics) > 1:
                        history.append(metrics)

                except Exception as e:
                    logger.warning(f"读取历史报告失败 {report_file}: {e}")
                    continue

        except Exception as e:
            logger.warning(f"加载历史指标失败: {e}")

        return history

    def _compute_trends(self, status: Dict[str, Any]):
        """
        计算趋势分析

        基于历史数据，计算：
        - 日变化量（delta）
        - 3天趋势方向（上升/下降/平稳）
        - 趋势解读（增长放缓=成熟？污染上升=启动孟婆？）

        结果写入 status["trends"]
        """
        metrics = status["metrics"]
        report_date = status["report_date"]

        history = self._load_history_metrics(max_days=7)

        history_before_today = [h for h in history if h.get("report_date") != report_date]

        trends = {
            "has_history": len(history_before_today) > 0,
            "history_days": len(history_before_today),
            "daily_delta": {},
            "three_day_trend": {},
            "interpretations": [],
        }

        if not history_before_today:
            trends["interpretations"].append("📅 第一天记录，尚无历史数据可供对比")
            status["trends"] = trends
            return

        yesterday = history_before_today[-1]

        tracked_metrics = [
            ("total_knowledge", "总知识数", "increase_good"),
            ("civilization_health_score", "文明健康度", "increase_good"),
            ("experiences_total", "经验总数", "increase_good"),
            ("experiences_validated_rate", "经验验证率", "increase_good"),
            ("experiences_deprecated_rate", "经验废弃率", "decrease_good"),
            ("experiences_hypothesis_ratio", "假说比例", "neutral"),
            ("experiences_fact_ratio", "事实比例", "increase_good"),
            ("lexicon_total", "概念总数", "increase_good"),
            ("lexicon_orphan_rate", "孤立概念率", "decrease_good"),
            ("evolution_total", "演化链总数", "increase_good"),
            ("overall_confidence", "总体置信度", "increase_good"),
        ]

        for key, label, direction in tracked_metrics:
            current = metrics.get(key, 0)
            prev = yesterday.get(key)

            if prev is None:
                continue

            delta = current - prev
            delta_pct = (delta / prev * 100) if prev != 0 else 0

            is_percentage = "rate" in key or "ratio" in key or "confidence" in key

            if is_percentage:
                delta_display = f"{delta*100:+.2f}%"
            else:
                delta_display = f"{delta:+}" if isinstance(delta, int) else f"{delta:+.2f}"

            trends["daily_delta"][key] = {
                "label": label,
                "current": current,
                "previous": prev,
                "delta": delta,
                "delta_pct": delta_pct,
                "delta_display": delta_display,
                "direction": direction,
            }

            if len(history_before_today) >= 3:
                last_three = [h.get(key, 0) for h in history_before_today[-3:]]
                last_three.append(current)

                if len(last_three) >= 3:
                    diffs = []
                    for i in range(1, len(last_three)):
                        if last_three[i-1] != 0:
                            diffs.append((last_three[i] - last_three[i-1]) / abs(last_three[i-1]))
                        else:
                            diffs.append(0)

                    avg_change = sum(diffs) / len(diffs) if diffs else 0

                    if avg_change > 0.02:
                        trend = "📈 上升"
                    elif avg_change < -0.02:
                        trend = "📉 下降"
                    else:
                        trend = "➡️ 平稳"

                    trends["three_day_trend"][key] = {
                        "label": label,
                        "trend": trend,
                        "avg_change_pct": avg_change * 100,
                    }

        trends["interpretations"] = self._generate_trend_interpretations(trends, metrics)

        status["trends"] = trends

    def _generate_trend_interpretations(self, trends: Dict[str, Any], metrics: Dict[str, Any]) -> List[str]:
        """
        生成趋势解读

        根据趋势数据，给出文明层面的解读，例如：
        - 增长放缓 = 文明开始成熟
        - 污染上升 = 建议启动孟婆
        - 拒绝率上升 = 文明越来越保守

        Args:
            trends: 趋势数据
            metrics: 当前指标

        Returns:
            解读列表
        """
        interpretations = []

        if not trends["has_history"]:
            return interpretations

        daily_delta = trends["daily_delta"]

        if "lexicon_total" in daily_delta:
            lex_delta = daily_delta["lexicon_total"]
            delta_pct = lex_delta["delta_pct"]

            if lex_delta["delta"] > 0 and delta_pct < 1:
                interpretations.append("🧠 概念增长放缓（+{:.1f}%），文明开始收敛并沉淀".format(delta_pct))
            elif delta_pct > 10:
                interpretations.append("🌱 概念快速扩张（+{:.1f}%），处于探索期".format(delta_pct))

        if "experiences_validated_rate" in daily_delta:
            val_delta = daily_delta["experiences_validated_rate"]
            if val_delta["delta"] > 0:
                interpretations.append("✅ 验证率上升（{}），知识质量在提升".format(val_delta["delta_display"]))
            elif val_delta["delta"] < 0:
                interpretations.append("⚠️ 验证率下降（{}），需关注知识质量".format(val_delta["delta_display"]))

        if "lexicon_orphan_rate" in daily_delta:
            orphan_delta = daily_delta["lexicon_orphan_rate"]
            if orphan_delta["delta"] < 0:
                interpretations.append("🔗 孤立概念率下降（{}），知识网络在连接".format(orphan_delta["delta_display"]))
            elif orphan_delta["delta"] > 0:
                interpretations.append("⚠️ 孤立概念率上升（{}），需加强概念互联".format(orphan_delta["delta_display"]))

        if "civilization_health_score" in daily_delta:
            health_delta = daily_delta["civilization_health_score"]
            if health_delta["delta"] > 0:
                interpretations.append("💚 健康度上升（{}），文明在向好发展".format(health_delta["delta_display"]))
            elif health_delta["delta"] < 0:
                interpretations.append("💔 健康度下降（{}），需关注系统状态".format(health_delta["delta_display"]))

        if "experiences_deprecated_rate" in daily_delta:
            dep_delta = daily_delta["experiences_deprecated_rate"]
            if dep_delta["delta"] > 0.05:
                interpretations.append("🗑️ 废弃率上升较快（{}），新陈代谢活跃".format(dep_delta["delta_display"]))

        if not interpretations:
            interpretations.append("📊 各项指标变化平稳，文明处于稳定状态")

        return interpretations

    def _generate_trend_section(self, status: Dict[str, Any]) -> str:
        """
        生成趋势分析章节的 Markdown 内容

        Args:
            status: 文明状态数据（包含 trends 字段）

        Returns:
            Markdown 格式的趋势分析内容
        """
        trends = status.get("trends", {})

        if not trends.get("has_history"):
            return (
                "**历史数据**: 第 1 天记录，尚无对比基准\n\n"
                "> 从今天开始建立趋势基线，明天起将显示日变化和趋势方向。"
            )

        lines = []

        lines.append(f"**历史数据**: 已有 {trends['history_days']} 天记录")
        lines.append("")

        daily_delta = trends.get("daily_delta", {})
        three_day_trend = trends.get("three_day_trend", {})

        lines.append("### 日变化")
        lines.append("")
        lines.append("| 指标 | 今日 | 昨日 | 变化 | 趋势(3天) |")
        lines.append("|------|------|------|------|-----------|")

        display_order = [
            "total_knowledge",
            "civilization_health_score",
            "experiences_total",
            "experiences_validated_rate",
            "experiences_deprecated_rate",
            "experiences_fact_ratio",
            "lexicon_total",
            "lexicon_orphan_rate",
            "evolution_total",
            "overall_confidence",
        ]

        for key in display_order:
            if key not in daily_delta:
                continue
            d = daily_delta[key]
            t = three_day_trend.get(key, {})
            trend_str = t.get("trend", "—")

            is_pct = "rate" in key or "ratio" in key or "confidence" in key or "score" in key

            if is_pct:
                current_str = f"{d['current']*100:.2f}%" if "score" not in key else f"{d['current']:.2f}"
                prev_str = f"{d['previous']*100:.2f}%" if "score" not in key else f"{d['previous']:.2f}"
            else:
                current_str = str(d['current'])
                prev_str = str(d['previous'])

            delta_display = d["delta_display"]

            direction = d.get("direction", "neutral")
            if direction == "increase_good":
                if d["delta"] > 0:
                    delta_display = f"🟢 {delta_display}"
                elif d["delta"] < 0:
                    delta_display = f"🔴 {delta_display}"
            elif direction == "decrease_good":
                if d["delta"] < 0:
                    delta_display = f"🟢 {delta_display}"
                elif d["delta"] > 0:
                    delta_display = f"🔴 {delta_display}"

            lines.append(f"| {d['label']} | {current_str} | {prev_str} | {delta_display} | {trend_str} |")

        lines.append("")
        lines.append("### 文明体检解读")
        lines.append("")

        interpretations = trends.get("interpretations", [])
        for interp in interpretations:
            lines.append(f"- {interp}")

        return "\n".join(lines)

    def _generate_continuity_section(self, status: Dict[str, Any]) -> str:
        """生成连续性指标章节的 Markdown 内容

        Args:
            status: 文明状态数据（包含 continuity 详情）

        Returns:
            Markdown 格式的连续性指标内容
        """
        metrics = status.get("metrics", {})
        details = status.get("details", {}).get("continuity", {})

        lines = []

        # 总体得分
        overall_score = metrics.get("continuity_overall_score", 0)
        lines.append(f"**综合连续性得分**: {round(overall_score * 100, 2)}%")
        lines.append("")

        # 1. 血缘连通性
        lineage_details = details.get("lineage_connectivity", {})
        lineage_score = metrics.get("continuity_lineage_score", 0)
        lines.append("### 1. 血缘连通性")
        lines.append("")
        lines.append(f"| 指标 | 值 |")
        lines.append(f"|------|-----|")
        lines.append(f"| 连通性得分 | {round(lineage_score * 100, 2)}% |")

        source = lineage_details.get("source", "unknown")
        lines.append(f"| 数据来源 | {source} |")

        if source == "civilization_graph":
            lines.append(f"| 活跃节点数 | {lineage_details.get('active_nodes', 0)} |")
            lines.append(f"| 活跃关系数 | {lineage_details.get('active_relations', 0)} |")
            lines.append(f"| 平均连接度 | {lineage_details.get('average_degree', 0)} |")
            lines.append(f"| 关系节点比 | {lineage_details.get('relation_node_ratio', 0)} |")
        elif source == "fallback_lexicon":
            lines.append(f"| 概念总数 | {lineage_details.get('total_concepts', 0)} |")
            lines.append(f"| 有关联概念数 | {lineage_details.get('connected_concepts', 0)} |")
            lines.append(f"| 总关系数 | {lineage_details.get('total_relations', 0)} |")

        if "error" in lineage_details:
            lines.append(f"| 备注 | {lineage_details['error']} |")

        lines.append("")

        # 2. 记忆完整性
        memory_details = details.get("memory_integrity", {})
        memory_score = metrics.get("continuity_memory_score", 0)
        lines.append("### 2. 记忆完整性")
        lines.append("")
        lines.append(f"| 指标 | 值 |")
        lines.append(f"|------|-----|")
        lines.append(f"| 完整性得分 | {round(memory_score * 100, 2)}% |")
        lines.append(f"| 记忆目录存在 | {'是' if memory_details.get('memory_dir_exists') else '否'} |")
        lines.append(f"| 文件总数 | {memory_details.get('total_files', 0)} |")
        lines.append(f"| 总大小 | {memory_details.get('total_size_human', '0 B')} |")
        lines.append(f"| 索引文件存在 | {'是' if memory_details.get('index_exists') else '否'} |")

        if "note" in memory_details:
            lines.append(f"| 备注 | {memory_details['note']} |")

        lines.append("")

        # 3. 标识一致性
        identity_details = details.get("identity_consistency", {})
        identity_score = metrics.get("continuity_identity_score", 0)
        lines.append("### 3. 标识一致性")
        lines.append("")
        lines.append(f"| 指标 | 值 |")
        lines.append(f"|------|-----|")
        lines.append(f"| 一致性得分 | {round(identity_score * 100, 2)}% |")
        lines.append(f"| 标识文件存在 | {'是' if identity_details.get('identity_file_exists') else '否'} |")

        if identity_details.get("identity_file_exists"):
            checks = identity_details.get("checks", {})
            lines.append(f"| 有唯一ID | {'✅' if checks.get('has_unique_id') else '❌'} |")
            lines.append(f"| 有创建时间 | {'✅' if checks.get('has_created_time') else '❌'} |")
            lines.append(f"| 有名称 | {'✅' if checks.get('has_name') else '❌'} |")
            lines.append(f"| 通过项 | {identity_details.get('passed', 0)}/{identity_details.get('total', 3)} |")
        else:
            lines.append(f"| 备注 | 未找到 identity.json |")

        if "error" in identity_details:
            lines.append(f"| 错误 | {identity_details['error']} |")

        return "\n".join(lines)

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
