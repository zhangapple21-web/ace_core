#!/usr/bin/env python3
"""Run 30 bounded Astra/Terra paired cases against the local model pool.

This is evidence collection only. Prompts and responses are not persisted;
only non-secret input/content hashes, status, usage and latency are recorded.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path


DOMAINS = [
    ("boundary", "说明协议兼容层、模型池和任务路由为什么必须分开，并给出两条隔离原则。"),
    ("routing", "把任务到能力到劳动力写成可审计的三步规则，并说明默认与升级关系。"),
    ("recovery", "设计模型失败后的有限重试、候选回退和 fail-closed 条件。"),
    ("config", "审查 3000 矿池和 3002 Responses 入口的职责边界，列出一项不可互相推断的事实。"),
    ("evidence", "区分目录可见、单次成功、能力验证、健康和生产晋升证据。"),
    ("governance", "为复杂模型候选设计一个不改变 Terra 默认的晋升门禁。"),
    ("watchdog", "说明 watchdog 应如何处理连续失败、确认探针、重启和恢复收据。"),
    ("fallback", "给出一个不重复尝试同一劳动力的顺序 fallback 算法。"),
    ("scope", "解释远端研究作用域与当前 Codex 控制面作用域为何必须分开。"),
    ("audit", "写一个最小运行审计清单，分别检查端口、目录、真实调用和收据。"),
]


def cases() -> list[tuple[str, str]]:
    rows = []
    for domain, prompt in DOMAINS:
        for variant in ("用四点回答，保留风险边界。", "用简洁 JSON 说明结论、风险和下一步。", "给出可执行但不越权的检查顺序。"):
            rows.append((f"{domain}-{len(rows)+1:02d}", prompt + variant))
    return rows


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def call(endpoint: str, model: str, prompt: str, timeout: int) -> dict:
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "只返回 JSON，键必须是 answer、risks、next_step。"},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": 96,
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": "Bearer local-ace-oneapi-20260902", "Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read())
        elapsed = round((time.perf_counter() - started) * 1000)
        choices = payload.get("choices") or []
        content = ""
        if choices and isinstance(choices[0], dict):
            content = str((choices[0].get("message") or {}).get("content") or "")
        parsed = None
        try:
            parsed = json.loads(content)
        except (TypeError, json.JSONDecodeError):
            pass
        schema_ok = isinstance(parsed, dict) and all(k in parsed for k in ("answer", "risks", "next_step"))
        return {
            "status": 200,
            "success": bool(content),
            "schema_ok": schema_ok,
            "latency_ms": elapsed,
            "usage": payload.get("usage") or {},
            "content_sha256": sha256(content) if content else "",
            "response_model": payload.get("model", ""),
        }
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError, OSError) as error:
        return {
            "status": getattr(error, "code", None) or 0,
            "success": False,
            "schema_ok": False,
            "latency_ms": round((time.perf_counter() - started) * 1000),
            "usage": {},
            "content_sha256": "",
            "response_model": "",
            "error_class": type(error).__name__,
        }


def run(endpoint: str, output: Path, timeout: int = 120) -> dict:
    def run_pair(item: tuple[str, str]) -> dict:
        case_id, prompt = item
        return {
            "case_id": case_id,
            "input_sha256": sha256(prompt),
            "models": {
                model: call(endpoint, model, prompt, timeout)
                for model in ("gpt-6-astra", "gpt-5.6-terra")
            },
        }

    # Two case workers keep the run bounded while avoiding a serial 20-minute
    # wall clock; each case still calls Astra then Terra sequentially.
    with ThreadPoolExecutor(max_workers=2) as executor:
        pairs = list(executor.map(run_pair, cases()))
    all_success = all(x["success"] for p in pairs for x in p["models"].values())
    all_schema = all(x["schema_ok"] for p in pairs for x in p["models"].values())
    report = {
        "schema": "ace.astra-live-paired-evaluation.v2",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "endpoint": endpoint,
        "cases": len(pairs),
        "paired_success": all_success,
        "paired_schema_verification": all_schema,
        "cost_reconciliation": "UNKNOWN",
        "production_promotion": "BLOCKED_PENDING_RECONCILED_BILL_AND_GOVERNED_ADMISSION",
        "pairs": pairs,
        "limitations": [
            "schema verification is not semantic quality verification",
            "provider bill reconciliation was not available to this harness",
            "this evaluates the 3000 Chat Completions pool; 3002 remains Responses-only compatibility ingress",
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--endpoint", default="http://127.0.0.1:3000/v1/chat/completions")
    parser.add_argument("--output", type=Path, default=Path(__file__).resolve().parents[1] / "research" / "astra_30_case_evaluation_20260908.json")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    report = run(args.endpoint, args.output, args.timeout)
    print(json.dumps({"output": str(args.output), "cases": report["cases"], "paired_success": report["paired_success"], "paired_schema_verification": report["paired_schema_verification"], "production_promotion": report["production_promotion"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
