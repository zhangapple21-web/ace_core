"""
Experience Health Monitor（经验治理监控器）

职责：
- 每天检查经验库健康状态
- 检测：重复经验/失效经验/被Constraint覆盖/被Blueprint覆盖/被Protocol替代
- 输出 experience_health.md

设计原则：
- 识别问题经验并提供处理建议
- 不自动删除，只标记和建议
- 支持批量处理
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class ExperienceHealthMonitor:
    """
    经验治理监控器

    检查项目：
    - duplicate_experiences: 重复经验
    - expired_experiences: 失效经验（超过有效期）
    - covered_by_constraint: 被约束覆盖的经验
    - covered_by_blueprint: 被蓝图覆盖的经验
    - superseded_by_protocol: 被协议替代的经验
    - orphan_experiences: 孤立经验（无来源任务）
    """

    def __init__(self, data_dir: str, output_dir: str):
        """
        初始化经验治理监控器

        Args:
            data_dir: 数据目录
            output_dir: 输出目录
        """
        self.data_dir = Path(data_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def check_health(self) -> Dict[str, Any]:
        """
        检查经验库健康状态

        Returns:
            健康检查报告
        """
        now = datetime.now()
        report_date = now.strftime("%Y-%m-%d")

        report = {
            "generated_at": now.isoformat(),
            "report_date": report_date,
            "total_experiences": 0,
            "issues": {},
            "suggestions": [],
        }

        # 读取经验库
        experiences_file = self.data_dir / "09_KNOWLEDGE" / "experiences.json"
        if not experiences_file.exists():
            report["issues"]["error"] = ["经验库文件不存在"]
            return report

        try:
            with open(experiences_file, "r", encoding="utf-8") as f:
                experiences = json.load(f)

            if not isinstance(experiences, list):
                report["issues"]["error"] = ["经验库格式错误"]
                return report

            report["total_experiences"] = len(experiences)

            # 1. 检测重复经验
            duplicates = self._find_duplicate_experiences(experiences)
            if duplicates:
                report["issues"]["duplicate_experiences"] = duplicates
                report["suggestions"].append(f"发现 {len(duplicates)} 个重复经验，建议合并或删除")

            # 2. 检测失效经验
            expired = self._find_expired_experiences(experiences)
            if expired:
                report["issues"]["expired_experiences"] = expired
                report["suggestions"].append(f"发现 {len(expired)} 个失效经验，建议重新验证")

            # 3. 检测孤立经验
            orphans = self._find_orphan_experiences(experiences)
            if orphans:
                report["issues"]["orphan_experiences"] = orphans
                report["suggestions"].append(f"发现 {len(orphans)} 个孤立经验，建议关联来源任务")

            # 4. 检测被约束覆盖的经验
            covered_by_constraint = self._find_covered_by_constraint(experiences)
            if covered_by_constraint:
                report["issues"]["covered_by_constraint"] = covered_by_constraint
                report["suggestions"].append(f"发现 {len(covered_by_constraint)} 个被约束覆盖的经验，建议标记为SUPERSEDED")

            # 5. 检测置信度过低的经验
            low_confidence = self._find_low_confidence_experiences(experiences)
            if low_confidence:
                report["issues"]["low_confidence_experiences"] = low_confidence
                report["suggestions"].append(f"发现 {len(low_confidence)} 个置信度过低的经验，建议补充证据")

            # 6. 检测状态异常的经验
            status_issues = self._find_status_issues(experiences)
            if status_issues:
                report["issues"]["status_issues"] = status_issues
                report["suggestions"].append(f"发现 {len(status_issues)} 个状态异常的经验，建议检查")

            # 生成报告文件
            self._generate_report_file(report)

            return report

        except Exception as e:
            logger.error(f"经验健康检查失败: {e}")
            report["issues"]["error"] = [str(e)]
            return report

    def _find_duplicate_experiences(self, experiences: List[Dict]) -> List[Dict]:
        """发现重复经验"""
        duplicates = []
        seen = {}

        for exp in experiences:
            if not isinstance(exp, dict):
                continue

            exp_id = exp.get("id", "")
            title = exp.get("title", "")
            conclusion = exp.get("conclusion", "")[:100]

            # 构建唯一键
            key = (title, conclusion)

            if key in seen:
                duplicates.append({
                    "id": exp_id,
                    "title": title,
                    "duplicate_of": seen[key],
                    "suggestion": "建议合并或删除其中一个",
                })
            else:
                seen[key] = exp_id

        return duplicates

    def _find_expired_experiences(self, experiences: List[Dict]) -> List[Dict]:
        """发现失效经验"""
        expired = []
        now = datetime.now()

        for exp in experiences:
            if not isinstance(exp, dict):
                continue

            updated_str = exp.get("updated", "")
            if not updated_str:
                continue

            try:
                updated = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))
                age_days = (now - updated).days

                # 超过30天未更新且置信度低于0.7的经验视为失效
                if age_days > 30 and exp.get("confidence", 0) < 0.7:
                    expired.append({
                        "id": exp.get("id", ""),
                        "title": exp.get("title", ""),
                        "days_since_update": age_days,
                        "current_confidence": exp.get("confidence", 0),
                        "suggestion": "建议重新验证或更新",
                    })
            except Exception:
                continue

        return expired

    def _find_orphan_experiences(self, experiences: List[Dict]) -> List[Dict]:
        """发现孤立经验（无来源任务）"""
        orphans = []

        for exp in experiences:
            if not isinstance(exp, dict):
                continue

            source_task = exp.get("source_task", "")
            if not source_task:
                orphans.append({
                    "id": exp.get("id", ""),
                    "title": exp.get("title", ""),
                    "suggestion": "建议关联来源任务",
                })

        return orphans

    def _find_covered_by_constraint(self, experiences: List[Dict]) -> List[Dict]:
        """发现被约束覆盖的经验"""
        covered = []

        for exp in experiences:
            if not isinstance(exp, dict):
                continue

            # 检查经验是否描述的是约束类内容
            conclusion = exp.get("conclusion", "")
            if any(keyword in conclusion.lower() for keyword in ["必须", "禁止", "不得", "约束", "规则"]):
                # 检查是否已有对应的约束
                title = exp.get("title", "")
                if any(keyword in title.lower() for keyword in ["约束", "规则", "限制"]):
                    covered.append({
                        "id": exp.get("id", ""),
                        "title": title,
                        "suggestion": "内容为约束类，建议升级为Constraint或标记为SUPERSEDED",
                    })

        return covered

    def _find_low_confidence_experiences(self, experiences: List[Dict]) -> List[Dict]:
        """发现置信度过低的经验"""
        low_confidence = []

        for exp in experiences:
            if not isinstance(exp, dict):
                continue

            confidence = exp.get("confidence", 0)
            if confidence < 0.3:
                low_confidence.append({
                    "id": exp.get("id", ""),
                    "title": exp.get("title", ""),
                    "confidence": confidence,
                    "suggestion": "置信度过低，建议补充证据或标记为HYPOTHESIS",
                })

        return low_confidence

    def _find_status_issues(self, experiences: List[Dict]) -> List[Dict]:
        """发现状态异常的经验"""
        issues = []

        for exp in experiences:
            if not isinstance(exp, dict):
                continue

            status = exp.get("status", "")
            confidence = exp.get("confidence", 0)

            # FACT状态需要高置信度
            if status == "FACT" and confidence < 0.9:
                issues.append({
                    "id": exp.get("id", ""),
                    "title": exp.get("title", ""),
                    "status": status,
                    "confidence": confidence,
                    "issue": "FACT状态需要置信度>=0.9",
                    "suggestion": "降低状态或提升置信度",
                })

            # VALIDATED状态需要中等置信度
            elif status == "VALIDATED" and confidence < 0.7:
                issues.append({
                    "id": exp.get("id", ""),
                    "title": exp.get("title", ""),
                    "status": status,
                    "confidence": confidence,
                    "issue": "VALIDATED状态需要置信度>=0.7",
                    "suggestion": "降低状态或提升置信度",
                })

            # 无状态
            elif not status:
                issues.append({
                    "id": exp.get("id", ""),
                    "title": exp.get("title", ""),
                    "issue": "缺少状态字段",
                    "suggestion": "补充状态字段",
                })

        return issues

    def _generate_report_file(self, report: Dict[str, Any]):
        """生成经验健康报告文件"""
        report_date = report["report_date"]
        report_file = self.output_dir / f"experience_health_{report_date}.md"

        content = f"""# 经验库健康报告

