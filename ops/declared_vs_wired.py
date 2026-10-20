"""Declared-vs-wired audit for the constitution registry.

Why this exists
---------------
On 2026-10-05 this repository registered `ace.root.calculus` as L1/NORMATIVE while
`core/state_calculus.py` had zero importers outside its own test. Twenty minutes
earlier the same session had revoked `ace.admission.operator` for exactly that
property, using this judgment:

    a module referenced only by its own tests is more dangerous when registered as
    an authority than when absent, because it makes the system look like it already
    owns a capability when no decision path uses one.

The rule was written down and then not applied to the artifact created right after
it. Prose declarations do not prevent this, because the next edit does not re-read
the prose. So the judgment is encoded here instead.

What it checks
--------------
For every CURRENT/NORMATIVE registry entry that names a Python implementation:

  * find every real importer by AST, not by grep -- a docstring or a Mission name
    string that happens to contain the module name is not an import
  * classify the entry as WIRED, DECLARED_UNWIRED or PROSE_ONLY
  * fail when an entry is DECLARED_UNWIRED but is not acknowledged in
    DECLARED_UNWIRED below

Acknowledgement is required to be explicit and to carry a reason. That is the whole
point: an unwired authority must be a decision someone wrote down, not a default.

Prose-only authorities (PRINCIPLES.md, ARCHITECTURE.md, ROOT_STATE.md and friends)
have no implementation to find and are PROSE_ONLY by construction. They are not
required to be wired. Listing them as failures would train the reader to ignore the
output.

Usage
-----
    python ops/declared_vs_wired.py            # report, exit 1 on unacknowledged drift
    python ops/declared_vs_wired.py --report   # report, always exit 0
"""
from __future__ import annotations

import argparse
import ast
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.constitution_hierarchy import (  # noqa: E402
    assert_hierarchy_registry_ready,
    constitution_registry,
    validate_hierarchy_registry,
)

SKIP_DIRS = {".git", "__pycache__", "backups", ".venv", "node_modules", "backups_legacy"}
SOURCE_SUFFIXES = (".md", ".markdown")

# Authorities that are intentionally registered but unwired, each with the reason it
# is still registered rather than revoked or demoted.
#
# Keep this honest. Removing an entry here is the cheapest possible way to make this
# script green while leaving the underlying illusion in place; that is exactly the
# failure mode this file exists to catch.
DECLARED_UNWIRED = {
    "ace.root.calculus": (
        "core/state_calculus.py",
        "Registered because the user asked ACE to own a cross-domain computation "
        "mechanism, which requires it to be a declared authority rather than a "
        "local script. Zero production consumers is measured, not assumed: the only "
        "real importer is ops/test_state_calculus.py. The live input path cannot "
        "consume it yet because core/governance/knowledge_status.py:89 appends "
        "free-text strings while project() requires coordinates, so a live call "
        "returns CALCULUS_BLOCKED. Wiring needs an evidence schema migration, which "
        "is a separate governed Task. Declared in the spec §0.0 and in the registry "
        "entry summary so no reader can mistake it for a running capability.",
    ),
}


def _module_importers(module_rel: str) -> list:
    """Every file that genuinely imports `module_rel`, by AST.

    Grep is not sufficient here and would have produced false positives: the module
    name appears inside a docstring and inside a Mission name string in
    ops/mission_runner.py without either being an import.
    """
    module_name = module_rel[:-3].replace("/", ".").replace("\\", ".")
    found = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if not name.endswith(".py"):
                continue
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path, ROOT).replace("\\", "/")
            if rel == module_rel:
                continue
            try:
                tree = ast.parse(io.open(path, encoding="utf-8", errors="replace").read())
            except (SyntaxError, ValueError, OSError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    if (node.module or "") == module_name or (
                        node.module or ""
                    ).endswith("." + module_name):
                        found.append(rel)
                        break
                elif isinstance(node, ast.Import):
                    if any(a.name == module_name or a.name.endswith("." + module_name)
                           for a in node.names):
                        found.append(rel)
                        break
    return sorted(set(found))


def _implementation_in(entry) -> str:
    """The Python module a spec names as its implementation, if it names one."""
    try:
        body = io.open(os.path.join(ROOT, entry["source"]), encoding="utf-8",
                       errors="replace").read()
    except OSError:
        return ""
    import re

    for match in re.finditer(r"`((?:core|ops)/[A-Za-z0-9_/]+\.py)`", body):
        candidate = match.group(1)
        if os.path.exists(os.path.join(ROOT, candidate)):
            return candidate
    return ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", action="store_true",
                        help="always exit 0, print the table only")
    args = parser.parse_args()

    validation = validate_hierarchy_registry()
    if validation["status"] != "READY":
        print("registry is %s: %s" % (validation["status"], validation["errors"]))
        return 1
    assert_hierarchy_registry_ready()

    rows = []
    for entry in constitution_registry():
        if entry["status"] != "CURRENT" or entry["authority"] == "REFERENCE":
            continue
        impl = _implementation_in(entry)
        if not impl:
            rows.append((entry["id"], "-", "-", "PROSE_ONLY", ""))
            continue
        importers = _module_importers(impl)
        tests_only = all(
            "/test_" in p or p.startswith("test_") or "/tests/" in p
            for p in importers
        ) if importers else True
        if not importers:
            verdict = "DECLARED_UNWIRED"
        elif tests_only:
            verdict = "TESTS_ONLY"
        else:
            verdict = "WIRED"
        rows.append((entry["id"], impl, str(len(importers)), verdict, ",".join(importers[:3])))

    width = max(len(r[0]) for r in rows) if rows else 10
    print("%-*s  %-34s %6s  %-16s %s" % (width, "REGISTRY ID", "IMPLEMENTATION", "IMPS",
                                          "VERDICT", "IMPORTERS"))
    print("-" * (width + 80))
    for entry_id, impl, imps, verdict, sample in sorted(rows, key=lambda r: r[3]):
        print("%-*s  %-34s %6s  %-16s %s" % (width, entry_id, impl, imps, verdict, sample))

    unacknowledged = [
        r for r in rows
        if r[3] in {"DECLARED_UNWIRED", "TESTS_ONLY"}
        and r[0] not in DECLARED_UNWIRED
    ]
    print("")
    if unacknowledged:
        print("UNACKNOWLEDGED declared-but-unwired authorities: %d" % len(unacknowledged))
        for entry_id, impl, imps, verdict, _ in unacknowledged:
            print("  %s -> %s (%s importers, %s)" % (entry_id, impl, imps, verdict))
        print("")
        print("Either wire it, or record it in DECLARED_UNWIRED in")
        print("ops/declared_vs_wired.py with the reason it is still registered.")
        return 0 if args.report else 1

    print("No unacknowledged declared-but-unwired authorities.")
    print("%d entries audited; %d are wired, %d are prose-only."
          % (len(rows),
             sum(1 for r in rows if r[3] == "WIRED"),
             sum(1 for r in rows if r[3] == "PROSE_ONLY")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())