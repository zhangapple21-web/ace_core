"""Prove the observation-lifecycle guards are load-bearing, by breaking each one.

A green suite says the tests pass. It does not say the tests would notice if the
guard were gone. This tool reintroduces, one at a time, the exact defects the
lifecycle fix removed, and requires the suite to go red for every one:

  A  record() returns a consumed observation again      condition freezes
  B  fragment_backlog's signature includes its counter  drifting value forks work
  C  reconcile ignores newer contradictory evidence     recovery erases relapse
  D  archived incident reuses its task without refresh  evidence freezes at closure
  E  ordering re-adds a wall-clock tie-break            a same-tick pair erases each other

It is deliberately fail-closed in both directions:

  an anchor that cannot be found is a FAILURE, not a skip, because a guard that
  cannot be broken cannot be shown to be needed - a renamed line must make this
  tool complain rather than quietly report success
  the restore is verified by hashing every touched file back to its pre-run state
  and re-running the suite, instead of trusting that the copy succeeded

Read-only with respect to production. It only rewrites two source files in the
working tree and puts them back; it never touches runtime data or the TaskPool.
Run it after changing any guard in core/observation.py or
core/observation_to_task.py.
"""
from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent

OBSERVATION = ROOT / "core" / "observation.py"
OBSERVATION_TO_TASK = ROOT / "core" / "observation_to_task.py"
SUITE = "core/test_observation_condition_lifecycle.py"

# label, file, exact text to find, text to put in its place
MUTATIONS: List[Tuple[str, Path, str, str]] = [
    (
        "A: a consumed observation is returned again",
        OBSERVATION,
        """            if active is not None and active.task_generated is None:
                return active""",
        """            if active is not None:
                return active""",
    ),
    (
        "B: the signature forks on a rolling counter",
        OBSERVATION_TO_TASK,
        """        elif name == "fragment_backlog":
            payload = {"condition": bool((state.get("pending_scan", 0) or 0) > 500)}""",
        """        elif name == "fragment_backlog":
            payload = {"condition": bool((state.get("pending_scan", 0) or 0) > 500),
                       "count": int(state.get("pending_scan", 0) or 0)}""",
    ),
    (
        "C: reconcile ignores newer contradictory evidence",
        OBSERVATION_TO_TASK,
        """            if self._newer_evidence_contradicts(rule, obs):
                continue""",
        """            if False:
                continue""",
    ),
    (
        "D: an archived incident reuses its task without refreshing evidence",
        OBSERVATION_TO_TASK,
        """                    # escalation layer's call, not the poll loop's.
                    self._record_persistent_incident(rule, state, task.task_id)""",
        """                    # escalation layer's call, not the poll loop's.""",
    ),
    (
        "E: ordering re-adds a wall-clock tie-break on top of append order",
        OBSERVATION_TO_TASK,
        """        for other in store[position + 1:]:
            if str(getattr(other, "category", "") or "") != rule.category:""",
        """        try:
            _seen = datetime.fromisoformat(str(getattr(obs, "created_at", "") or ""))
        except (ValueError, TypeError):
            return False
        for other in store[position + 1:]:
            try:
                _other_at = datetime.fromisoformat(str(getattr(other, "created_at", "") or ""))
            except (ValueError, TypeError):
                continue
            if _other_at <= _seen:
                continue
            if str(getattr(other, "category", "") or "") != rule.category:""",
    ),
]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_suite() -> Tuple[bool, str]:
    """Return (failed, summary). A crash counts as failure: it still shows the guard matters."""
    try:
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", SUITE, "-q", "--no-header",
             "-p", "no:cacheprovider"],
            capture_output=True, text=True, timeout=900, cwd=str(ROOT),
            encoding="utf-8", errors="replace",
        )
    except subprocess.TimeoutExpired:
        return True, "timeout"
    lines = [line for line in completed.stdout.splitlines()
             if "passed" in line or "failed" in line or "error" in line]
    return completed.returncode != 0, (lines[-1].strip() if lines else "no summary")


def main() -> int:
    originals: Dict[Path, str] = {}
    backups: Dict[Path, Path] = {}
    for _, path, _, _ in MUTATIONS:
        if path in originals:
            continue
        originals[path] = digest(path)
        backups[path] = path.with_suffix(path.suffix + ".mutbak")
        shutil.copy2(path, backups[path])

    clean_failed, clean_summary = run_suite()
    print(f"baseline (unmutated): {'FAILED' if clean_failed else 'green'} - {clean_summary}")
    if clean_failed:
        print("\nThe suite is already red before any mutation. Refusing to report on")
        print("mutations: an unmutated failure would be mistaken for detection.")
        for path, backup in backups.items():
            shutil.copy2(backup, path)
            backup.unlink(missing_ok=True)
        return 2

    results: List[Tuple[str, bool, str]] = []
    try:
        for label, path, anchor, replacement in MUTATIONS:
            shutil.copy2(backups[path], path)
            text = path.read_text(encoding="utf-8")
            if anchor not in text:
                results.append((label, False, "ANCHOR MISSING - cannot show this guard is needed"))
                print(f"{label}\n    ANCHOR MISSING in {path.name}; treated as failure")
                continue
            path.write_text(text.replace(anchor, replacement, 1), encoding="utf-8")
            detected, summary = run_suite()
            results.append((label, detected, summary))
            print(f"{label}\n    detected: {detected}   {summary}")
    finally:
        for path, backup in backups.items():
            shutil.copy2(backup, path)
            backup.unlink(missing_ok=True)

    restored_ok = all(digest(path) == original for path, original in originals.items())
    after_failed, after_summary = run_suite()
    print(f"\nrestored: {'FAILED' if after_failed else 'green'} - {after_summary}")
    print(f"every touched file byte-identical to before: {restored_ok}")

    all_detected = all(detected for _, detected, _ in results)
    verdict = all_detected and not after_failed and restored_ok
    print(f"\nVERDICT all_{len(results)}_guards_bind={all_detected} tree_restored={restored_ok}")
    for label, detected, _ in results:
        print(f"  {'ok  ' if detected else 'NOT '}{label}")
    print("\n(reaching the guard without breaking it is not proof it is needed; this tool")
    print(" is the difference between 'tests pass' and 'these lines are load-bearing')")
    return 0 if verdict else 1


if __name__ == "__main__":
    raise SystemExit(main())
