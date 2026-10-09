"""Do the staged ACE instructions change the artifact, or not?

WHAT WENT WRONG TWICE, so the design here is shaped by it:

1. The first run compared "reduced instructions" against "no instructions" and
   reported a striking result -- every retained-rule trace 2/2 with, 0/2 without.
   That was false. The control arm emitted zero bytes, so its traces scored zero
   because there was no document to scan. A difference of "document" against
   "nothing" measures success, not quality.

2. The fix for that -- granting the staged worker read access to the repository
   -- was applied to AceDaemon._deliver_with_reduced_instructions. This script
   had reimplemented the staging steps for itself, so it kept running the broken
   control arm, and was about to produce a second confident number from it.

So this script now calls the production path. It does not stage anything itself;
the only thing it varies is whether an AGENTS.md is present, which it does by
running the production method against two different instruction directories. If
production changes what it stages, this measures the new behaviour instead of a
stale copy.

A starved arm is reported as a starved arm. Zeros from an arm that produced no
document are never presented as a delta.
"""
import json
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(r"C:\tmp\ace_core")
sys.path.insert(0, str(ROOT))

from ace_daemon import AceDaemon
from core.opencode_worker import OpenCodeWorker

REDUCED = ROOT / "model_instructions" / "AGENTS.md"

MODEL_ORDER = ["opencode/nemotron-3.5-lightning-free"]

TASK_TITLE = "document how to add a new provider to the miner pool"
TASK_HYPOTHESIS = (
    "A reader who has never seen this codebase can add a provider by following "
    "the note alone"
)
REQUIRED = "docs/INSTRUCTION_VALUE_PROBE.md"

# Traces of rules that were retained in the reduction. Chosen to be specific:
# a hit has to mean the text reached the model.
TRACES = {
    "reuse_existing": [r"reuse", r"already exists", r"existing\b", r"mirr"],
    "find_before_build": [r"before (?:building|creating|writing|adding)", r"search"],
    "recovery_first": [r"recover", r"recovery"],
    "continuity": [r"continuity", r"keep running", r"before optimi"],
    "acceptance_path": [
        r"independent(?:ly)? (?:accept|verify|audit)", r"acceptance",
        r"evidence",
    ],
}

# Byte-for-byte what AceDaemon._deliver_with_reduced_instructions builds. If
# production changes its prompt, this must change with it or the arms stop being
# comparable -- which is the whole mistake this harness already made once.
def _production_task(title: str, hypothesis: str) -> str:
    repo = str(ROOT).replace("\\", "/").rstrip("/")
    return (
        f"Produce the deliverable at {REQUIRED}. "
        f"Task: {title}. "
        f"Hypothesis: {hypothesis}. "
        f"The code you are documenting is readable at {repo}; "
        f"read it before writing. Write the deliverable into "
        f"your own working directory."
    )


def _score(text: str) -> dict:
    lowered = text.lower()
    return {
        name: any(re.search(pattern, lowered) for pattern in patterns)
        for name, patterns in TRACES.items()
    }


