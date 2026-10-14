"""Find ACE components that are defined but never wired.

This defect class has recurred three times now - MengpoAutoTrigger with zero
call sites, the reflection relay's unbounded admission, and the ledger's
unreachable drift gate. Each was invisible because nobody asked the question
mechanically. This asks it.

"Defined but unused" is not automatically a defect: a module may be a library,
a staged candidate, or deliberately held. So each hit is reported with its
category rather than condemned, and the ones worth acting on say why.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(r"C:\tmp/ace_core")
SCAN_DIRS = ["core", "ops", "ace_daemon.py", "ace.py"]

#: Names that are documented as deliberately unwired. A hit here is expected
#: and is not reported as a finding.
KNOWN_UNWIRED = {
    "RoundTable": "AGENTS.md: historical, not wired; roles are separate wired lifecycle roles",
    "MengpoAutoTrigger": "Mengpo's auto-trigger: never wired (now diagnosed, see mengpo_runtime)",
}


def defined_names(path: Path) -> set[str]:
    """Top-level classes and functions this module defines."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return set()
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    names.add(target.id)
    return names


def referenced_names(path: Path) -> set[str]:
    """Every Name/Attribute load in this file, i.e. what it uses."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return set()
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    return names


def main() -> int:
    files: list[Path] = []
    for entry in SCAN_DIRS:
        target = ROOT / entry
        if target.is_file():
            files.append(target)
        elif target.is_dir():
            files.extend(sorted(target.rglob("*.py")))

    definitions: dict[str, list[Path]] = {}
    for path in files:
        for name in defined_names(path):
            definitions.setdefault(name, []).append(path)

    # every name used anywhere, so a definition is "used" if any other file
    # mentions it - not just imports it, because attribute access counts too
    usage: dict[str, set[str]] = {}
    for path in files:
        for name in referenced_names(path):
            usage.setdefault(name, set()).add(str(path.relative_to(ROOT)))

    out = []
    unused = []
    for name, paths in sorted(definitions.items()):
        if len(paths) > 1:
            continue  # defined more than once: not a dead-definition question
        defining_file = paths[0]
        # A name used anywhere - including inside its own module - is in use.
        # Module-level constants are normally consumed by the module that
        # defines them, and discarding that file turns every healthy constant
        # into a phantom dead component.
        users = usage.get(name) or set()
        if users:
            continue
        category = "KNOWN_UNWIRED" if name in KNOWN_UNWIRED else "NOT_REFERENCED"
        unused.append((name, str(defining_file.relative_to(ROOT)), category))

    out.append(f"python files scanned : {len(files)}")
    out.append(f"top-level definitions: {len(definitions)}")
    out.append(f"never referenced     : {len(unused)}")
    out.append("")
    for category in ("NOT_REFERENCED", "KNOWN_UNWIRED"):
        hits = [u for u in unused if u[2] == category]
        if not hits:
            continue
        out.append(f"--- {category} ({len(hits)}) ---")
        for name, path, _ in hits[:40]:
            note = KNOWN_UNWIRED.get(name, "")
            out.append(f"  {name:44s} {path}{'  # ' + note if note else ''}")
        out.append("")

    text = "\n".join(out)
    Path(r"C:\tmp/dead_components.txt").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())