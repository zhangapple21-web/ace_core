"""Does the instruction staging earn its place?

READ THIS BEFORE TRUSTING THE SCORE TABLE.

The first run of this produced a striking result -- every retained-rule trace
present with instructions, absent without -- and the score table was wrong. The
control arm emitted zero bytes, so all of its traces scored zero for the trivial
reason that there was no document to scan. A difference of "document" against
"nothing" measures whether the arm succeeded, not whether the instructions
improved it.

That turned out to be the useful finding. The control arm had failed with
opencode_all_models_failed after spending its budget globbing an empty
staging directory: the staging change had taken the repository away from a
worker whose job is to document the repository. See the read-access grant in
AceDaemon._deliver_with_reduced_instructions and ops/test_delivery_repo_read_access.py.

What this script is now good for: detecting an arm that fails rather than
producing a weak document. It is not a measure of instruction quality. To get
that, both arms must produce a document, and the scorer must say so instead of
reporting zeros as a delta.

The A/B the ruling forbids remains "full private manual vs reduced", since the
control group would itself be the forbidden egress.
"""
import json
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(r"C:\tmp\ace_core")
sys.path.insert(0, str(ROOT))

from core.opencode_worker import OpenCodeWorker

REDUCED = ROOT / "model_instructions" / "AGENTS.md"

# One free model, pinned so a registry change cannot move the arms apart.
MODEL_ORDER = ["opencode/nemotron-3.5-lightning-free"]

# A task of the shape the delivery stage actually issues: a documentation
# deliverable that a competent engineer could satisfy without ever reading ACE's
# rules, which is exactly why it is a fair probe.
TASK_TITLE = "document how to add a new provider to the miner pool"
TASK_HYPOTHESIS = (
    "A reader who has never seen this codebase can add a provider by following "
    "the note alone"
)
REQUIRED = "docs/INSTRUCTION_VALUE_PROBE.md"

# Traces of rules that were retained in the reduction.
TRACES = {
    "reuse_existing": [r"reuse", r"already exists", r"existing\b", r"mirror"],
    "find_before_build": [r"before (?:building|creating|writing)", r"search"],
    "recovery_first": [r"recover", r"recovery"],
    "continuity": [r"continuity", r"keep running", r"before optimi"],
    "acceptance_path": [
        r"independent(?:ly)? (?:accept|verify|audit)", r"acceptance",
        r"evidence", r"not .*proof",
    ],
    "no_manufactured_completion": [
        r"not .{0,20}proof", r"cannot claim", r"until .{0,30}verified",
        r"do not claim", r"pending",
    ],
}


def _score(text: str) -> dict:
    lowered = text.lower()
    return {
        name: any(re.search(pattern, lowered) for pattern in patterns)
        for name, patterns in TRACES.items()
    }


def _deliver(with_instructions: bool, run_id: int) -> dict:
    """One delivery through the same staging shape production uses, instructions on or off.

    Reimplemented here rather than calling _deliver_with_reduced_instructions,
    because that method always copies an instruction file and the control arm
    needs a run with none. The steps are the same: scratch directory, model runs
    with its working directory set to it, the declared path copied back for
    scoring. Only the presence of AGENTS.md differs between arms.
    """
    staging = Path(tempfile.mkdtemp(prefix=f"ace_value_{run_id}_"))
    if with_instructions:
        shutil.copy2(REDUCED, staging / "AGENTS.md")

    worker = OpenCodeWorker(
        executable=r"C:\Users\Administrator\.local\bin\opencode.exe",
        timeout_seconds=300,
    )

    try:
        started = time.time()
        receipt = worker.run(
            task=(
                f"Produce the deliverable at {REQUIRED}. "
                f"Task: {TASK_TITLE} (variant {run_id}). "
                f"Hypothesis: {TASK_HYPOTHESIS}"
            ),
            workspace=str(staging),
            expected_result=REQUIRED,
            verification_method="file_exists_nonempty",
            model_order=list(MODEL_ORDER),
        )
        elapsed = round(time.time() - started, 1)

        produced = staging / REQUIRED
        target = ROOT / REQUIRED
        body = ""
        if produced.is_file():
            body = produced.read_text(encoding="utf-8")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(produced, target)
        if target.is_file():
            target.unlink()
        return {
            "arm": "instructions" if with_instructions else "no_instructions",
            "run": run_id,
            "gate": receipt.get("instruction_gate"),
            "instruction_files": len(receipt.get("instruction_context_sources", [])),
            "success": receipt.get("success"),
            "artifact_bytes": len(body.encode("utf-8")),
            "seconds": elapsed,
            "scores": _score(body),
            "head": "\n".join(body.splitlines()[:6]),
        }
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def main() -> int:
    results = []
    for arm_on in (True, False, True, False):
        results.append(_deliver(arm_on, len(results) + 1))
        latest = results[-1]
        print(
            f"[{latest['arm']:15s}] run{latest['run']} "
            f"gate={latest['gate']} files={latest['instruction_files']} "
            f"bytes={latest['artifact_bytes']} {latest['seconds']}s",
            flush=True,
        )

    print("=" * 78)
    summary = {}
    for arm in ("instructions", "no_instructions"):
        rows = [item for item in results if item["arm"] == arm]
        summary[arm] = {
            name: sum(1 for row in rows if row["scores"][name])
            for name in TRACES
        }
        summary[arm]["runs"] = len(rows)
        summary[arm]["avg_bytes"] = sum(
            row["artifact_bytes"] for row in rows) // max(1, len(rows))
        summary[arm]["avg_seconds"] = round(
            sum(row["seconds"] for row in rows) / max(1, len(rows)), 1)
        print(f"\n{arm}  (n={len(rows)}, avg {summary[arm]['avg_bytes']} B, "
              f"{summary[arm]['avg_seconds']}s)")
        for name in TRACES:
            print(f"  {name:28s} {summary[arm][name]}/{len(rows)}")

    print("=" * 78)
    print(f"{'trace':30s} {'with':>6s} {'without':>8s}  delta")
    deltas = {}
    for name in TRACES:
        with_n = summary["instructions"][name]
        without_n = summary["no_instructions"][name]
        deltas[name] = with_n - without_n
        print(f"{name:30s} {with_n:>6d} {without_n:>8d}  {deltas[name]:+d}")

    affected = [name for name, delta in deltas.items() if delta != 0]
    starved = [
        item["arm"] for item in results if item["artifact_bytes"] == 0
    ]
    print()
    if starved:
        print("INVALID COMPARISON -- an arm produced no document:")
        print(f"  starved runs: {starved}")
        print("  Trace zeros for a starved arm mean 'no document', not 'rule not")
        print("  applied'. The only defensible conclusion is that the arm failed.")
        print("  Investigate why before reading any delta above as an effect.")
    elif affected:
        print("detectable effect on:", ", ".join(affected))
        print("NOTE: n=2 per arm with a small free model. This shows a direction,")
        print("      not a quality score. Re-run with more runs before relying on it.")
    else:
        print("NULL RESULT: both arms produced documents and no trace differed.")
        print("The staging machinery currently shows no measurable effect on the")
        print("artifact. That is a finding, not a pass.")

    Path(r"C:\tmp\_instruction_value.json").write_text(
        json.dumps({"runs": results, "summary": summary, "deltas": deltas},
                   indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())