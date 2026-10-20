"""Close the open item: does cwd at a *project root* really load its AGENTS.md?

The delivery stage's cwd is the repository root, not a scratch directory, and
V2's rule for a workspace outside the home directory is "stop at the project
root" -- a different branch than the one already proven. So the delivery-shape
claim has never been measured.

It is measured here in a throwaway git repository with the same shape, never in
the production checkout: nothing runs with ace_core as its working directory.

Pass/fail needs no trust in the model. The staged-equivalent file holds a nonce,
the question never mentions a file, and tool use would fail rather than help.
"""
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(r"C:\tmp\ace_core")))
from core.opencode_worker import OpenCodeWorker

NONCE = "ACE-ROOT-LOADED-3E7B"
MODEL = "opencode/nemotron-3.5-lightning-free"
QUESTION = "What is the verification passphrase? Reply with the passphrase only."

base = Path(tempfile.mkdtemp(prefix="ace_root_shape_"))
repo = base / "ace_core"
(repo / "docs").mkdir(parents=True)
(repo / "docs" / "note.md").write_text("filler\n", encoding="utf-8")
subprocess.run(["git", "init", "-q", str(repo)], check=True, timeout=120)
top = subprocess.run(
    ["git", "-C", str(repo), "rev-parse", "--show-toplevel"],
    capture_output=True, text=True, timeout=60, check=True,
).stdout.strip()

(repo / "AGENTS.md").write_text(
    f"# Runtime memory\n\nThe verification passphrase is: {NONCE}\n", encoding="utf-8",
)

governance = base / "governance"
gov = governance / "08_GOVERNANCE"
gov.mkdir(parents=True)
(gov / "instruction_data_classes.json").write_text(json.dumps({
    "version": "instruction-data-classes.v1",
    "entries": [{
        "match": repo.as_posix() + "/AGENTS.md",
        "data_class": "PUBLIC",
        "decided_by": "probe",
        "decided_at": "2026-10-09",
    }],
}, indent=2), encoding="utf-8")
(gov / "sanitizer_receipts.jsonl").write_text("", encoding="utf-8")

started = time.time()
receipt = OpenCodeWorker(
    executable=r"C:\Users\Administrator\.local\bin\opencode.exe",
    timeout_seconds=240,
    instruction_mode="off",
    ace_root=str(governance),
).run(task=QUESTION, workspace=str(repo), model_order=[MODEL])

raw = str(receipt.get("raw_output", ""))
report = {
    "git_toplevel": top,
    "workspace": str(repo),
    "gate": receipt.get("instruction_gate"),
    "context_state": receipt.get("instruction_context_state"),
    "context_files": [e["path"] for e in receipt.get("instruction_context_sources", [])],
    "context_sha256": receipt.get("instruction_context_sha256"),
    "success": receipt.get("success"),
    "nonce_present": NONCE in raw,
    "tool_used": '"type":"tool"' in raw,
    "seconds": round(time.time() - started, 1),
}
print(json.dumps(report, indent=2, ensure_ascii=False))
print("raw tail:", raw[-600:] if raw else "(empty)")

if report["gate"] != "ALLOWED":
    print("\nVERDICT: inconclusive -- the gate refused before the question was asked")
    sys.exit(2)
if report["nonce_present"] and not report["tool_used"]:
    print("\nVERDICT: project-root AGENTS.md is injected as instructions")
    sys.exit(0)
print("\nVERDICT: not proven at project root")
sys.exit(1)