#!/usr/bin/env python3
"""Read-only code health audit for an ACE checkout.

Reports, without writing or mutating anything:

1. syntax parse errors (BOM-tolerant, matching the CPython tokenizer);
2. duplicate top-level definitions inside a single file;
3. duplicate method names inside a single class;
4. unresolved in-repo ``core.*`` / ``ops.*`` imports;
5. byte-identical duplicate files (md5);
6. near-duplicate file pairs (Jaccard over normalized code lines);
7. silent exception swallows (``except Exception: pass`` / bare ``except:``).

Usage:
    python ops/code_health_audit.py [--root PATH] [--jaccard 0.60] [--json]

This is an observation tool.  It never edits, deletes, or rewrites a file and
never touches TaskPool, runtime state, or any governed ledger.
"""

from __future__ import annotations

import argparse
import ast
import collections
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

SKIP_DIRS = {".git", ".cline-home", "__pycache__", ".venv", "venv", "node_modules"}


def iter_python_files(root: Path) -> Iterable[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in sorted(filenames):
            if name.endswith(".py"):
                yield Path(dirpath) / name


def read_source(path: Path) -> str:
    """Decode like CPython does: a leading UTF-8 BOM is not an error."""
    return path.read_text(encoding="utf-8-sig", errors="replace")


def parse_trees(root: Path) -> Tuple[Dict[str, ast.Module], List[Dict[str, Any]]]:
    trees: Dict[str, ast.Module] = {}
    errors: List[Dict[str, Any]] = []
    for path in iter_python_files(root):
        rel = str(path.relative_to(root))
        try:
            trees[rel] = ast.parse(read_source(path), filename=rel)
        except SyntaxError as exc:
            errors.append({"file": rel, "line": exc.lineno, "error": str(exc)})
    return trees, errors


def _top_level_names(tree: ast.Module) -> Dict[str, List[int]]:
    seen: Dict[str, List[int]] = collections.defaultdict(list)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            seen[node.name].append(node.lineno)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    seen[target.id].append(node.lineno)
    return {k: v for k, v in seen.items() if len(v) > 1}


def _duplicate_methods(tree: ast.Module) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        seen: Dict[str, List[int]] = collections.defaultdict(list)
        for sub in node.body:
            if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                seen[sub.name].append(sub.lineno)
        for name, lines in seen.items():
            if len(lines) > 1:
                out.append({"class": node.name, "method": name, "lines": lines})
    return out


def _module_exports(tree: ast.Module) -> set:
    names: set = set()

    def collect(body: List[ast.stmt]) -> None:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        names.add(target.id)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    names.add(alias.asname or alias.name.split(".")[0])
            elif isinstance(node, ast.If):
                collect(node.body)
                collect(node.orelse)
            elif isinstance(node, ast.Try):
                collect(node.body)
                collect(node.orelse)
                collect(node.finalbody)
                for handler in node.handlers:
                    collect(handler.body)
            elif isinstance(node, (ast.With, ast.AsyncWith)):
                collect(node.body)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names.add(node.target.id)

    collect(tree.body)
    return names


def unresolved_imports(root: Path, trees: Dict[str, ast.Module]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for rel, tree in trees.items():
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or not node.module:
                continue
            module = node.module
            if not (module == "core" or module.startswith(("core.", "ops."))):
                continue
            if any(alias.name == "*" for alias in node.names):
                continue
            target = root.joinpath(*module.split("."))
            pkg_init = target / "__init__.py"
            module_file = target.with_suffix(".py")
            if pkg_init.exists():
                continue
            if not module_file.exists():
                out.append({"file": rel, "line": node.lineno, "problem": f"module missing: {module}"})
                continue
            try:
                sub_tree = ast.parse(read_source(module_file), filename=str(module_file))
            except SyntaxError:
                continue
            exported = _module_exports(sub_tree)
            for alias in node.names:
                if alias.name not in exported:
                    out.append({
                        "file": rel,
                        "line": node.lineno,
                        "problem": f"{module}.{alias.name} not defined at module level",
                    })
    return out


def duplicate_files(root: Path) -> List[Dict[str, Any]]:
    digests: Dict[str, List[str]] = collections.defaultdict(list)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            path = Path(dirpath) / name
            try:
                data = path.read_bytes()
            except OSError:
                continue
            if not data:
                continue
            digests[hashlib.md5(data).hexdigest()].append(str(path.relative_to(root)))
    return [
        {"md5": digest, "files": sorted(files)}
        for digest, files in sorted(digests.items())
        if len(files) > 1
    ]


def _normalized_lines(path: Path) -> set:
    lines = set()
    for raw in read_source(path).splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        lines.add(re.sub(r"\s+", " ", stripped))
    return lines


def near_duplicates(root: Path, threshold: float) -> List[Dict[str, Any]]:
    cache: Dict[str, set] = {}
    for path in iter_python_files(root):
        rel = str(path.relative_to(root))
        if rel.startswith(("08_ARCHAEOLOGY/", "07_SANDBOX/", "docs/", "research/")):
            continue
        lines = _normalized_lines(path)
        if len(lines) >= 8:
            cache[rel] = lines
    rels = sorted(cache)
    out: List[Dict[str, Any]] = []
    for i, first in enumerate(rels):
        set_a = cache[first]
        for second in rels[i + 1:]:
            set_b = cache[second]
            if len(set_b) > len(set_a) * 3 + 20 or len(set_a) > len(set_b) * 3 + 20:
                continue
            intersection = len(set_a & set_b)
            if not intersection:
                continue
            jaccard = intersection / len(set_a | set_b)
            if jaccard >= threshold:
                out.append({"similarity": round(jaccard, 3), "a": first, "b": second})
    return sorted(out, key=lambda item: -item["similarity"])


def silent_swallows(trees: Dict[str, ast.Module]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for rel, tree in trees.items():
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            if node.type is None:
                out.append({"file": rel, "line": node.lineno, "kind": "bare except"})
            elif (
                isinstance(node.type, ast.Name)
                and node.type.id in {"Exception", "BaseException"}
                and len(node.body) == 1
                and isinstance(node.body[0], ast.Pass)
            ):
                out.append({"file": rel, "line": node.lineno, "kind": f"except {node.type.id}: pass"})
    return out


def audit(root: Path, threshold: float) -> Dict[str, Any]:
    trees, parse_errors = parse_trees(root)
    dup_defs: List[Dict[str, Any]] = []
    dup_methods: List[Dict[str, Any]] = []
    for rel, tree in trees.items():
        for name, lines in _top_level_names(tree).items():
            dup_defs.append({"file": rel, "name": name, "lines": lines})
        for item in _duplicate_methods(tree):
            item["file"] = rel
            dup_methods.append(item)
    return {
        "root": str(root),
        "python_files": len(trees),
        "parse_errors": parse_errors,
        "duplicate_top_level_definitions": sorted(dup_defs, key=lambda d: d["file"]),
        "duplicate_methods": sorted(dup_methods, key=lambda d: d["file"]),
        "unresolved_imports": sorted(unresolved_imports(root, trees), key=lambda d: d["file"]),
        "duplicate_files": duplicate_files(root),
        "near_duplicates": near_duplicates(root, threshold),
        "silent_swallows": sorted(silent_swallows(trees), key=lambda d: d["file"]),
    }



def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    parser.add_argument("--jaccard", type=float, default=0.60)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = audit(Path(args.root).resolve(), args.jaccard)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    print(f"root: {report['root']}")
    print(f"python files parsed: {report['python_files']}")
    print(f"syntax errors: {len(report['parse_errors'])}")
    for item in report["parse_errors"]:
        print(f"   {item['file']}:{item['line']} {item['error']}")
    print(f"duplicate top-level definitions in one file: {len(report['duplicate_top_level_definitions'])}")
    for item in report["duplicate_top_level_definitions"]:
        print(f"   {item['file']}: {item['name']} {item['lines']}")
    print(f"duplicate methods in one class: {len(report['duplicate_methods'])}")
    for item in report["duplicate_methods"]:
        print(f"   {item['file']}: {item['class']}.{item['method']} {item['lines']}")
    print(f"unresolved in-repo imports: {len(report['unresolved_imports'])}")
    for item in report["unresolved_imports"]:
        print(f"   {item['file']}:{item['line']} {item['problem']}")
    print(f"byte-identical duplicate file groups: {len(report['duplicate_files'])}")
    for item in report["duplicate_files"]:
        print(f"   {item['md5']}")
        for name in item["files"]:
            print(f"      {name}")
    print(f"near-duplicate pairs (>= {args.jaccard}): {len(report['near_duplicates'])}")
    for item in report["near_duplicates"]:
        print(f"   {item['similarity']:.3f}  {item['a']}  <->  {item['b']}")
    print(f"silent exception swallows: {len(report['silent_swallows'])}")
    kinds = collections.Counter(item["kind"] for item in report["silent_swallows"])
    for kind, count in kinds.most_common():
        print(f"   {count:4d}  {kind}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

