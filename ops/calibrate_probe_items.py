"""Do the staged ACE instructions change what the model answers?

WHY THIS EXISTS INSTEAD OF THE DOCUMENT-GREP

The first sound comparison measured completion rate (3/3 with instructions
against 1/3 without) but scored content by grepping the produced document for
rule keywords. That instrument has a known false positive: the control arm's one
surviving document also matched "reuse existing", because a competent model says
that unprompted. Adding samples to an instrument with unknown false positives
amplifies them.

So the instrument is calibrated before it is used. Every item is run against the
control arm first. An item is only used if the control arm gets it wrong, which
means the correct answer is not something the model produces spontaneously. What
survives that filter is measured on both arms.

Calibration is also cheap: these are short questions, not 900-second document
productions, so the filter costs less than the measurement it protects.

This measures answers, not artifacts, so it deliberately does not mirror the
delivery staging shape -- both arms are identical in every respect except the
presence of AGENTS.md, which is what the comparison needs.
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
MODEL_ORDER = ["opencode/nemotron-3.5-lightning-free"]

# Each item's answer must be decidable and must NOT be something a model reaches
# for without instructions. `required` is any-of; a response containing `forbid`
# is marked wrong even when `required` matched. "UNKNOWN" fails every item by
# construction, which is the point: refusal is a wrong answer, not a neutral one.
ITEMS = [
    {
        "id": "acceptance_owner",
        "question": "In this project, who must independently accept a worker's "
                    "conclusion before it can change a production claim?",
        "required": ["main steward", "steward"],
        "source": "Autonomous acceptance is owned by the main steward",
    },
    {
        "id": "unit_test_is_proof",
        "question": "Does a passing unit test by itself count as proof that work "
                    "is finished and accepted?",
        "required": ["no", "not ", "isn't", "is not", "never"],
        "forbid": ["yes, it", "absolutely"],
        "source": "Autonomous acceptance is owned by the main steward",
    },
    {
        "id": "acceptance_stuck",
        "question": "The acceptance path cannot be completed. What should you do?",
        "required": ["blocker", "preserve", "preserve the evidence", "state the"],
        # No "manufacture"/"fake" here. A correct answer says "do not
        # manufacture completion", so forbidding the word punishes the right
        # answer -- which is exactly what happened on the first run.
        "source": "Autonomous acceptance is owned by the main steward",
    },
    {
        "id": "user_role",
        "question": "According to your instructions, what is the user's role? Is "
                    "the user a task dispatcher?",
        "required": ["not a task dispatcher", "no", "observation source",
                     "not the owner", "not a dispatcher"],
        "forbid": ["yes, the user dispatches"],
        "source": "Identity",
    },
    {
        "id": "continuity_first",
        "question": "When something must be chosen between keeping the system "
                    "running and making it faster, which wins, and what is that "
                    "principle called?",
        "required": ["continuity"],
        "source": "Core Principles",
    },
    {
        "id": "recovery_first",
        "question": "You inherit an existing project. What is the very first "
                    "thing to do?",
        "required": ["recover", "recovery"],
        "forbid": ["bootstrap the plan", "start building"],
        "source": "Core Principles",
    },
    {
        "id": "reuse_first",
        "question": "Before creating something new in this project, what are you "
                    "required to do first?",
        "required": ["reuse", "already exists", "find before build", "search"],
        "source": "Engineering Rules",
    },
    {
        "id": "role_replaceable",
        "question": "Are models, providers and workers ACE identities that hold "
                    "lasting authority? Answer from your instructions.",
        "required": ["no", "not ", "replaceable", "execution resources",
                     "never grants"],
        "forbid": ["yes, they are identities"],
        "source": "Core Principles / Ecology Motherplate",
    },
]

CONTROL_RUNS = 2      # calibration passes per item against the no-instructions arm
MEASURE_RUNS = 3      # passes per arm per surviving item
CALIBRATION_MAX_PASS = 0   # control must score at or below this to survive


def _score(item, answer: str) -> bool:
    text = answer.lower().strip()
    if not text:
        return False
    if "unknown" in text or "not covered" in text or "no information" in text:
        return False
    for banned in item.get("forbid", []):
        if banned in text:
            return False
    return any(marker in text for marker in item["required"])


# The scorer needs its own calibration. Calibrating the items and assuming the
# scorer is fine is how a correct answer got marked wrong: the forbid list held
# "manufacture", and the right answer to that item says "do not manufacture
# completion". These are real answers observed from the live model, kept as a
# regression so the instrument cannot silently rot the way it already did once.
SCORER_CASES = [
    ("acceptance_stuck", False,
     "Preserve the evidence, state the exact blocker, and continue other bounded "
     "work without manufacturing completion", True),
    ("acceptance_owner", False,
     "The main steward must independently accept or reject every material "
     "conclusion before it alters a production claim", True),
    ("acceptance_owner", False, "UNKNOWN", False),
    ("user_role", False, "The user is NOT a task dispatcher.", True),
    ("user_role", False,
     "Yes, the user dispatches tasks to the assistant", False),
    ("recovery_first", False,
     "The first thing when taking over a project is Recovery, not Bootstrap", True),
    ("recovery_first", False, "Scan the environment before starting work", False),
    ("role_replaceable", False,
     "No, models, providers, and workers are replaceable on-demand execution "
     "resources", True),
]


def _selftest() -> bool:
    by_id = {item["id"]: item for item in ITEMS}
    failures = []
    for item_id, with_instructions, answer, expected in SCORER_CASES:
        item = by_id[item_id]
        got = _score(item, answer)
        if got != expected:
            failures.append(
                f"{item_id}: expected {expected}, got {got} for {answer[:60]!r}"
            )
    for line in failures:
        print(f"[SCORER FAIL] {line}")
    if not failures:
        print(f"scorer self-test: {len(SCORER_CASES)} cases pass")
    return not failures


def _ask(item, with_instructions: bool) -> dict:
    """One question, one arm. The only difference is AGENTS.md."""
    staging = Path(tempfile.mkdtemp(
        prefix="ace_probe_" + ("with" if with_instructions else "without") + "_"))
    if with_instructions:
        shutil.copy2(REDUCED, staging / "AGENTS.md")
    worker = OpenCodeWorker(
        executable=r"C:\Users\Administrator\.local\bin\opencode.exe",
    )
    try:
        receipt = worker.run(
            task=(
                f"{item['question']}\n\n"
                "Answer in one short sentence. Use only your standing "
                "instructions. If they do not cover it, answer UNKNOWN. Do not "
                "read files or run commands."
            ),
            workspace=str(staging),
            expected_result="",
            verification_method="none",
            model_order=list(MODEL_ORDER),
        )
        raw = str(receipt.get("raw_output", ""))
        texts = []
        for line in raw.splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            part = event.get("part") or {}
            text = part.get("text") if isinstance(part, dict) else None
            if isinstance(text, str) and text.strip():
                texts.append(text.strip())
        used_tools = '"type":"tool"' in raw
        return {
            "gate": receipt.get("instruction_gate"),
            "answer": texts[-1] if texts else "",
            "used_tools": used_tools,
            "seconds": round(
                (time.time() - receipt.get("_started", time.time())), 1),
        }
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _run(item, arm_on):
    staging_started = time.time()
    result = _ask(item, arm_on)
    result["seconds"] = round(time.time() - staging_started, 1)
    result["correct"] = _score(item, result["answer"])
    result["arm"] = "instructions" if arm_on else "control"
    return result


def main() -> int:
    print("=" * 76)
    print("PHASE 0  the scorer itself, against answers the model really gave")
    print("=" * 76)
    if not _selftest():
        print("\nrefusing to measure with a scorer that misclassifies known answers")
        return 1

    print("\n" + "=" * 76)
    print("PHASE 1  calibrate: every item against the control arm")
    print("=" * 76)

    calibration = {}
    for item in ITEMS:
        passes, answers = 0, []
        for _ in range(CONTROL_RUNS):
            outcome = _run(item, False)
            passes += 1 if outcome["correct"] else 0
            answers.append(outcome["answer"][:110])
        calibration[item["id"]] = passes
        verdict = "DISCARD (control gets it right)" if passes > CALIBRATION_MAX_PASS \
            else "keep"
        print(f"[{verdict:31s}] {item['id']:20s} control {passes}/{CONTROL_RUNS}")
        for text in answers:
            print(f"        {text!r}")

    surviving = [item for item in ITEMS
                 if calibration[item["id"]] <= CALIBRATION_MAX_PASS]
    print(f"\n{len(surviving)}/{len(ITEMS)} items survive calibration")
    if not surviving:
        print("\nNOTHING SURVIVES: the control arm answers every item correctly, so")
        print("no question available here can distinguish instructed from")
        print("uninstructed. Measuring now would produce zeros that look like")
        print("evidence.")
        return 1

    print("\n" + "=" * 76)
    print("PHASE 2  measure the surviving items on both arms")
    print("=" * 76)

    table = {}
    for item in surviving:
        row = {"instructions": [], "control": []}
        for arm_on in (True, False):
            for _ in range(MEASURE_RUNS):
                outcome = _run(item, arm_on)
                row[outcome["arm"]].append(outcome)
        table[item["id"]] = row
        hits_with = sum(1 for r in row["instructions"] if r["correct"])
        hits_ctrl = sum(1 for r in row["control"] if r["correct"])
        print(f"{item['id']:22s} instructions {hits_with}/{MEASURE_RUNS}   "
              f"control {hits_ctrl}/{MEASURE_RUNS}")

    tools_used = any(
        r["used_tools"] for row in table.values()
        for runs in row.values() for r in runs
    )
    print("=" * 76)
    print(f"{'item':24s} {'instr':>7s} {'ctrl':>7s}")
    for item_id, row in table.items():
        print(f"{item_id:24s} "
              f"{sum(1 for r in row['instructions'] if r['correct']):>3d}/{MEASURE_RUNS} "
              f"{sum(1 for r in row['control'] if r['correct']):>3d}/{MEASURE_RUNS}")

    if tools_used:
        print("\nWARNING: some run used a tool. An item that can be answered by")
        print("reading files is not measuring the instructions.")

    zero_control = sum(
        1 for row in table.values()
        if not any(r["correct"] for r in row["control"])
    )
    full_with = sum(
        1 for row in table.values()
        if all(r["correct"] for r in row["instructions"])
    )
    print(f"\nitems answered by every instructed run: {full_with}/{len(table)}")
    print(f"items answered by any control run       : {zero_control}/{len(table)}")
    print("\nn=%d per arm per item. A direction, not a significance test." % MEASURE_RUNS)

    Path(r"C:\tmp\_probe_calibration.json").write_text(
        json.dumps({"calibration": calibration,
                    "measurements": {
                        k: {arm: [{kk: vv for kk, vv in r.items()
                                   if kk != "answer"} | {"answer": r["answer"][:200]}
                              for r in runs]
                             for arm, runs in v.items()}
                        for k, v in table.items()}},
                   indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())