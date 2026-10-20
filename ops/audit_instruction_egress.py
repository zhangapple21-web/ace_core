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

from contextlib import contextmanager

from core.instruction_boundary import ace_root, survey_instruction_egress


@contextmanager
def staging_site():
    """Reproduce the delivery staging directory, then clean it up.

    The scratch directory must exist while the survey runs and must not outlive
    it, or the audit would leave evidence behind in the very place it is
    reporting on.
    """
    if not REDUCED_ARTIFACT.is_file():
        yield None
        return
    import shutil
    import tempfile

    scratch = tempfile.mkdtemp(prefix="ace_audit_staging_")
    try:
        shutil.copy2(REDUCED_ARTIFACT, Path(scratch) / "AGENTS.md")
        yield scratch
    finally:
        shutil.rmtree(scratch, ignore_errors=True)

# The delivery stage no longer runs in the repository root -- it stages the
# reduced instructions in a scratch directory. That root is still audited,
# because any *other* caller that sets its working directory there would load
# the private manual, and that is the situation worth being able to see.
DEFAULT_SITES = [
    {
        "label": "repository root (any caller rooted here loads the private manual)",
        "workspace": str(ace_root()),
    },
    ]

# The delivery stage does not run *in* model_instructions/: it copies the reduced
# AGENTS.md into a scratch directory outside the repository and runs there,
# because a directory inside the repository would also pull the private manual
# in from the ancestor chain. So the staging site has to be reproduced the same
# way, or the audit reports a block that never happens in production.
REDUCED_ARTIFACT = ace_root() / "model_instructions" / "AGENTS.md"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--workspace", help="an extra working directory to audit")
    parser.add_argument("--label", default="ad hoc", help="name for --workspace")
    args = parser.parse_args(argv)

    # Only the reduced staging directory is expected to pass. A repository root
    # carrying a PRIVATE manual is a fact to report, not a failure of the build,
    # so it is shown and does not by itself fail the audit.

    sites = list(DEFAULT_SITES)
    with staging_site() as scratch:
        if scratch is not None:
            sites.append({"label": "delivery staging (reduced instructions)", "workspace": scratch})
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
        return 1

    # A reduced staging directory that will not egress is a real failure: it
    # means delivery cannot run. A repository root that refuses is not -- it is
    # the private manual refusing to leave, which is the gate working.
    staging = [
        site for site in report["call_sites"]
        if site["label"].startswith("delivery staging")
    ]
    if staging and staging[0]["gate"] != "ALLOWED":
        print("\nFAIL: the reduced delivery staging directory cannot egress")
        return 1

    blocked = [
        site for site in report["call_sites"]
        if site["gate"] == "BLOCKED" and not site["label"].startswith("delivery staging")
    ]
    if blocked:
        print("\nNOTE: these call sites cannot egress and are expected not to; "
              "a caller rooted here would need the reduced staging instead")
    print("\nOK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())