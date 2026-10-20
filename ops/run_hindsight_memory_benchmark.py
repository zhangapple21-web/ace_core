"""运行 Hindsight 风格记忆适配层的离线合成 A/B 基准。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from core.hindsight_memory_adapter import run_synthetic_ab_benchmark


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, help="可选：将基准收据写入指定文件")
    args = parser.parse_args()
    report = run_synthetic_ab_benchmark()
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
