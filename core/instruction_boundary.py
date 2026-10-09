"""Egress gate for the instruction set a CLI run actually carries.

OpenCode merges every AGENTS.md it can reach whether or not anyone staged one,
so a gate that only inspected an explicitly staged file would miss the delivery
stage entirely: that path's cwd is the repository root and its instructions
arrive by ambient discovery, never by copying.

Two records back the decision, both append-only and both outside this module's
control:

* ``08_GOVERNANCE/instruction_data_classes.json`` -- what class a given
  instruction file is. Absence is not permission: an unclassified file blocks.
* ``08_GOVERNANCE/sanitizer_receipts.jsonl`` -- proof that a specific file, at
  a specific hash, was reduced to an egressable class and passed the boundary.
  Binding by hash is the point: editing an instruction file invalidates the
  receipt that used to cover it.

A blocked call returns a verdict naming every file, its class and the rule that
refused it. No subprocess starts.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from core.mirror_constitution import DATA_CLASSES, validate_data_boundary

REGISTRY_RELATIVE = Path("08_GOVERNANCE") / "instruction_data_classes.json"
RECEIPTS_RELATIVE = Path("08_GOVERNANCE") / "sanitizer_receipts.jsonl"

# Mirrors core/delivery_execution.INSTRUCTION_EVIDENCE_KEYS, which is what
# actually reaches a stored receipt. Listed here so an audit can tell when the
# two have drifted.
def instruction_evidence_keys() -> tuple:
    from core.delivery_execution import INSTRUCTION_EVIDENCE_KEYS

    return INSTRUCTION_EVIDENCE_KEYS

# Classes that may reach a model only behind a sanitizer receipt.
CONDITIONAL_CLASSES = {"CAPABILITY", "STRUCTURE"}
# Classes no receipt can unlock.
LOCAL_ONLY_CLASSES = {"PRIVATE", "CORE"}

ACCEPTANCE = "ACCEPTANCE_VERIFIED"


def ace_root(explicit: Optional[str] = None) -> Path:
    """The ACE checkout that owns the governance records."""
    if explicit:
        return Path(explicit).expanduser().resolve()
    return Path(__file__).resolve().parents[1]


def _read_registry(root: Path) -> Dict[str, Dict[str, Any]]:
    path = root / REGISTRY_RELATIVE
    if not path.is_file():
        return {}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # An unreadable registry classifies nothing, which blocks. That is the
        # intended failure: a broken governance record must not read as consent.
        return {}
    entries = document.get("entries") if isinstance(document, dict) else None
    if not isinstance(entries, list):
        return {}
    table: Dict[str, Dict[str, Any]] = {}
    for entry in entries:
        if isinstance(entry, dict) and entry.get("match"):
            table[str(entry["match"]).replace("\\", "/").lower()] = entry
    return table


def _read_receipts(root: Path) -> List[Dict[str, Any]]:
    path = root / RECEIPTS_RELATIVE
    if not path.is_file():
        return []
    receipts: List[Dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict) and record.get("receipt_id"):
            receipts.append(record)
    return receipts


def _matches(entry_match: str, source_path: Path) -> bool:
    """Match on a repo-relative suffix so the record stays portable."""
    normalized = source_path.as_posix().lower()
    return normalized.endswith(entry_match.lower().replace("\\", "/"))


def classify_source(
    source: Dict[str, Any],
    *,
    registry: Dict[str, Dict[str, Any]],
    root: Path,
) -> Dict[str, Any]:
    """Resolve one instruction file to a data class and the basis for it."""
    path = Path(str(source.get("path", "")))
    sha256 = str(source.get("sha256", ""))

    for receipt in _read_receipts(root):
        if str(receipt.get("artifact_sha256", "")).lower() != sha256.lower():
            continue
        if not _matches(str(receipt.get("path", "")), path):
            continue
        if receipt.get("acceptance") != ACCEPTANCE:
            continue
        data_class = str(receipt.get("data_class", "")).upper()
        verdict = validate_data_boundary(
            {"data_class": data_class},
            target="MODEL_CONTEXT",
            payload=path.read_text(encoding="utf-8", errors="replace")
            if path.is_file() else "",
        )
        if verdict["valid"]:
            return {
                "path": str(path),
                "sha256": sha256,
                "data_class": data_class,
                "basis": "sanitizer_receipt",
                "receipt_id": str(receipt.get("receipt_id", "")),
            }
        return {
            "path": str(path),
            "sha256": sha256,
            "data_class": data_class,
            "basis": "sanitizer_receipt_rejected",
            "errors": list(verdict["errors"]),
        }

    for entry_match, entry in registry.items():
        if _matches(entry_match, path):
            return {
                "path": str(path),
                "sha256": sha256,
                "data_class": str(entry.get("data_class", "")).upper(),
                "basis": "registry",
                "decided_by": str(entry.get("decided_by", "")),
                "decided_at": str(entry.get("decided_at", "")),
                "evidence": str(entry.get("evidence", "")),
            }

    return {
        "path": str(path),
        "sha256": sha256,
        "data_class": "",
        "basis": "unclassified",
    }


def evaluate_instruction_set(
    sources: Iterable[Dict[str, Any]],
    *,
    root: Optional[str] = None,
) -> Dict[str, Any]:
    """Decide whether this instruction set may reach a hosted model.

    Fail closed in three places: an unclassified file, a local-only class, and
    a conditional class without a live receipt. The verdict names every file so
    a blocked receipt explains itself.
    """
    base = ace_root(root)
    registry = _read_registry(base)
    entries = [classify_source(item, registry=registry, root=base) for item in sources]

    blocked: List[str] = []
    for entry in entries:
        data_class = entry.get("data_class", "")
        path = entry.get("path", "")
        if not data_class:
            blocked.append(f"unclassified:{path}")
            continue
        if data_class not in DATA_CLASSES:
            blocked.append(f"unknown_class:{path}:{data_class}")
            continue
        if data_class in LOCAL_ONLY_CLASSES:
            blocked.append(f"local_only_class:{path}:{data_class}")
            continue
        if data_class in CONDITIONAL_CLASSES and entry.get("basis") != "sanitizer_receipt":
            blocked.append(f"sanitizer_receipt_required:{path}:{data_class}")
            continue
        if entry.get("basis") == "sanitizer_receipt_rejected":
            blocked.append(f"sanitizer_receipt_invalid:{path}")
            continue
        # The class is only half the answer. Re-check the bytes actually headed
        # out, so a PUBLIC-labelled file carrying credential-shaped content
        # still stops here instead of riding its label.
        source_path = Path(path)
        verdict = validate_data_boundary(
            {"data_class": data_class},
            target="MODEL_CONTEXT",
            payload=source_path.read_text(encoding="utf-8", errors="replace")
            if source_path.is_file() else "",
        )
        if not verdict["valid"]:
            blocked.append(f"content_not_egressable:{path}:{','.join(verdict['errors'])}")

    return {
        "instruction_gate": "BLOCKED" if blocked else "ALLOWED",
        "instruction_gate_allowed": not blocked,
        "instruction_gate_blocked": blocked,
        "instruction_classes": entries,
        "instruction_registry": str(base / REGISTRY_RELATIVE),
    }


def discover_repo_instruction_files(root: Optional[str] = None) -> List[Path]:
    """Every AGENTS.md inside the checkout.

    Used by the audit to answer "is every instruction file we ship actually
    classified?", which is the question that a gate alone never surfaces: a file
    nobody has classified is inert until some call happens to sit under it.
    """
    base = ace_root(root)
    if not base.is_dir():
        return []
    return sorted(path for path in base.rglob("AGENTS.md") if path.is_file())


def survey_instruction_egress(
    *,
    root: Optional[str] = None,
    call_sites: Optional[Iterable[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """Report what instruction files exist and how each call site would fare.

    Read-only and model-free on purpose: the point is to be able to answer
    "what would leave if we called from here?" without making the call, which is
    the only way to know the answer before paying for it.
    """
    base = ace_root(root)
    registry = _read_registry(base)
    files = discover_repo_instruction_files(base)

    classified, unclassified = [], []
    for path in files:
        entry = classify_source(
            {"path": str(path), "sha256": ""}, registry=registry, root=base,
        )
        # A repo file carries no bytes in the survey, so classify by the record
        # only; content verification happens against the real file at call time.
        resolved = classify_source(
            {"path": str(path), "sha256": _sha256_of(path)}, registry=registry, root=base,
        )
        record = {
            "path": str(path),
            "data_class": entry["data_class"] or resolved["data_class"],
            "basis": entry["basis"] if entry["basis"] != "unclassified" else resolved["basis"],
        }
        (classified if record["data_class"] else unclassified).append(record)

    sites = []
    for site in call_sites or []:
        workspace = Path(str(site.get("workspace", ""))).expanduser()
        sources: List[Dict[str, Any]] = []
        if workspace.is_dir():
            sources = [
                {"path": str(item["path"]), "sha256": item["sha256"], "bytes": item["bytes"]}
                for item in _instruction_files_for(workspace)
            ]
        verdict = evaluate_instruction_set(sources, root=str(base))
        sites.append({
            "label": str(site.get("label", "")),
            "workspace": str(workspace),
            "instruction_files": len(sources),
            "gate": verdict["instruction_gate"],
            "blocked": verdict["instruction_gate_blocked"],
        })

    blocked = any(item["gate"] == "BLOCKED" for item in sites)
    return {
        "root": str(base),
        "registry": str(base / REGISTRY_RELATIVE),
        "registry_present": (base / REGISTRY_RELATIVE).is_file(),
        "repo_instruction_files": len(files),
        "classified": classified,
        "unclassified": unclassified,
        "call_sites": sites,
        "egress_blocked": blocked,
    }


def _sha256_of(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _instruction_files_for(workspace: Path) -> List[Dict[str, Any]]:
    """The AGENTS.md set for a workspace, in the shape the gate consumes."""
    from core.opencode_worker import OpenCodeWorker

    return OpenCodeWorker._instruction_sources(workspace.resolve())


__all__ = [
    "ACCEPTANCE",
    "CONDITIONAL_CLASSES",
    "LOCAL_ONLY_CLASSES",
    "RECEIPTS_RELATIVE",
    "REGISTRY_RELATIVE",
    "ace_root",
    "classify_source",
    "discover_repo_instruction_files",
    "evaluate_instruction_set",
    "instruction_evidence_keys",
    "survey_instruction_egress",
]