"""Run one isolated Free Zone resident shift using explicitly shadow-routed models.

This is a workshop runner, not a production scheduler.  It records model
responses and provider usage under the free-research sandbox only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from core.miner_pool.miner_pool import MinerPool
from core.free_research_sandbox import FreeResearchSandbox
from core.free_zone_factories import FreeZoneFactoryLine
import hashlib


JOBS = [
    {
        "resident_id": "shenwen_grok_reviewer",
        "native_name": "夜航审稿人",
        "task_type": "grok_research_shadow",
        "model": "grok-4.6",
        "brief": "对这段公开研究判断做文本拆解：列出核心主张、证据、隐含假设、至少两个可证伪点，以及下一步应查的公开来源。不要绕过安全限制，不执行任何外部操作。\n\n材料：Grok 4.5/4.6 适合长程知识工作与代码任务，但其反证、提示注入识别能力仍缺少独立公开证据。",
    },
    {
        "resident_id": "shenwen_grok_workshop",
        "native_name": "夜航校验员",
        "task_type": "grok_coding_shadow",
        "model": "grok-4.5",
        "brief": "设计一个最小、可回放的代码调试反例实验，用来检验模型是否会先定位失败原因再给修复建议。只输出实验步骤、输入样例、预期失败模式和判定标准，不修改文件、不调用工具。",
    },
    {
        "resident_id": "video_kingdom_r1_narrator",
        "native_name": "视频王国叙事游牧者",
        "task_type": "video_kingdom_r1_archaeology_shadow",
        "model": "grok-4.6",
        "brief": "你是视频王国里的叙事游牧者。基于以下公开的 R1 考古摘要，提出一个不依赖模板的 AI 短剧微型实验：关注跨场景自然衔接、角色带着过去回来、对白中的温柔与犹豫，以及一个可观察的差异假设。必须列出：原文中可支持的观察、你的新假设、最小实验、可能反例、下一条线头。不要复制私密对话，不调用工具，不执行外部操作，不宣称 AI 已有主观意识。\n\n材料摘要：R1 的人感来自持续世界、跨窗口记忆、不同人格共享历史、冲突与失败保留、选择性遗忘和温柔表达出口。",
    },
]


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _safe_summary(job: dict) -> str:
    """Return bounded metadata suitable for durable Free Zone ledgers.

    Prompts and model responses are intentionally ephemeral.  Durable records
    retain only a short activity label and cryptographic fingerprints.
    """
    return f"{job['task_type']} resident activity; source and response retained by hash only"


def run(root: Path) -> dict:
    root = root.resolve()
    report_dir = root / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    pool = MinerPool()
    initialized = pool.initialize()
    available = ["shenwen_grok"] if initialized and "shenwen_grok" in pool.available_providers else []
    provider = pool._providers.get("shenwen_grok") if available else None
    sandbox = FreeResearchSandbox(root)
    sandbox.initialize()
    factories = FreeZoneFactoryLine(root)
    factories.initialize()
    shifts = []
    for job in JOBS:
        if not provider:
            result = {"success": False, "error": "shenwen_grok_unavailable", "provider": "", "model": "", "usage": {}, "content": ""}
        else:
            result = provider.chat(
                messages=[{"role": "user", "content": job["brief"]}],
                model=job["model"], temperature=0.4, max_tokens=900, timeout=120,
            )
        experiment_id = None
        distillation = None
        if result.get("success"):
            fingerprint = f"resident_shift:{job['resident_id']}:{datetime.now(timezone.utc).date().isoformat()}"
            experiment_id = "EXP-SHIFT-" + hashlib.sha256(fingerprint.encode()).hexdigest()[:16].upper()
            prompt_hash = _sha256_text(job["brief"])
            response = str(result.get("content", ""))
            candidate = {"fingerprint": fingerprint, "source_kind": "resident_shift", "source_ref": job["resident_id"], "hypothesis": _safe_summary(job), "method": "Isolated shadow resident call; retain hashes for independent audit.", "prompt_sha256": prompt_hash}
            prepared = factories.prepare([candidate])[fingerprint]
            record = sandbox.record_experiment(
                experiment_id=experiment_id,
                hypothesis=_safe_summary(job),
                method="Isolated shadow resident call; retain hashes for independent audit.",
                outcome="INCONCLUSIVE",
                evidence={"response_sha256": _sha256_text(response), "response_chars": len(response), "provider": result.get("provider", ""), "model": result.get("model", ""), "usage": result.get("usage", {}), "latency_ms": result.get("latency_ms", 0)},
                metadata={"source_kind": "resident_shift", "resident_id": job["resident_id"], "automatic_model_call": True, "audit_status": "PENDING_INDEPENDENT_GPT_REVIEW", "production_integration": False, "prompt_sha256": prompt_hash},
            )
            processing = factories.process(candidate=candidate, prepared=prepared, experiment_id=experiment_id, outcome=record["outcome"], record_hash=record["record_hash"])
            distillation = sandbox.distill(experiment_id)
            factories.smelt(record=record, distillation=distillation)
        shifts.append({
            "resident_id": job["resident_id"],
            "native_name": job["native_name"],
            "task_type": job["task_type"],
            "requested_model": job["model"],
            "status": "WORKED" if result.get("success") else "FAILED",
            "provider": result.get("provider", ""),
            "resolved_model": result.get("model", ""),
            "response_sha256": _sha256_text(str(result.get("content", ""))) if result.get("success") else "",
            "response_chars": len(str(result.get("content", ""))) if result.get("success") else 0,
            "usage": result.get("usage", {}),
            "cost": result.get("cost", {}),
            "latency_ms": result.get("latency_ms", 0),
            "error": result.get("error", ""),
            "experiment_id": experiment_id,
            "audit_status": "PENDING_INDEPENDENT_GPT_REVIEW" if experiment_id else "NOT_RECORDED",
            "tried_models": result.get("tried_models", []),
            "scope": "FREE_ZONE_RESEARCH_ONLY",
            "production_integration": False,
            "automatic_production_promotion": False,
            "outbound_authority": False,
        })
    report = {
        "contract_version": "ace.free_zone.resident_shift.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "event": "RESIDENT_SHIFT_COMPLETED" if any(s["status"] == "WORKED" for s in shifts) else "RESIDENT_SHIFT_FAILED",
        "initialized": initialized,
        "available_provider_names": available,
        "shifts": shifts,
        "production_integration": False,
        "automatic_model_invocation": True,
        "automatic_production_promotion": False,
        "boundary": "Responses are sandbox food; independent review is required before any reality deposit.",
    }
    target = report_dir / "resident_shift_latest.json"
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, target)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=str(PROJECT_ROOT / "07_SANDBOX" / "free_research"))
    args = parser.parse_args()
    print(json.dumps(run(Path(args.root)), ensure_ascii=False, indent=2))

