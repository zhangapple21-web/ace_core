#!/usr/bin/env python3
"""
ENV-002: Environment Awareness Loop — 环境感知闭环
====================================================

核心区别：
  旧：扫描 → 结束
  新：扫描 → 为什么？→ 需要调查吗？→ 自动生成Task → 自动派Miner → 自动RoundTable

闭环：
  Environment
      ↓
  Observation (Sensor)
      ↓
  Question (为什么不正常？需要调查吗？)
      ↓
  Task (自动生成)
      ↓
  Research (Miner + call_model)
      ↓
  Report (研究结果)
      ↓
  RoundTable (审议)
      ↓
  Experience (沉淀)
      ↓
  Repository

用法：
  python awareness_loop.py              # 完整闭环
  python awareness_loop.py --scan-only  # 只扫描+提问，不执行
  python awareness_loop.py --json       # JSON输出
"""
import os, sys, json, argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from environment_sensor import EnvironmentSensor, SituationBuilder, Observation
from local_miner import call_model, health, list_capabilities, CAPABILITY_GRAPH
from roundtable import roundtable

WORKSPACE = Path(__file__).parent.parent
EXPERIENCE_DIR = WORKSPACE / "02_MEMORY" / "experience"


class QuestionGenerator:
    """从 Observation 生成 Question — 不是扫描完就结束，而是问'为什么'"""

    # 规则：什么样的 Observation 需要调查
    INVESTIGATE_RULES = {
        "provider_down": {
            "question": "数据源 {detail} 不可用，是否需要切换到备用源？",
            "capability": "research",
            "priority": "P0",
        },
        "provider_missing": {
            "question": "关键依赖 {detail} 未安装，是否影响系统运行？",
            "capability": "research",
            "priority": "P0",
        },
        "module_missing": {
            "question": "核心模块 {detail} 缺失，是否需要恢复？",
            "capability": "research",
            "priority": "P0",
        },
        "file_deleted": {
            "question": "文件被删除 {detail}，是否是误删？",
            "capability": "research",
            "priority": "P1",
        },
        "trending_repo": {
            "question": "GitHub 发现 {detail}，是否与 ACE 能力图谱相关？值得考古吗？",
            "capability": "archaeology",
            "priority": "P2",
        },
        "api_error": {
            "question": "API 错误 {detail}，是否需要切换 Provider？",
            "capability": "reasoning",
            "priority": "P1",
        },
    }

    def generate(self, observation: dict) -> dict | None:
        """从 Observation 生成 Question，如果不需要调查则返回 None"""
        category = observation.get("category", "")
        rule = self.INVESTIGATE_RULES.get(category)
        if not rule:
            return None

        detail_str = observation.get("title", "")
        question_text = rule["question"].format(detail=detail_str)

        return {
            "question": question_text,
            "capability": rule["capability"],
            "priority": rule["priority"],
            "source_observation": observation,
            "timestamp": datetime.now().isoformat(),
        }


class TaskDispatcher:
    """自动派单 — 把 Question 变成 Miner Task"""

    def execute(self, question: dict) -> dict:
        """执行研究任务"""
        capability = question.get("capability", "research")
        prompt = f"""你是 ACE 自主研究系统的研究员。

环境传感器发现了以下情况，需要你分析：

问题：{question['question']}

观察详情：
{json.dumps(question.get('source_observation', {}), ensure_ascii=False, indent=2)}

请分析：
1. 这个情况是否需要立即处理？
2. 如果需要处理，建议的方案是什么？
3. 是否需要人工介入？

请用简洁的中文回答（不超过200字）。
"""

        result = call_model(prompt, max_tokens=300, capability=capability)
        if "error" in result:
            return {
                "status": "failed",
                "error": result.get("errors", result.get("error")),
                "question": question["question"],
            }

        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
        return {
            "status": "ok",
            "question": question["question"],
            "analysis": content,
            "provider": result.get("provider"),
            "model": result.get("model"),
            "capability": capability,
            "latency_ms": result.get("latency_ms"),
            "timestamp": datetime.now().isoformat(),
        }


class ExperienceSediment:
    """经验沉淀 — 把研究结果存入 Experience"""

    def __init__(self):
        self.dir = EXPERIENCE_DIR
        self.dir.mkdir(parents=True, exist_ok=True)

    def save(self, report: dict):
        """保存经验"""
        filename = f"exp_{datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
        filepath = self.dir / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2, default=str)
        return filename


class AwarenessLoop:
    """环境感知闭环 — 把所有已有能力连接起来"""

    def __init__(self):
        self.sensor = EnvironmentSensor()
        self.builder = SituationBuilder()
        self.question_gen = QuestionGenerator()
        self.dispatcher = TaskDispatcher()
        self.experience = ExperienceSediment()

    def run(self, scan_only: bool = False) -> dict:
        """执行完整闭环"""
        print(f"[AWARENESS LOOP] Start @ {datetime.now().isoformat()}")

        # Step 1: 感知
        print("  [1] Scanning environment...")
        observations = self.sensor.scan_all(sources=["local", "providers"])
        situation = self.builder.build(observations)
        print(f"      → {situation['total_observations']} observations, {situation['new_observations']} new, {len(situation['high_priority'])} high priority")

        # Step 2: 提问
        print("  [2] Generating questions...")
        questions = []
        for obs in situation.get("all_observations", []):
            q = self.question_gen.generate(obs)
            if q:
                questions.append(q)
        print(f"      → {len(questions)} questions generated")
        for q in questions:
            print(f"        [{q['priority']}] {q['question'][:80]}")

        if scan_only or not questions:
            return {
                "step": "scan+question",
                "situation": situation,
                "questions": questions,
            }

        # Step 3: 自动派单（只处理 P0 和 P1）
        print("  [3] Dispatching tasks...")
        reports = []
        for q in questions:
            if q["priority"] not in ("P0", "P1"):
                print(f"        SKIP [{q['priority']}] {q['question'][:60]}")
                continue
            print(f"        EXECUTE [{q['priority']}] {q['question'][:60]}")
            report = self.dispatcher.execute(q)
            reports.append(report)
            if report["status"] == "ok":
                print(f"          → {report['provider']}: {report['analysis'][:100]}")
            else:
                print(f"          → FAILED: {report.get('error')}")

        # Step 4: 经验沉淀
        print("  [4] Sedimenting experience...")
        saved = []
        for r in reports:
            if r["status"] == "ok":
                fname = self.experience.save(r)
                saved.append(fname)
                print(f"        Saved: {fname}")

        # Step 5: Provider Health 摘要
        print("  [5] Provider Health:")
        for s in health.all_status():
            print(f"        {s['provider']:12s} status={s['status']:12s} score={s['health_score']}")

        print(f"[AWARENESS LOOP] Done @ {datetime.now().isoformat()}")

        return {
            "step": "full_loop",
            "situation": situation,
            "questions": questions,
            "reports": reports,
            "experiences_saved": saved,
            "provider_health": health.all_status(),
        }


def main():
    parser = argparse.ArgumentParser(description="ENV-002 Environment Awareness Loop")
    parser.add_argument("--scan-only", action="store_true", help="Only scan+question, no execution")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    loop = AwarenessLoop()
    result = loop.run(scan_only=args.scan_only)

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