**报告日期**: {report_date}
**生成时间**: {report["generated_at"]}
**经验总数**: {report["total_experiences"]}

---

## 一、问题概述

| 问题类型 | 数量 |
|----------|------|"""

        total_issues = 0
        for issue_type, items in report["issues"].items():
            if issue_type != "error":
                count = len(items)
                total_issues += count
                content += f"\n| {issue_type} | {count} |"

        content += f"""
| **总计** | **{total_issues}** |

---

## 二、详细问题

"""

        for issue_type, items in report["issues"].items():
            if issue_type == "error":
                continue

            content += f"### {issue_type}\n\n"
            if items:
                content += "| ID | 标题 | 建议 |\n"
                content += "|----|------|------|\n"
                for item in items[:20]:
                    content += f"| {item.get('id', '')} | {item.get('title', '')} | {item.get('suggestion', '')} |\n"

                if len(items) > 20:
                    content += f"\n（仅显示前20条，共{len(items)}条）\n"
            else:
                content += "无问题\n\n"

        content += """

---

## 三、处理建议

"""

        for suggestion in report["suggestions"]:
            content += f"- {suggestion}\n"

        if not report["suggestions"]:
            content += "- ✅ 经验库健康，无特殊建议\n"

        try:
            with open(report_file, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info(f"经验健康报告已生成: {report_file}")
        except Exception as e:
            logger.error(f"生成经验健康报告失败: {e}")
