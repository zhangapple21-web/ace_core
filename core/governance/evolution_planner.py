"""
Evolution Planner — ACE 每日自检机制

老张的核心要求：
系统每天结束时要问自己四个问题，而不是继续堆模块。

四个核心问题：
1. 今天真正新增了什么能力，而不是新增了什么文件？
2. 今天拒绝了哪些东西，为什么拒绝？
3. 今天哪些知识发生了升级、降级或废弃？
4. 如果明天只能研究一个方向，应该选哪一个，为什么？

这不是写日报。
这是在规划自己的演化方向。
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field, asdict


@dataclass
class EvolutionQuestion:
    """演化问题"""
    id: str
    question: str
    answer: str = ""
    confidence: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DailyEvolutionReport:
    """每日演化报告"""
    date: str
    questions: List[EvolutionQuestion] = field(default_factory=list)

    # 今天真正新增了什么能力
    capabilities_added: List[str] = field(default_factory=list)
    files_added: List[str] = field(default_factory=list)

    # 今天拒绝了什么
    rejected_items: List[Dict[str, str]] = field(default_factory=list)

    # 知识变更
    knowledge_upgraded: List[str] = field(default_factory=list)
    knowledge_deprecated: List[str] = field(default_factory=list)

    # ROI 评估
    highest_roi_activity: str = ""
    lowest_roi_activity: str = ""
    total_time_estimate: str = ""

    # 明天方向
    recommended_direction: str = ""
    recommended_direction_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "date": self.date,
            "questions": [q.to_dict() for q in self.questions],
            "capabilities_added": self.capabilities_added,
            "files_added": self.files_added,
            "rejected_items": self.rejected_items,
            "knowledge_upgraded": self.knowledge_upgraded,
            "knowledge_deprecated": self.knowledge_deprecated,
            "roi": {
                "highest": self.highest_roi_activity,
                "lowest": self.lowest_roi_activity,
                "time_estimate": self.total_time_estimate,
            },
            "tomorrow": {
                "direction": self.recommended_direction,
                "reason": self.recommended_direction_reason,
            },
        }


class EvolutionPlanner:
    """
    演化规划器

    每天结束时触发，不是写日报，是在规划演化方向。

    核心问题：
    1. 今天真正新增了什么能力？
    2. 今天拒绝了什么？
    3. 哪些知识发生了变更？
    4. 明天应该研究什么？

    设计原则：
    - 少即是多：每天最多 3 个真正进入文明的能力
    - 拒绝也是成绩：没有拒绝说明没有判断力
    - 成本意识：评估 ROI，不是所有考古都值得
    - 方向优先：选择比努力更重要
    """

    def __init__(self, memory_path: str, archaeology_path: str):
        self.memory_path = Path(memory_path)
        self.archaeology_path = Path(archaeology_path)
        self.questions = [
            EvolutionQuestion(
                id="q1",
                question="今天真正新增了什么能力，而不是新增了什么文件？"
            ),
            EvolutionQuestion(
                id="q2",
                question="今天拒绝了哪些东西，为什么拒绝？"
            ),
            EvolutionQuestion(
                id="q3",
                question="今天哪些知识发生了升级、降级或废弃？"
            ),
            EvolutionQuestion(
                id="q4",
                question="如果明天只能研究一个方向，应该选哪一个，为什么？"
            ),
        ]

    def generate_daily_report(self) -> DailyEvolutionReport:
        """生成每日演化报告"""
        today = datetime.now().strftime("%Y-%m-%d")
        report = DailyEvolutionReport(date=today, questions=self.questions)

        # 1. 分析今天真正新增的能力
        report.capabilities_added = self._analyze_capabilities_added()
        report.files_added = self._analyze_files_added()

        # 2. 分析今天的拒绝
        report.rejected_items = self._analyze_rejections()

        # 3. 分析知识变更
        report.knowledge_upgraded, report.knowledge_deprecated = (
            self._analyze_knowledge_changes()
        )

        # 4. ROI 评估
        report.highest_roi_activity, report.lowest_roi_activity = (
            self._assess_roi()
        )

        # 5. 推荐明天方向
        (
            report.recommended_direction,
            report.recommended_direction_reason,
        ) = self._recommend_tomorrow_direction()

        # 回答四个核心问题
        for q in report.questions:
            q.answer = self._answer_question(q.id, report)

        return report

    def _analyze_capabilities_added(self) -> List[str]:
        """
        分析今天真正新增的能力

        区分"能力"和"文件"：
        - 文件：BinarySensor.py, tool_provider.py, ...
        - 能力：能够理解二进制结构、能够提取架构骨架、能够自动分类文件类型
        """
        capabilities = []

        # 从考古报告中提取今天学到的"方法"而不是"代码"
        archaeology_reports = list(self.archaeology_path.glob("*考古*.md"))
        today_reports = [
            r for r in archaeology_reports
            if r.stat().st_mtime > (datetime.now() - timedelta(days=1)).timestamp()
        ]

        for report_path in today_reports:
            try:
                content = report_path.read_text(encoding="utf-8")
                # 提取骨架/模式/方法
                if "骨架" in content:
                    capabilities.append(f"学会了骨架提取：从 {report_path.stem}")
                if "模式" in content:
                    capabilities.append(f"识别了新模式：从 {report_path.stem}")
                if "验证" in content and "R2" in content:
                    capabilities.append(f"验证了R2公理：从 {report_path.stem}")
            except Exception:
                pass

        # 限制：每天最多 3 个真正进入文明的能力
        return capabilities[:3]

    def _analyze_files_added(self) -> List[str]:
        """分析今天新增的文件"""
        files = []
        core_path = Path("c:/Users/USER/Downloads/Telegram Desktop/ace_runtime/core")

        if core_path.exists():
            for path in core_path.rglob("*.py"):
                if path.stat().st_mtime > (datetime.now() - timedelta(days=1)).timestamp():
                    rel = path.relative_to(core_path.parent)
                    files.append(str(rel))

        return files

    def _analyze_rejections(self) -> List[Dict[str, str]]:
        """
        分析今天的拒绝

        没有拒绝说明没有判断力。
        真正成熟后会大量输出：Reject / Duplicate / Already known / Too implementation-specific
        """
        # 从日志或记忆索引中查找今天的"未采用"记录
        # 目前返回空列表，后续可以从 memory_index 中提取
        rejections = []

        # 示例：如果有拒绝记录
        # rejections = [
        #     {"reason": "Duplicate", "item": "xxx", "because": "与已有的yyy重复"},
        #     {"reason": "Too specific", "item": "zzz", "because": "只是实现细节，无骨架价值"},
        # ]

        return rejections

    def _analyze_knowledge_changes(self) -> tuple[List[str], List[str]]:
        """
        分析知识变更

        - 升级：某个概念的理解更深了
        - 降级：发现之前理解有误
        - 废弃：某个模式不再适用
        """
        upgraded = []
        deprecated = []

        # 从考古报告中提取知识变更
        archaeology_reports = list(self.archaeology_path.glob("*考古*.md"))
        today_reports = [
            r for r in archaeology_reports
            if r.stat().st_mtime > (datetime.now() - timedelta(days=1)).timestamp()
        ]

        for report_path in today_reports:
            try:
                content = report_path.read_text(encoding="utf-8")
                if "升级" in content or "深化" in content:
                    upgraded.append(f"深化理解：从 {report_path.stem}")
                if "废弃" in content or "过时" in content:
                    deprecated.append(f"更新认知：从 {report_path.stem}")
            except Exception:
                pass

        return upgraded, deprecated

    def _assess_roi(self) -> tuple[str, str]:
        """
        评估 ROI

        不是所有考古都值得。
        最高ROI：验证了核心假设、发现了关键骨架
        最低ROI：研究了一个很普通、很容易被替代的项目
        """
        highest = ""
        lowest = ""

        # 从考古报告中提取 ROI 评估
        archaeology_reports = list(self.archaeology_path.glob("*考古*.md"))
        today_reports = [
            r for r in archaeology_reports
            if r.stat().st_mtime > (datetime.now() - timedelta(days=1)).timestamp()
        ]

        if today_reports:
            highest = f"最高ROI：{today_reports[0].stem}"
            if len(today_reports) > 1:
                lowest = f"最低ROI：{today_reports[-1].stem}"
            else:
                lowest = "最低ROI：今天只有一次考古，无法对比"

        return highest, lowest

    def _recommend_tomorrow_direction(self) -> tuple[str, str]:
        """
        推荐明天方向

        选择比努力更重要。
        回答：如果明天只能研究一个方向，应该选哪一个，为什么？
        """
        # 基于今天的发现，推荐明天应该继续深挖还是转向
        today_reports = list(self.archaeology_path.glob("*考古*.md"))
        today_reports = [
            r for r in today_reports
            if r.stat().st_mtime > (datetime.now() - timedelta(days=1)).timestamp()
        ]

        if not today_reports:
            return "继续观察", "今天无新发现，明天继续日常扫描"

        # 基于今天的骨架数量推荐
        capabilities_count = len(self._analyze_capabilities_added())

        if capabilities_count >= 3:
            # 今天吸收足够多了，明天应该消化
            return (
                "消化现有骨架，实现 BinarySensor 实际功能",
                "今天吸收了 3 个骨架，明天应该让它们长出肌肉，而不是继续考古"
            )
        elif capabilities_count >= 1:
            # 有一些收获，可以继续
            return (
                "继续考古 ReVa/Claude-Code 相关项目",
                "今天发现了工具驱动哲学，明天可以继续深挖"
            )
        else:
            # 没有收获，需要反思
            return (
                "复盘今天的考古方法",
                "今天没有找到真正有价值的骨架，需要反思方法是否正确"
            )

    def _answer_question(
        self, question_id: str, report: DailyEvolutionReport
    ) -> str:
        """回答四个核心问题"""
        answers = {
            "q1": f"真正新增能力：{', '.join(report.capabilities_added) if report.capabilities_added else '无'}",
            "q2": f"拒绝了：{len(report.rejected_items)} 个（ {'; '.join(r['reason'] for r in report.rejected_items) if report.rejected_items else '暂无拒绝记录'}）",
            "q3": f"升级：{', '.join(report.knowledge_upgraded) if report.knowledge_upgraded else '无'}；废弃：{', '.join(report.knowledge_deprecated) if report.knowledge_deprecated else '无'}",
            "q4": f"{report.recommended_direction}。原因：{report.recommended_direction_reason}",
        }
        return answers.get(question_id, "")

    def save_report(self, report: DailyEvolutionReport) -> str:
        """保存每日演化报告"""
        report_path = (
            self.archaeology_path
            / f"daily_evolution_{report.date}.json"
        )
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return str(report_path)

    def format_report(self, report: DailyEvolutionReport) -> str:
        """格式化报告为可读文本"""
        lines = [
            f"# 每日演化报告 — {report.date}",
            "",
            "## 四个核心问题",
        ]

        for q in report.questions:
            lines.append(f"**{q.question}**")
            lines.append(f"→ {q.answer}")
            lines.append("")

        lines.append("## 今日数据")
        lines.append(f"- 新增文件：{len(report.files_added)} 个")
        lines.append(f"- 新增能力：{len(report.capabilities_added)} 个")
        lines.append(f"- 拒绝项目：{len(report.rejected_items)} 个")

        if report.roi["highest"]:
            lines.append("")
            lines.append("## ROI 评估")
            lines.append(f"- {report.roi['highest']}")
            if report.roi["lowest"]:
                lines.append(f"- {report.roi['lowest']}")

        lines.append("")
        lines.append("## 明天方向")
        lines.append(f"**{report.recommended_direction}**")
        lines.append(f"原因：{report.recommended_direction_reason}")

        return "\n".join(lines)
