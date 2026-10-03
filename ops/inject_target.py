#!/usr/bin/env python3
"""外部目标注入脚本：把一个 ace.target.inject.v1 JSON 转成必须交付物理文件的 Task。

用法：
    python ops/inject_target.py --json '{"protocol":"ace.target.inject.v1",...}'
    python ops/inject_target.py --file target.json
    cat target.json | python ops/inject_target.py --stdin
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.task import TaskPool  # noqa: E402

PROTOCOL = "ace.target.inject.v1"
ALLOWED_METRICS = {"file_exists_nonempty", "user_accepted", "schema_valid_json", "tests_pass"}
ALLOWED_OUTPUT_EXTS = {".md", ".json", ".py", ".txt", ".csv", ".yaml", ".yml"}
ALLOWED_PRIORITIES = {"low", "medium", "high", "critical"}
ALLOWED_DOMAINS = {"document", "code", "analysis", "other"}


def validate_target(payload: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["payload_must_be_object"]
    if payload.get("protocol") != PROTOCOL:
        errors.append("protocol_mismatch")
    if not payload.get("title") or not isinstance(payload["title"], str) or len(payload["title"]) > 200:
        errors.append("title_required_or_too_long")
    expected = payload.get("expected_output")
    if not expected or not isinstance(expected, str):
        errors.append("expected_output_required")
    elif Path(expected).suffix.lower() not in ALLOWED_OUTPUT_EXTS:
        errors.append("expected_output_must_be_physical_file")
    metric = payload.get("success_metric")
    if metric not in ALLOWED_METRICS:
        errors.append("success_metric_invalid")
    priority = payload.get("priority", "medium")
    if priority not in ALLOWED_PRIORITIES:
        errors.append("priority_invalid")
    domain = payload.get("domain", "other")
    if domain not in ALLOWED_DOMAINS:
        errors.append("domain_invalid")
    tags = payload.get("tags", [])
    if not isinstance(tags, list) or any(not isinstance(t, str) for t in tags):
        errors.append("tags_must_be_string_list")
    return errors


def inject(payload: dict) -> dict:
    title = str(payload["title"]).strip()
    hypothesis = str(payload.get("hypothesis", "")).strip()
    expected_output = str(payload["expected_output"]).strip().replace("\\", "/")
    success_metric = str(payload["success_metric"]).strip()
    priority = str(payload.get("priority", "medium")).strip()
    domain = str(payload.get("domain", "other")).strip()
    why_now = str(payload.get("why_now", "external_target_injected")).strip()
    tags = list(payload.get("tags", []))
    for tag in ("external_target", "delivery:physical"):
        if tag not in tags:
            tags.append(tag)

    pool = TaskPool(str(ROOT / "task_pool"))
    admission = {
        "source_type": "external_target",
        "source_ref": expected_output,
        "why_now": why_now,
        "evidence": [{"content": "external_target_injection", "source": "inject_target"}],
        "expected_result": expected_output,
        "verification_method": success_metric,
        "risk": "low",
        "estimated_scope": "single_delivery",
    }
    outputs = {
        "delivery": {
            "required_path": expected_output,
            "success_metric": success_metric,
            "domain": domain,
        }
    }
    task = pool.create_task(
        title=title,
        hypothesis=hypothesis,
        priority=priority,
        tags=tags,
        admission=admission,
        outputs=outputs,
    )
    return {
        "task_id": task.task_id,
        "status": task.status,
        "title": task.title,
        "expected_output": expected_output,
        "success_metric": success_metric,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inject an external target into ACE task pool.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--json", help="inline JSON payload")
    group.add_argument("--file", help="path to JSON file")
    group.add_argument("--stdin", action="store_true", help="read JSON from stdin")
    args = parser.parse_args(argv)

    try:
        if args.json is not None:
            raw = args.json
        elif args.file is not None:
            raw = Path(args.file).read_text(encoding="utf-8")
        else:
            raw = sys.stdin.read()
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"status": "ERROR", "error": f"invalid_json:{exc}"}, ensure_ascii=False))
        return 2

    errors = validate_target(payload)
    if errors:
        print(json.dumps({"status": "ERROR", "errors": errors}, ensure_ascii=False))
        return 2

    try:
        result = inject(payload)
    except Exception as exc:
        print(json.dumps({"status": "ERROR", "error": f"inject_failed:{type(exc).__name__}:{exc}"}, ensure_ascii=False))
        return 1

    print(json.dumps({"status": "OK", **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