def _run_once(with_instructions: bool, run_id: int) -> dict:
    """One delivery through the production staging path.

    The treatment arm calls AceDaemon._deliver_with_reduced_instructions directly
    and changes nothing, so it measures production as production behaves.

    The control arm cannot be built the same way. An AGENTS.md the gate does not
    recognise is refused in 0.0s without a model running -- an unclassified file
    is exactly what the gate exists to refuse, and a registry entry keyed on a
    fixed path can never match the randomly named staging copy, because the gate
    identifies a file by where it sits. So the only compliant control is no
    instruction file at all, and the gate admits that.

    The control therefore performs the same steps minus one file copy, and
    asserts that the staging directory it built differs from production's only
    by the absence of AGENTS.md.
    """
    if with_instructions:
        return _run_treatment(run_id)

    staging = Path(tempfile.mkdtemp(prefix=f"ace_control_stage_{run_id}_"))
    worker = OpenCodeWorker(
        # Production builds OpenCodeWorker() with defaults, which means a 900s
        # budget. A harness that quietly under-budgets measures itself, not the
        # thing under test -- that mistake starved runs before it was spotted.
        # Only the executable is pinned, because it is the one thing a machine
        # without the CLI installed cannot resolve.
        executable=r"C:\Users\Administrator\.local\bin\opencode.exe",
    )
    repo_pattern = str(ROOT).replace("\\", "/").rstrip("/") + "/*"
    (staging / "opencode.json").write_text(
        json.dumps({"$schema": "https://opencode.ai/config.json", "permissions": [
            {"action": "external_directory", "resource": repo_pattern, "effect": "allow"},
            {"action": "read", "resource": repo_pattern, "effect": "allow"},
            {"action": "edit", "resource": repo_pattern, "effect": "deny"},
        ]}, indent=2),
        encoding="utf-8",
    )
    assert not (staging / "AGENTS.md").exists()

    target = ROOT / REQUIRED
    if target.is_file():
        target.unlink()
    started = time.time()
    try:
        receipt = worker.run(
            # Byte-for-byte the prompt production builds for this task, so the
            # only difference between the arms is the presence of AGENTS.md.
            task=_production_task(
                f"{TASK_TITLE} (variant {run_id})", TASK_HYPOTHESIS,
            ),
            workspace=str(staging),
            expected_result=REQUIRED,
            verification_method="file_exists_nonempty",
            model_order=list(MODEL_ORDER),
        )
        elapsed = round(time.time() - started, 1)
        body = ""
        if target.is_file():
            body = target.read_text(encoding="utf-8")
            target.unlink()
        elif (staging / REQUIRED).is_file():
            shutil.copy2(staging / REQUIRED, target)
            body = target.read_text(encoding="utf-8")
            target.unlink()
        starved = not body
        return {
            "arm": "control", "run": run_id,
            "gate": receipt.get("instruction_gate"),
            "instruction_files": len(receipt.get("instruction_context_sources", [])),
            "success": receipt.get("success"),
            "artifact_bytes": len(body.encode("utf-8")),
            "seconds": elapsed, "starved": starved,
            "scores": _score(body) if not starved else {},
            "body": body,
        }
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _run_treatment(run_id: int) -> dict:
    """Production path, untouched."""
    target = ROOT / REQUIRED
    if target.is_file():
        target.unlink()

    daemon = AceDaemon.__new__(AceDaemon)
    daemon.base_dir = ROOT
    daemon.task_pool = None
    daemon._reuse_hint_for = lambda *a, **k: ""

    def route(capability, worker, **kwargs):
        kwargs.pop("verify", None)
        kwargs["model_order"] = list(MODEL_ORDER)
        return worker.run(**kwargs)

    daemon.worker_router = SimpleNamespace(run=route)
    worker = OpenCodeWorker(
        executable=r"C:\Users\Administrator\.local\bin\opencode.exe",
    )

    target = ROOT / REQUIRED
    if target.is_file():
        target.unlink()

    daemon = AceDaemon.__new__(AceDaemon)
    daemon.base_dir = ROOT
    daemon.task_pool = None
    daemon._reuse_hint_for = lambda *a, **k: ""

    def route(capability, worker, **kwargs):
        kwargs.pop("verify", None)
        kwargs["model_order"] = list(MODEL_ORDER)
        return worker.run(**kwargs)

    daemon.worker_router = SimpleNamespace(run=route)
    worker = OpenCodeWorker(
        executable=r"C:\Users\Administrator\.local\bin\opencode.exe",
    )

    try:
        started = time.time()
        receipt = daemon._deliver_with_reduced_instructions(
            worker, REDUCED.parent,
            required_path=REQUIRED,
            title=f"{TASK_TITLE} (variant {run_id})",
            hypothesis=TASK_HYPOTHESIS,
            task_id=f"value-{run_id}",
        )
        elapsed = round(time.time() - started, 1)
        body = target.read_text(encoding="utf-8") if target.is_file() else ""
        if target.is_file():
            target.unlink()
        starved = not body
        return {
            "arm": "instructions", "run": run_id,
            "gate": receipt.get("instruction_gate"),
            "instruction_files": len(
                receipt.get("instruction_context_sources", [])
            ),
            "success": receipt.get("success"),
            "artifact_bytes": len(body.encode("utf-8")),
            "seconds": elapsed, "starved": starved,
            "scores": _score(body) if not starved else {},
            "body": body,
        }
    finally:
        pass


