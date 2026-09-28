"""离线运行 Memory Kernel 的可恢复性和晋升门自检。"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from core.memory_kernel import MemoryKernel


def run(output: Path | None = None) -> dict:
    with tempfile.TemporaryDirectory(prefix="ace-memory-kernel-") as temp_dir:
        root = Path(temp_dir) / "kernel"
        kernel = MemoryKernel(root, bank="ace")
        unknown = kernel.capture(
            content="真实结果尚未回读，保持未知",
            title="待核观察",
            memory_type="OBSERVATION",
            claim_key="selfcheck.unknown",
            data_class="STRUCTURE",
            source_refs=["selfcheck://unknown"],
            scope="selfcheck",
        )
        candidate = kernel.capture(
            content="检索必须同时保留时间和来源边界",
            title="记忆检索",
            memory_type="CAPABILITY_CANDIDATE",
            claim_key="selfcheck.retrieval_boundary",
            data_class="CAPABILITY",
            source_refs=["selfcheck://baseline"],
            evidence_refs=["selfcheck://test"],
            scope="selfcheck",
        )
        kernel.verify(
            candidate["id"],
            {
                "receipt_id": "selfcheck://verification",
                "source_refs": ["selfcheck://test"],
                "result": "PASS",
                "reviewer": "selfcheck",
            },
        )
        kernel.promote_capability(
            candidate["id"],
            {
                "decision": "PROMOTE",
                "baseline": {"retrieval_recall": 0.5},
                "change": {"retrieval_recall": 1.0},
                "test": {"status": "PASS"},
                "evaluation": {"regression": False},
                "compare": {"improved": True},
                "independent_evidence_groups": [["selfcheck://test"], ["selfcheck://verification"]],
                "painful_review": {
                    "cost": "自检样本构造成本",
                    "impact": "若无边界会污染跨窗口召回",
                    "counterfactual": "会把未知误报为事实",
                    "recurrence_risk": "低",
                    "lesson": "所有召回先过范围和证据门",
                    "reuse_conditions": "仅用于受治理内存查询",
                },
            },
        )
        query = kernel.query("时间 来源", scope="selfcheck")
        state = kernel.project_current_state(scope="selfcheck")
        recovered = MemoryKernel(root, bank="ace")
        report = {
            "contract_version": "ace.memory_kernel.v1",
            "status": "PASS" if recovered.integrity_report()["valid"] and unknown["id"] in recovered._records and query["results"] else "REVIEW_REQUIRED",
            "record_ids": sorted(recovered._records),
            "query_result_count": len(query["results"]),
            "unknown_count": len(state["unknowns"]),
            "accepted_capability_count": len([item for item in state["verified"] if item.get("memory_type") == "CAPABILITY_ACCEPTED"]),
            "integrity": recovered.integrity_report(),
            "execution_authorized": False,
            "production_integration": False,
            "promotion": False,
        }
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run(args.output)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
