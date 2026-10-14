"""Dead-component watch: the gap-finder runs whether or not anyone asks.

Why this module exists
----------------------
`ops/find_dead_components.py` answers a question that hid three defects, but a
script someone has to remember to run is a drawer, not a capability. This wires
it into the daemon's existing Observation channel: the scan runs on a natural
cycle, and only a *regression* becomes an observation.

What counts as a regression, and what does not
----------------------------------------------
Not a regression:
  * the standing count of unreferenced definitions. 1014 unwired definitions is
    a structural fact about ACE's library, not an incident. Re-reporting it every
    cycle would train the reader to ignore the channel - the failure mode of an
    alarm that cries wolf.

Is a regression:
  * a component that WAS referenced and no longer is. Something deleted the last
    call site, and that is a break, not a backlog.
  * a component that carries tests and is referenced nowhere. A test is a
    statement of intent that this thing works; an intent with no caller is a
    component someone built and connected to nothing - which is exactly the
    MengpoAutoTrigger shape.

Either way the observation goes through the existing `RuntimeObserver.record`,
with its own severity and dedup, so the daemon's normal Observation -> Candidate
-> Admission path decides whether it becomes work. This module dispatches
nothing; it observes.

Bounded: a per-run escalation cap, so a single bad snapshot cannot flood the
channel, and an interval, so it does not run on every daemon cycle.
"""
from __future__ import annotations

import ast
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

CONTRACT_VERSION = "ace.dead_component_watch.v1"