def main() -> int:
    print(f"reduced artifact: {REDUCED}")
    print(f"task: {_production_task(TASK_TITLE, TASK_HYPOTHESIS)[:80]}...\n")

    results = []
    order = (True, False, True, False, True, False)
    for arm_on in order:
        item = _run_once(arm_on, len(results) + 1)
        results.append(item)
        print(
            f"[{item['arm']:12s}] run{item['run']} gate={item['gate']} "
            f"files={item['instruction_files']} success={item['success']} "
            f"bytes={item['artifact_bytes']} {item['seconds']}s"
            + ("  STARVED" if item["starved"] else ""),
            flush=True,
        )
        Path(r"C:\tmp\_instruction_value_bodies").mkdir(exist_ok=True)
        if item["body"]:
            Path(
                rf"C:\tmp\_instruction_value_bodies\{item['arm']}_{item['run']}.md"
            ).write_text(item["body"], encoding="utf-8")

    print("\n" + "=" * 74)

    # Pre-flight, learned the hard way. If either arm was refused at the gate it
    # never ran a model, and every trace it "scored" would be a zero for a
    # document that was never written. Refuse to report rather than report that.
    blocked = [item for item in results if item["gate"] != "ALLOWED"]
    if blocked:
        print("INVALID RUN -- an arm was refused at the gate:")
        for item in blocked:
            print(f"  {item['arm']} run{item['run']}: gate={item['gate']} "
                  f"{item['seconds']}s")
        print("No model ran. A gate refusal is not a zero, and a zero here would")
        print("look like evidence.")
        return 1

    control_files = {
        item["instruction_files"] for item in results if item["arm"] == "control"
    }
    if control_files - {0}:
        print(f"INVALID RUN -- control arm carried instruction files: "
              f"{sorted(control_files)}")
        print("The control is only a control if it carries no instructions.")
        return 1

    summary = {}
    for arm in ("instructions", "control"):
        rows = [item for item in results if item["arm"] == arm]
        fed = [item for item in rows if not item["starved"]]
        summary[arm] = {
            "runs": len(rows),
            "starved": sum(1 for item in rows if item["starved"]),
            "scored": len(fed),
            "avg_bytes": sum(
                item["artifact_bytes"] for item in fed) // max(1, len(fed)),
            "avg_seconds": round(
                sum(item["seconds"] for item in rows) / max(1, len(rows)), 1),
            "traces": {
                name: sum(1 for item in fed if item["scores"][name])
                for name in TRACES
            },
        }
        entry = summary[arm]
        print(f"\n{arm}: {entry['runs']} runs, {entry['starved']} starved, "
              f"{entry['scored']} scored, avg {entry['avg_bytes']} B, "
              f"{entry['avg_seconds']}s")
        for name in TRACES:
            print(f"  {name:24s} {entry['traces'][name]}/{entry['scored']}")

    print("=" * 74)
    print(f"{'trace':26s} {'with':>7s} {'ctrl':>7s}  delta")
    deltas = {}
    for name in TRACES:
        with_n = summary["instructions"]["traces"][name]
        ctrl_n = summary["control"]["traces"][name]
        deltas[name] = with_n - ctrl_n
        print(f"{name:26s} {with_n:>7d} {ctrl_n:>7d}  {deltas[name]:+d}")

    print()
    starved_any = (
        summary["instructions"]["starved"] or summary["control"]["starved"]
    )
    if starved_any:
        print(f"CAVEAT: starved runs "
              f"(instructions {summary['instructions']['starved']}/"
              f"{summary['instructions']['runs']}, "
              f"control {summary['control']['starved']}/"
              f"{summary['control']['runs']}) were excluded from scoring.")
        print("        A starved arm is a failure of that arm, not evidence about")
        print("        instructions. Deltas above count only runs that wrote.")
    if not summary["instructions"]["scored"] or not summary["control"]["scored"]:
        print("\nNO USABLE COMPARISON: one arm wrote nothing at all.")
        return 1
    affected = [name for name, delta in deltas.items() if delta != 0]
    print("\ndetectable effect on:", ", ".join(affected) if affected else "nothing")
    print("NOTE n=3 per arm, small free model. Direction, not a quality score.")

    Path(r"C:\tmp\_instruction_value.json").write_text(
        json.dumps(
            {"summary": summary, "deltas": deltas,
             "runs": [{k: v for k, v in item.items() if k != "body"}
                      for item in results]},
            indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())