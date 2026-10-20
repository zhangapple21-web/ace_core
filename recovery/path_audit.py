#!/usr/bin/env python3
"""检查恢复入口和运行时关键模块是否藏有机器专属绝对路径。"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ABSOLUTE_WINDOWS = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]")
CRITICAL_FILES = (
    "portable_paths.py",
    "recovery/bootstrap.py",
    "recovery/restore_from_remote.py",
    "recovery/bootstrap.ps1",
    "recovery/restore_from_remote.ps1",
    "ace.py",
    "ace_daemon.py",
    "core/config.py",
    "core/llm/client.py",
    "core/governance/evolution_planner.py",
    "core/stock_dialogue_context.py",
)


def audit(workspace: Path) -> dict:
    findings: list[dict] = []
    for relative in CRITICAL_FILES:
        path = workspace / relative
        if not path.is_file():
            findings.append({"path": relative, "kind": "missing", "severity": "fail"})
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for line_no, line in enumerate(text.splitlines(), 1):
            if ABSOLUTE_WINDOWS.search(line):
                findings.append({"path": relative, "line": line_no, "text": line.strip(), "severity": "fail"})
    imports = {
        "bootstrap": "from portable_paths import",
        "restore": "from portable_paths import",
    }
    for name, needle in imports.items():
        relative = "recovery/bootstrap.py" if name == "bootstrap" else "recovery/restore_from_remote.py"
        path = workspace / relative
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        if needle not in text:
            findings.append({"path": relative, "kind": "portable_paths_not_imported", "severity": "fail"})
    return {
        "schema": "ace.portable_path_audit.v1",
        "workspace": str(workspace),
        "status": "PASS" if not findings else "FAIL",
        "critical_files": list(CRITICAL_FILES),
        "findings": findings,
        "note": "历史考古/证据文本可以保留旧路径；本门禁只约束当前执行链关键文件。",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    result = audit(args.workspace_root.expanduser().resolve())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
