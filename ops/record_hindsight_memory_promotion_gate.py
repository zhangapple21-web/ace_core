"""Record the governed promotion decision for the Hindsight-style adapter.

The adapter is intentionally evaluated as a candidate default retrieval path.
The receipt remains separate from the benchmark and records why a measurable
recall gain is not enough to promote when latency regresses.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.closed_loop_engine import ClosedLoopEngine
from core.hindsight_memory_adapter import run_synthetic_ab_benchmark


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="ACE root used for the governed receipt",
    )
    parser.add_argument("--output", type=Path, help="Optional UTF-8 receipt output path")
    args = parser.parse_args()
    report = run_synthetic_ab_benchmark()
    baseline = {
        "recall": report["baseline_hit_rate"],
        "mrr": report["baseline_mrr"],
        "precision_at_3": report["baseline_precision_at_3"],
        "latency_ms": report["baseline_median_latency_ms"],
    }
    changed = {
        "recall": report["adapter_hit_rate"],
        "mrr": report["adapter_mrr"],
        "precision_at_3": report["adapter_precision_at_3"],
        "latency_ms": report["adapter_median_latency_ms"],
    }
    painful_review = {
        "cost": "默认检索会增加计算时间；适配器本身没有网络或模型费用",
        "counterfactual": "若不保留适配器，ACE 对概念、时间和同义问题的召回仍可能漏检",
        "recurrence_risk": "中；若直接默认启用，低延迟场景可能回归",
        "reusable_lesson": "召回改善必须和延迟、边界泄漏、重复抑制一起评估；只读候选层优先",
        "retain": True,
    }
    engine = ClosedLoopEngine(args.base_dir)
    receipt = engine.run_cycle(
        observation={
            "source": "synthetic_hindsight_style_ab",
            "status": report["status"],
            "production_integration": False,
        },
        objective="评估 Hindsight 风格适配器是否可以成为 ACE 默认记忆检索路径",
        baseline=baseline,
        changed=changed,
        painful_review=painful_review,
        directions={
            "recall": "higher",
            "mrr": "higher",
            "precision_at_3": "higher",
            "latency_ms": "lower",
        },
        change={
            "adapter": "core.hindsight_memory_adapter.HindsightStyleRetriever",
            "mode": "opt_in_read_only",
            "external_model_calls": report["external_model_calls"],
            "network_calls": report["network_calls"],
        },
    )
    output = {
        "contract_version": "ace.hindsight_memory_promotion_gate.v1",
        "benchmark_receipt": report,
        "closed_loop_receipt": receipt,
        "default_path_changed": False,
        "production_integration": False,
    }
    rendered = json.dumps(output, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if receipt["decision"] == "ROLLBACK_REQUIRED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
