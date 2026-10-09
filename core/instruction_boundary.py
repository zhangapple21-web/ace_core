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
# Classes a sanitizer receipt may legitimately reduce from.
RESTRICTED_CLASSES = CONDITIONAL_CLASSES | LOCAL_ONLY_CLASSES

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


def _registry_entry_for(registry: Dict[str, Dict[str, Any]], path: Path):
    """The most specific registry record covering a path.

    Registry entries match on path suffixes, so a record for the bare filename
    would otherwise shadow the specific one for the private source and let a
    reduced artifact inherit a class nobody assigned to it.
    """
    best, best_length = None, -1
    for item in registry.values():
        candidate = str(item.get("match", "")).replace("\\", "/").lower()
        if candidate and _matches(candidate, path) and len(candidate) > best_length:
            best, best_length = item, len(candidate)
    return best


def _receipt_source_problem(
    receipt: Dict[str, Any],
    registry: Dict[str, Dict[str, Any]],
    artifact_path: Path,
) -> tuple:
    """Check that a receipt describes a real reduction of a registered source.

    Returns ``(source_data_class, problem)``; ``problem`` is empty when the
    receipt is structurally sound. A receipt naming no known source, or signing
    bytes identical to its source, is refused rather than believed.
    """
    declared_source = str(receipt.get("source_path", "")).strip()
    if not declared_source:
        return "", "receipt_without_registered_source"

    source_record = _registry_entry_for(registry, Path(declared_source))
    if source_record is None:
        return "", "receipt_without_registered_source"

    source_class = str(source_record.get("data_class", "")).upper()
    if source_class not in RESTRICTED_CLASSES:
        return source_class, "receipt_source_not_restricted"

    artifact_class = str(receipt.get("data_class", "")).upper()
    if artifact_class not in DATA_CLASSES:
        return source_class, "receipt_unknown_class"

    source_sha = str(receipt.get("source_sha256", "")).lower()
    if not source_sha:
        return source_class, "receipt_without_source_hash"
    if source_sha == str(receipt.get("artifact_sha256", "")).lower():
        # Nothing was removed. The artifact is the source, and signing it a
        # lower class would move a label rather than remove a byte.
        return source_class, "receipt_claims_unaltered_source"

    # Only ever a reduction.
    if artifact_class == source_class:
        return source_class, "receipt_class_unchanged"
    if artifact_class in LOCAL_ONLY_CLASSES:
        return source_class, "receipt_raises_data_class"
    return source_class, ""


def classify_source(
    source: Dict[str, Any],
    *,
    registry: Dict[str, Dict[str, Any]],
    root: Path,
) -> Dict[str, Any]:
    """Resolve one instruction file to a data class and the basis for it."""
    path = Path(str(source.get("path", "")))
    sha256 = str(source.get("sha256", ""))

    # Set by the first receipt that covers this file but does not hold up. The
    # reason rides along on the registry record so a refused receipt is visible
    # rather than silently bypassed.
    receipt_problem, receipt_source_class = "", ""

    for receipt in _read_receipts(root):
        # Hash binding is the authority, not the path. A receipt certifies
        # content: identical bytes are identical content whatever directory they
        # are staged into, and the delivery stage copies the reduction into a
        # scratch workspace precisely so the private manual is not in scope.
        # Requiring the recorded path to match would force the receipt to
        # name a staging directory that does not exist yet.
        if str(receipt.get("artifact_sha256", "")).lower() != sha256.lower():
            continue
        if receipt.get("acceptance") != ACCEPTANCE:
            continue

        # A receipt lowers a class by removing content. It may never raise one,
        # and it may never sign the source's own bytes: handing the gate PUBLIC
        # alongside the original private bytes removes nothing at all, and
        # validate_data_boundary cannot catch that because it inspects the class
        # it is told rather than where the content came from.
        source_class, problem = _receipt_source_problem(receipt, registry, path)
        if problem == "receipt_source_not_restricted":
            # Malformed rather than useless: someone signed a "sanitisation"
            # over a source that was never restricted. Refuse rather than let a
            # bare-name registry entry manufacture egress.
            receipt_problem = receipt_source_class = problem
            continue
        if problem:
            # A refused receipt must not shadow a legitimate classification.
            # Fall through to the registry below and carry the reason.
            receipt_problem = problem
            receipt_source_class = source_class
            continue

        artifact_class = str(receipt.get("data_class", "")).upper()
        verdict = validate_data_boundary(
            {"data_class": artifact_class},
            target="MODEL_CONTEXT",
            payload=path.read_text(encoding="utf-8", errors="replace")
            if path.is_file() else "",
        )
        if verdict["valid"]:
            return {
                "path": str(path),
                "sha256": sha256,
                "data_class": artifact_class,
                "basis": "sanitizer_receipt",
                "receipt_id": str(receipt.get("receipt_id", "")),
                "source_data_class": source_class,
                "source_sha256": str(receipt.get("source_sha256", "")),
            }
        return {
            "path": str(path),
            "sha256": sha256,
            "data_class": artifact_class,
            "basis": "sanitizer_receipt_rejected",
            "errors": list(verdict["errors"]),
        }

    record = _registry_entry_for(registry, path)
    if record is not None:
        classified = {
            "path": str(path),
            "sha256": sha256,
            "data_class": str(record.get("data_class", "")).upper(),
            "basis": "registry",
            "decided_by": str(record.get("decided_by", "")),
            "decided_at": str(record.get("decided_at", "")),
            "evidence": str(record.get("evidence", "")),
        }
        if receipt_problem:
            classified["ignored_receipt"] = receipt_problem
            classified["source_data_class"] = receipt_source_class
        return classified

    return {
        "path": str(path),
        "sha256": sha256,
        "data_class": "",
        "basis": "unclassified",
        "ignored_receipt": receipt_problem,
        "source_data_class": receipt_source_class,
    }


def evaluate_instruction_set(
    sources: Iterable[Dict[str, Any]],
    *,
    root: Optional[str] = None,
    scan_complete: bool = True,
) -> Dict[str, Any]:
    """Decide whether this instruction set may reach a hosted model.

    Fail closed in four places: an unclassified file, a local-only class, a
    conditional class without a live receipt, and an incomplete enumeration.
    The verdict names every file so a blocked receipt explains itself.
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

    if not scan_complete:
        # The nested scan stopped at its bound. Reporting the files it did find
        # would read as a checked set when part of the surface is simply
        # unexamined, which is the failure this whole gate exists to prevent.
        blocked.append("instruction_scan_incomplete:nested_files_unenumerated")

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
        complete = True
        if workspace.is_dir():
            found, complete = _instruction_files_for(workspace)
            sources = [
                {"path": str(item["path"]), "sha256": item["sha256"], "bytes": item["bytes"]}
                for item in found
            ]
        verdict = evaluate_instruction_set(
            sources, root=str(base), scan_complete=complete,
        )
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


def _instruction_files_for(workspace: Path):
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