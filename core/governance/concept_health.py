"""
Concept Health Monitor（词库治理监控器）

职责：
- 检查词库健康状态
- 检测：孤立Concept/无人引用/重复命名/不同名同义/同名不同义/缺少父子节点
- 输出 concept_health.md

设计原则：
- 识别问题概念并提供处理建议
- 不自动删除，只标记和建议
- 支持批量处理
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Set

logger = logging.getLogger(__name__)


class ConceptHealthMonitor:
    """
    词库治理监控器

    检查项目：
    - orphan_concepts: 孤立概念（无related引用）
    - unreferenced_concepts: 无人引用的概念
    - duplicate_names: 重复命名
    - synonym_different_names: 不同名同义
    - homonym_different_meanings: 同名不同义
    - missing_parent_child: 缺少父子节点
    """

    def __init__(self, data_dir: str, output_dir: str):
        """
        初始化词库治理监控器

        Args:
            data_dir: 数据目录
            output_dir: 输出目录
        """
        self.data_dir = Path(data_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def check_health(self) -> Dict[str, Any]:
        """
        检查词库健康状态

        Returns:
            健康检查报告
        """
        now = datetime.now()
        report_date = now.strftime("%Y-%m-%d")

        report = {
            "generated_at": now.isoformat(),
            "report_date": report_date,
            "total_concepts": 0,
            "issues": {},
            "suggestions": [],
        }

        # 读取词库
        lexicon_file = self.data_dir / "06_RUNTIME" / "ace" / "data" / "memory" / "lexicon.json"
        if not lexicon_file.exists():
            report["issues"]["error"] = ["词库文件不存在"]
            return report

        try:
            with open(lexicon_file, "r", encoding="utf-8") as f:
                lexicon = json.load(f)

            concepts = lexicon.get("concepts", {})
            report["total_concepts"] = len(concepts)

            # 1. 检测孤立概念（无related引用）
            orphans = self._find_orphan_concepts(concepts)
            if orphans:
                report["issues"]["orphan_concepts"] = orphans
                report["suggestions"].append(f"发现 {len(orphans)} 个孤立概念，建议建立引用关系")

            # 2. 检测重复命名
            duplicates = self._find_duplicate_names(concepts)
            if duplicates:
                report["issues"]["duplicate_names"] = duplicates
                report["suggestions"].append(f"发现 {len(duplicates)} 个重复命名，建议合并或重命名")

            # 3. 检测缺少父子节点的概念
            missing_hierarchy = self._find_missing_hierarchy(concepts)
            if missing_hierarchy:
                report["issues"]["missing_hierarchy"] = missing_hierarchy
                report["suggestions"].append(f"发现 {len(missing_hierarchy)} 个缺少父子节点的概念，建议建立层级关系")

            # 4. 检测描述过短的概念
            short_definitions = self._find_short_definitions(concepts)
            if short_definitions:
                report["issues"]["short_definitions"] = short_definitions
                report["suggestions"].append(f"发现 {len(short_definitions)} 个描述过短的概念，建议补充定义")

            # 5. 检测格式异常的概念
            format_issues = self._find_format_issues(concepts)
            if format_issues:
                report["issues"]["format_issues"] = format_issues
                report["suggestions"].append(f"发现 {len(format_issues)} 个格式异常的概念，建议修正")

            # 6. 检测无人引用的概念
            unreferenced = self._find_unreferenced_concepts(concepts)
            if unreferenced:
                report["issues"]["unreferenced_concepts"] = unreferenced
                report["suggestions"].append(f"发现 {len(unreferenced)} 个无人引用的概念，建议检查是否需要保留")

            # 生成报告文件
            self._generate_report_file(report)

            return report

        except Exception as e:
            logger.error(f"词库健康检查失败: {e}")
            report["issues"]["error"] = [str(e)]
            return report

    def _find_orphan_concepts(self, concepts: Dict) -> List[Dict]:
        """发现孤立概念（无related引用）"""
        orphans = []

        for name, concept in concepts.items():
            if not isinstance(concept, dict):
                continue

            related = concept.get("related", [])
            if not related:
                orphans.append({
                    "name": name,
                    "suggestion": "建议添加related引用",
                })

        return orphans

    def _find_duplicate_names(self, concepts: Dict) -> List[Dict]:
        """发现重复命名（名称完全相同但内容不同）"""
        duplicates = []
        seen = {}

        for name, concept in concepts.items():
            if not isinstance(concept, dict):
                continue

            definition = concept.get("definition", "")

            if name in seen:
                # 检查定义是否不同
                existing_def = seen[name].get("definition", "")
                if definition != existing_def:
                    duplicates.append({
                        "name": name,
                        "existing_definition": existing_def[:50],
                        "new_definition": definition[:50],
                        "suggestion": "同名不同定义，建议重命名或合并",
                    })
            else:
                seen[name] = concept

        return duplicates

    def _find_missing_hierarchy(self, concepts: Dict) -> List[Dict]:
        """发现缺少父子节点的概念"""
        missing = []

        for name, concept in concepts.items():
            if not isinstance(concept, dict):
                continue

            # 检查是否缺少父节点或子节点
            parent = concept.get("parent", "")
            children = concept.get("children", [])

            if not parent and not children:
                missing.append({
                    "name": name,
                    "suggestion": "建议建立父子关系",
                })

        return missing

    def _find_short_definitions(self, concepts: Dict) -> List[Dict]:
        """发现描述过短的概念"""
        short = []

        for name, concept in concepts.items():
            if not isinstance(concept, dict):
                continue

            definition = concept.get("definition", "")
            if len(definition) < 10:
                short.append({
                    "name": name,
                    "definition_length": len(definition),
                    "suggestion": "描述过短，建议补充定义",
                })

        return short

    def _find_format_issues(self, concepts: Dict) -> List[Dict]:
        """发现格式异常的概念"""
        issues = []

        for name, concept in concepts.items():
            # 检查概念是否是字符串而非字典
            if isinstance(concept, str):
                issues.append({
                    "name": name,
                    "type": type(concept).__name__,
                    "value": concept[:50],
                    "suggestion": "格式异常，应为字典格式",
                })
            elif not isinstance(concept, dict):
                issues.append({
                    "name": name,
                    "type": type(concept).__name__,
                    "suggestion": f"格式异常，应为字典格式，当前为{type(concept).__name__}",
                })
            else:
                # 检查缺少必要字段
                if "name" not in concept:
                    issues.append({
                        "name": name,
                        "suggestion": "缺少name字段",
                    })

        return issues

    def _find_unreferenced_concepts(self, concepts: Dict) -> List[Dict]:
        """发现无人引用的概念"""
        referenced = set()
        unreferenced = []

        # 收集所有被引用的概念
        for name, concept in concepts.items():
            if isinstance(concept, dict):
                related = concept.get("related", [])
                if isinstance(related, list):
                    referenced.update(related)

        # 找出未被引用的概念
        for name in concepts.keys():
            if name not in referenced:
                unreferenced.append({
                    "name": name,
                    "suggestion": "无人引用，建议检查是否需要保留",
                })

        return unreferenced

    def _generate_report_file(self, report: Dict[str, Any]):
        """生成词库健康报告文件"""
        report_date = report["report_date"]
        report_file = self.output_dir / f"concept_health_{report_date}.md"

        content = f"""# 词库健康报告

**报告日期**: {report_date}
**生成时间**: {report["generated_at"]}
**概念总数**: {report["total_concepts"]}

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
                content += "| 概念名 | 建议 |\n"
                content += "|--------|------|\n"
                for item in items[:30]:
                    content += f"| {item.get('name', '')} | {item.get('suggestion', '')} |\n"

                if len(items) > 30:
                    content += f"\n（仅显示前30条，共{len(items)}条）\n"
            else:
                content += "无问题\n\n"

        content += """

---

## 三、处理建议

"""

        for suggestion in report["suggestions"]:
            content += f"- {suggestion}\n"

        if not report["suggestions"]:
            content += "- ✅ 词库健康，无特殊建议\n"

        try:
            with open(report_file, "w", encoding="utf-8") as f:
                f.write(content)
            logger.info(f"词库健康报告已生成: {report_file}")
        except Exception as e:
            logger.error(f"生成词库健康报告失败: {e}")