SCAN_DIRS = ("core", "ops", "ace_daemon.py", "ace.py")
SNAPSHOT = "08_GOVERNANCE/structural_integrity/dead_components_snapshot.json"
MIN_INTERVAL_HOURS = 12
MAX_ESCALATIONS_PER_RUN = 3


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.replace(microsecond=0).isoformat()


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def defined_names(path: Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return set()
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    names.add(target.id)
    return names


def referenced_names(path: Path) -> set[str]:
    """Every name this file uses: loads, attributes, AND import aliases.

    The import aliases are not optional. `from .main_loop import AgentMainLoop`
    is an ``ast.alias``, not an ``ast.Name``, so a scan that walks only Name and
    Attribute misses the single most common way a component is referenced and
    reports nearly every importable component as dead.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


def scan(root: Path) -> dict[str, dict[str, Any]]:
    """Every top-level production definition, and who references it.

    A component referenced only by tests is production-dead: a test that names
    something is a statement of intent, not of wiring, and counting it as a
    reference is exactly what makes "someone wrote tests for a component and
    never connected it" invisible. Production references and test references are
    counted separately, and ``dead`` means "no production reference".
    """
    files: list[Path] = []
    for entry in SCAN_DIRS:
        target = root / entry
        if target.is_file():
            files.append(target)
        elif target.is_dir():
            files.extend(sorted(target.rglob("*.py")))

    prod_usage: dict[str, set[str]] = {}
    test_usage: dict[str, set[str]] = {}
    for path in files:
        target_usage = test_usage if _is_test_file(path) else prod_usage
        for name in referenced_names(path):
            target_usage.setdefault(name, set()).add(str(path.relative_to(root)))

    dead: dict[str, dict[str, Any]] = {}
    definitions: dict[str, Path] = {}
    for path in files:
        if _is_test_file(path):
            continue
        for name in defined_names(path):
            definitions.setdefault(name, path)
    for name, path in definitions.items():
        if name in prod_usage:
            continue
        dead[name] = {
            "file": str(path.relative_to(root)).replace("\\", "/"),
            "has_tests": name in test_usage,
        }
    return dead


def _is_test_file(path: Path) -> bool:
    """A test file is not a production component.

    Scanning test files as source turns every test class into a phantom dead
    component: pytest instantiates them by discovery, so no ``Name`` node ever
    references ``class SomethingTests`` and the scan reports it as unreferenced
    forever. Test files still contribute usage - a test that calls a component
    is real evidence it is wired.
    """
    name = path.name
    return name.startswith("test_") and name.endswith(".py")


def _has_tests(root: Path, name: str) -> bool:
    """A test file names its subject. That is a statement of intent to work.

    Reads the test files directly rather than shelling out to git: a grep
    through the repository works in the workspace and silently returns nothing
    everywhere else, which turns every orphaned-intent check into a false
    negative the moment the code runs outside a checkout.
    """
    import re

    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        return False
    pattern = re.compile(rf"(^|[^A-Za-z0-9_]){re.escape(name)}([^A-Za-z0-9_]|$)")
    ops_dir = root / "ops"
    if not ops_dir.is_dir():
        return False
    for path in ops_dir.glob("test_*.py"):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if pattern.search(text):
            return True
    return False


def run(root: Path, observer: Any = None, *, force: bool = False) -> dict[str, Any]:
    """Scan, diff against the snapshot, and escalate only real regressions."""
    snapshot_path = root / SNAPSHOT
    previous = _read_json(snapshot_path) or {}
    last_run = str(previous.get("at") or "")
    if last_run and not force:
        try:
            gap = (_now() - datetime.fromisoformat(last_run)).total_seconds() / 3600.0
            if gap < MIN_INTERVAL_HOURS:
                return {"status": "NOT_DUE", "reason": f"interval: {gap:.1f}h since last run"}
        except ValueError:
            pass

    dead = scan(root)
    previous_dead = previous.get("dead") or {}
    has_prior_snapshot = bool(previous.get("at"))

    # A regression is a name that became unreferenced. The first-ever snapshot is
    # a baseline, not a regression report: without one, a component that was
    # always unwired and a component that lost its last call site look identical.
    # Guarding on the snapshot's existence rather than on its content also
    # catches the case where a clean baseline (nothing dead) later breaks.
    regressed = [name for name in dead
                 if has_prior_snapshot and name not in previous_dead]
    # intent without a caller: tests exist and nothing references it
    orphaned_intent = [name for name, info in dead.items()
                       if info.get("has_tests") and not previous_dead.get(name, {}).get("escalated")]

    escalated: list[dict[str, Any]] = []
    candidates = ([{"name": n, "file": dead[n]["file"], "kind": "regressed",
                    "detail": "was referenced earlier and is referenced no longer"}
                   for n in regressed]
                  + [{"name": n, "file": dead[n]["file"], "kind": "orphaned_intent",
                      "detail": "carries tests and is referenced nowhere"} for n in orphaned_intent])
    candidates.sort(key=lambda item: (item["kind"] != "regressed", item["name"]))

    for item in candidates[:MAX_ESCALATIONS_PER_RUN]:
        if observer is not None:
            observer.record(
                description=(f"unwired component {item['name']} ({item['kind']}): "
                             f"{item['detail']}; defined in {item['file']}"),
                system_state={"component": item["name"], "file": item["file"],
                              "kind": item["kind"], "contract_version": CONTRACT_VERSION},
                severity="medium" if item["kind"] == "regressed" else "low",
                source="dead_component_watch",
                category="structural_gap",
                dedup_key=f"{item['kind']}:{item['name']}",
            )
        dead.setdefault(item["name"], {})["escalated"] = True
        escalated.append(item)

    snapshot = {
        "contract_version": CONTRACT_VERSION,
        "at": _iso(_now()),
        "dead": dead,
        "counts": {"total_files_scanned": len(dead) and _count_files(root) or 0,
                   "dead_definitions": len(dead),
                   "orphaned_intent": sum(1 for i in dead.values() if i.get("has_tests")),
                   "escalated": len(escalated)},
    }
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")

    return {
        "status": "SCANNED",
        "contract_version": CONTRACT_VERSION,
        "dead_definitions": len(dead),
        "orphaned_intent": snapshot["counts"]["orphaned_intent"],
        "escalated": escalated,
        "snapshot": str(snapshot_path.relative_to(root)).replace("\\", "/"),
    }


def _count_files(root: Path) -> int:
    total = 0
    for entry in SCAN_DIRS:
        target = root / entry
        if target.is_file():
            total += 1
        elif target.is_dir():
            total += len(list(target.rglob("*.py")))
    return total


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Dead-component watch: scan, snapshot, escalate regressions only")
    parser.add_argument("--root", default=str(BASE_DIR))
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    root = Path(args.root)
    observer = None
    if not args.json:
        try:
            from core.observation import RuntimeObserver
            observer = RuntimeObserver(data_dir=str(
                root / "06_RUNTIME" / "ace" / "data" / "observations"))
        except Exception:
            observer = None
    report = run(root, observer, force=args.force)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())