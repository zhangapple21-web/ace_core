"""Audit what instruction content ACE would send out, without sending it.

Answers three questions the gate cannot answer on its own:

  1. Which AGENTS.md files does this checkout ship, and is each one classified?
  2. From a given working directory, would a hosted call be allowed?
  3. Which call sites are currently blocked, and on what rule?

Read-only, no model call, no network. Exit code is non-zero when any call site
is blocked, so it can gate a check rather than only inform a human.

    python ops/audit_instruction_egress.py
    python ops/audit_instruction_egress.py --json
    python ops/audit_instruction_egress.py --workspace C:\\some\\dir --label probe
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.instruction_boundary import ace_root, survey_instruction_egress

DEFAULT_SITES = [
    {
        "label": "delivery stage cwd (production repository root)",
        "workspace": str(ace_root()),
    },
]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--workspace", help="an extra working directory to audit")
    parser.add_argument("--label", default="ad hoc", help="name for --workspace")
    args = parser.parse_args(argv)

    sites = list(DEFAULT_SITES)
    if args.workspace:
        sites.append({"label": args.label, "workspace": args.workspace})

    report = survey_instruction_egress(call_sites=sites)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(f"root            : {report['root']}")
        print(f"registry        : {report['registry']} "
              f"({'present' if report['registry_present'] else 'MISSING'})")
        print(f"shipped AGENTS.md: {report['repo_instruction_files']}")
        for item in report["classified"]:
            print(f"  [classified] {item['data_class']:11s} {item['path']}")
        for item in report["unclassified"]:
            print(f"  [UNCLASSIFIED]        {item['path']}")
        print("\ncall sites:")
        for site in report["call_sites"]:
            print(f"  {site['gate']:8s} {site['label']}")
            print(f"           workspace={site['workspace']} "
                  f"instruction_files={site['instruction_files']}")
            for reason in site["blocked"]:
                print(f"           blocked: {reason}")

    if report["unclassified"]:
        print("\nFAIL: shipped instruction files with no classification record")
    if report["egress_blocked"]:
        print("\nBLOCKED: at least one call site cannot egress")
    return 1 if (report["unclassified"] or report["egress_blocked"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())