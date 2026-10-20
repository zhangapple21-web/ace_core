#!/usr/bin/env python3
"""一阶尺子检查器（OpenStall 考古 · M2/M3/M4/M6/M7 空转的共性规律）。

尺子本体：
    凡是需要交易对手（或消费者、订阅方）去执行的环节，实测全部空转或已坏；
    凡是执行方自己能强制的环节（服务端状态机、形状校验、越权拒绝），全部工作。
    —— 所以吸收任何外部机制之前，先问：这条机制由谁强制执行？
       该执行方式要么有"自己就能跑"的载体，要么给对手方依赖配清道者与救济口。

输入：机制声明文件（.yaml / .json / .md，md 里的 fenced yaml 块与含
      enforced_by 列的表格都会被解析）。每条机制字段：
        id / name
        enforced_by            self | counterparty | third_party_server（必填）
        status                 DISCOVERED | CANDIDATE | VERIFIED | ACCEPTED（选填）
        carrier                真正执行这条机制的命令或文件路径
        sweeper                谁在超时后清扫停滞状态（对手方依赖必填）
        remedy_in_counterparty_hand  救济是否写在对手方客户端里（bool）
        absorption             是否已/准备吸收进自有系统（bool）
        evidence               活指针列表 [{type: file, path: ...}]

输出：每条机制一行判定 PASS / WARN / REJECT + 理由码；stdout 出 JSON。
退出码：0 = 无 REJECT；1 = 有 REJECT；2 = 输入错误。

跑法：
    cd C:/tmp/ace_core
    PYTHONIOENCODING=utf-8 py -3.11 ops/check_external_mechanism_safety.py ops/external_mechanism_safety.sample.yaml
    PYTHONIOENCODING=utf-8 py -3.11 ops/check_external_mechanism_safety.py <清单文件> --quiet
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.task_ledger import resolve_ref  # noqa: E402

VALID_ENFORCERS = {"self", "counterparty", "third_party_server"}
VALID_STATUS = {"DISCOVERED", "CANDIDATE", "VERIFIED", "ACCEPTED"}
NO_SWEEPER = {"", "none", "n/a", "na", "-", "no", "无"}
YAML_BLOCK = re.compile(r"```ya?ml\s*\n(.*?)```", re.S | re.I)


def _load_structured(text: str) -> List[Dict[str, Any]]:
    mechanisms: List[Dict[str, Any]] = []
    try:
        import yaml  # type: ignore
    except ImportError:
        yaml = None  # JSON 仍可用；yaml 缺失时 md/yaml 输入会给出明确错误

    stripped = text.strip()
    if stripped.startswith("{") or stripped.startswith("["):
        data = json.loads(stripped)
        if isinstance(data, dict):
            data = data.get("mechanisms", [])
        return [row for row in data if isinstance(row, dict)]

    chunks: List[str] = []
    for match in YAML_BLOCK.finditer(text):
        chunks.append(match.group(1))
    if not chunks and yaml is not None:
        chunks.append(text)

    parse_errors: List[str] = []
    for index, chunk in enumerate(chunks):
        if yaml is None:
            parse_errors.append(f"pyyaml_absent:chunk_{index}")
            continue
        try:
            loaded = yaml.safe_load(chunk)
        except Exception as error:
            parse_errors.append(f"yaml_error:chunk_{index}:{error}")
            continue
        if isinstance(loaded, dict):
            loaded = loaded.get("mechanisms", [])
        if isinstance(loaded, list):
            mechanisms.extend(row for row in loaded if isinstance(row, dict))

    if not mechanisms:
        mechanisms.extend(_rows_from_markdown_tables(text))
    if not mechanisms and parse_errors:
        raise ValueError("mechanism_declaration_unparsable:" + " | ".join(parse_errors)[:400])
    return mechanisms


def _rows_from_markdown_tables(text: str) -> List[Dict[str, Any]]:
    """解析含 enforced_by 列的 markdown 表格。"""
    rows: List[Dict[str, Any]] = []
    lines = text.splitlines()
    header: Optional[List[str]] = None
    for line in lines:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if "enforced_by" in cells:
            header = cells
            continue
        if header and line.strip().startswith("|") and set(line.replace("|", "").replace(" ", "")) <= {"-"}:
            continue
        if header and line.strip().startswith("|") and len(cells) == len(header):
            row = {}
            for key, value in zip(header, cells):
                if value.lower() in {"true", "false"}:
                    row[key] = value.lower() == "true"
                else:
                    row[key] = value
            rows.append(row)
    return rows


def _carrier_resolves(carrier: str) -> bool:
    command = str(carrier or "").strip()
    if not command:
        return False
    first = command.split()[0]
    candidate = Path(first)
    if not candidate.is_absolute():
        candidate = ROOT / first
    if candidate.exists():
        return True
    if first.endswith((".py", ".sh", ".mjs", ".js")):
        return False
    return shutil.which(first) is not None


def _check_mechanism(row: Dict[str, Any]) -> Dict[str, Any]:
    rejects: List[str] = []
    warns: List[str] = []
    enforcer = str(row.get("enforced_by") or "").strip().lower()
    status = str(row.get("status") or "").strip().upper()
    carrier = str(row.get("carrier") or "").strip()
    sweeper = str(row.get("sweeper") or "").strip()
    remedy = bool(row.get("remedy_in_counterparty_hand"))
    absorption = bool(row.get("absorption"))
    evidence = row.get("evidence") or []

    if enforcer not in VALID_ENFORCERS:
        return {
            "id": str(row.get("id") or "?"),
            "enforced_by": enforcer or "MISSING",
            "verdict": "REJECT",
            "reasons": ["unclassified_enforcement"],
            "detail": "机制必须先声明由谁强制执行；没声明 = 不许吸收",
        }
    if status and status not in VALID_STATUS:
        warns.append(f"unknown_status:{status}")

    if enforcer in ("self", "counterparty"):
        if not carrier:
            rejects.append("no_carrier_criterion_S27")
        elif not _carrier_resolves(carrier):
            rejects.append(f"carrier_dead:{carrier.split()[0]}")

    if enforcer == "third_party_server":
        proved = False
        for pointer in evidence if isinstance(evidence, list) else []:
            if isinstance(pointer, dict):
                ok, _ = resolve_ref(pointer)
                if ok:
                    proved = True
                    break
        if not proved:
            rejects.append("server_enforcement_unproven")

    if enforcer == "counterparty":
        if sweeper.strip().lower() in NO_SWEEPER:
            rejects.append("counterparty_without_sweeper")
        if absorption and status not in ("VERIFIED", "ACCEPTED"):
            warns.append("premature_absorption")
    if remedy and enforcer != "self":
        rejects.append("remedy_in_counterparty_hand")

    for pointer in evidence if isinstance(evidence, list) else []:
        if isinstance(pointer, dict):
            ok, error = resolve_ref(pointer)
            if not ok:
                warns.append(error)

    verdict = "REJECT" if rejects else ("WARN" if warns else "PASS")
    return {
        "id": str(row.get("id") or "?"),
        "name": str(row.get("name") or "")[:80],
        "enforced_by": enforcer,
        "status": status or None,
        "carrier": carrier or None,
        "sweeper": sweeper or None,
        "verdict": verdict,
        "reasons": rejects + warns,
    }


def check_text(text: str, origin: str = "<text>") -> Dict[str, Any]:
    rows = _load_structured(text)
    results = [_check_mechanism(row) for row in rows]
    totals = {
        "total": len(results),
        "pass": sum(1 for r in results if r["verdict"] == "PASS"),
        "warn": sum(1 for r in results if r["verdict"] == "WARN"),
        "reject": sum(1 for r in results if r["verdict"] == "REJECT"),
    }
    return {"origin": origin, "parsed_mechanisms": len(rows) > 0, "totals": totals, "mechanisms": results}


def main() -> int:
    parser = argparse.ArgumentParser(description="First-order enforcement ruler for external mechanisms.")
    parser.add_argument("inputs", nargs="+", help="yaml/json/md mechanism declarations")
    parser.add_argument("--quiet", action="store_true", help="totals only")
    args = parser.parse_args()

    combined: List[Dict[str, Any]] = []
    reject = False
    for raw in args.inputs:
        path = Path(raw)
        if not path.exists():
            print(json.dumps({"error": f"input_absent:{path}"}, ensure_ascii=False))
            return 2
        try:
            report = check_text(path.read_text(encoding="utf-8", errors="replace"), origin=str(path))
        except (json.JSONDecodeError, ValueError) as error:
            print(json.dumps({"error": f"input_unparsable:{path}:{error}"}, ensure_ascii=False))
            return 2
        combined.append(report)
        if report["totals"]["reject"]:
            reject = True
        if not report["parsed_mechanisms"]:
            print(json.dumps({"warning": f"no_mechanisms_parsed:{path}"}, ensure_ascii=False))

    if args.quiet:
        print(json.dumps({"files": [
            {"origin": r["origin"], **r["totals"]} for r in combined
        ]}, ensure_ascii=False, indent=2))
    else:
        print(json.dumps({"files": combined}, ensure_ascii=False, indent=2))
    return 1 if reject else 0


if __name__ == "__main__":
    raise SystemExit(main())
