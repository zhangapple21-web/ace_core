#!/usr/bin/env python3
"""Run a small, local-only Astra/Terra paired evaluation.

The harness records request/response metadata and content hashes only.  It
does not persist prompts, responses, credentials, or provider request IDs.
This is evidence collection for a governed review, not a production switch.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


CASES = [
    ("architecture-boundary", "说明为什么协议兼容层、模型池和任务路由策略必须分开；给出两条故障隔离原则。"),
    ("capability-routing", "把‘任务→能力→劳动力’写成一个三步、可审计的调度规则，并说明默认模型与升级模型的关系。"),
    ("recovery-design", "设计一个模型请求失败后的有限重试与 Terra 回退流程，明确何时 fail-closed。"),
    ("config-review", "审查本地 3000 模型池与 3002 Responses 兼容入口的职责边界，列出一项不能互相推断的健康事实。"),
]


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _call(endpoint: str, model: str, prompt: str) -> dict:
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "只返回 JSON，键必须是 answer、risks、next_step。"},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 180,
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": "Bearer local-ace-oneapi-20260902",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = json.loads(response.read())
        elapsed = round((time.perf_counter() - started) * 1000)
        choices = payload.get("choices") or []
        content = ""
        if choices and isinstance(choices[0], dict):
            message = choices[0].get("message") or {}
            content = message.get("content") or ""
        try:
            parsed = json.loads(content)
            schema_ok = all(key in parsed for key in ("answer", "risks", "next_step"))
        except (TypeError, json.JSONDecodeError):
            schema_ok = False
        return {
            "status": 200,
            "success": bool(content),
            "schema_ok": schema_ok,
            "latency_ms": elapsed,
            "usage": payload.get("usage") or {},
            "content_sha256": _sha256(content) if content else "",
            "response_model": payload.get("model", ""),
        }
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError) as error:
        status = getattr(error, "code", None)
        return {
            "status": status or 0,
            "success": False,
            "schema_ok": False,
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "usage": {},
            "content_sha256": "",
            "response_model": "",
            "error_class": type(error).__name__,
        }


def run(endpoint: str, output: Path) -> dict:
    pairs = []
    for case_id, prompt in CASES:
        input_hash = _sha256(prompt)
        row = {
            "case_id": case_id,
            "input_sha256": input_hash,
            "models": {},
        }
        for model in ("gpt-6-astra", "gpt-5.6-terra"):
            row["models"][model] = _call(endpoint, model, prompt)
        pairs.append(row)

    all_success = all(
        result["success"]
        for pair in pairs
        for result in pair["models"].values()
    )
    all_schema = all(
        result["schema_ok"]
        for pair in pairs
        for result in pair["models"].values()
    )
    report = {
        "schema": "ace.astra-live-paired-evaluation.v1",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "endpoint": endpoint,
        "cases": len(pairs),
        "paired_success": all_success,
        "paired_schema_verification": all_schema,
        "cost_reconciliation": "UNKNOWN",
        "production_promotion": "BLOCKED_PENDING_30_PAIRED_CASES_AND_RECONCILED_BILL",
        "pairs": pairs,
        "limitations": [
            "small local evaluation set; not a 30-case promotion set",
            "schema verification is not semantic quality verification",
            "provider bill reconciliation was not available to this harness",
            "failure recovery is covered separately by the routing unit tests and remains unproven here with a live forced fault",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default="http://127.0.0.1:3000/v1/chat/completions")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "research" / "astra_live_paired_evaluation_20260908.json",
    )
    args = parser.parse_args()
    report = run(args.endpoint, args.output)
    print(json.dumps({
        "output": str(args.output),
        "cases": report["cases"],
        "paired_success": report["paired_success"],
        "paired_schema_verification": report["paired_schema_verification"],
        "production_promotion": report["production_promotion"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
