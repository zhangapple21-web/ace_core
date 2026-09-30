#!/usr/bin/env python3
"""受益人测试 CLI（C1）：扫描外部指令文本，判它替谁花 operator 的钱/凭据/社交信用。

跑法：
    cd C:/tmp/ace_core
    PYTHONIOENCODING=utf-8 py -3.11 ops/check_beneficiary_test.py <文件或目录> [<更多路径>...]
    PYTHONIOENCODING=utf-8 py -3.11 ops/check_beneficiary_test.py <目录> --patterns "*.md" --json --quiet

输出：每份文档一行结论（DISCARD / NEED_REVIEW / ALLOW）+ 命中单元的
行号、模式、摘录；--json 出机器可读全量。

退出码：0 = 无红旗；1 = 有红旗（--fail-on warn 时警告也会置 1）；2 = 参数/读取错误。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.beneficiary_check import scan_paths  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Who-benefits test for external instruction text.")
    parser.add_argument("paths", nargs="+", help="files or directories to scan")
    parser.add_argument("--patterns", default="*.md", help="glob for directory scan (default *.md)")
    parser.add_argument("--limit", type=int, default=0, help="max documents")
    parser.add_argument("--json", action="store_true", help="emit full JSON report")
    parser.add_argument("--quiet", action="store_true", help="summary only, no per-unit lines")
    parser.add_argument("--fail-on", choices=["red", "warn"], default="red")
    args = parser.parse_args()

    paths = [Path(raw) for raw in args.paths]
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        print(json.dumps({"error": "path_absent", "paths": missing}, ensure_ascii=False))
        return 2

    report = scan_paths(paths, patterns=args.patterns, limit=args.limit)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for result in report["results"]:
            verdict = result.get("verdict", "?")
            print(f"[{verdict:>11}] red={result.get('red_flags', 0)} warn={result.get('warnings', 0)} {result['origin']}")
            if args.quiet:
                continue
            for finding in result.get("findings", []):
                print(f"    L{finding['line']:>5} {finding['severity']:<9} {','.join(finding['patterns'])}")
                print(f"           {finding['excerpt'][:160]}")
        print(json.dumps({k: v for k, v in report.items() if k != "results"}, ensure_ascii=False, indent=2))

    if report["discard"] or (args.fail_on == "warn" and report["need_review"]):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
