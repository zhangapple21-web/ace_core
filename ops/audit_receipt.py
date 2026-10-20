"""Machine verifier for independent-audit receipts (013 contract).

Validates structure and self-consistency only: SHAs exist in the repo,
diff digest matches a recomputed digest, author differs from reviewer,
verdict is in the closed set, test evidence is present. It never approves
merging; it only says whether the receipt itself is well-formed.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

VERDICTS = {"PASS", "REVISE", "BLOCKED"}
SCHEMA_VERSION = "ace.audit-receipt.v1"


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode != 0:
        raise ValueError("git_failed:" + " ".join(args) + ":" + completed.stderr.strip()[:160])
    return completed.stdout.strip()


def _commit_exists(repo: Path, sha: str) -> bool:
    try:
        _git(repo, "cat-file", "-e", sha + "^{commit}")
        return True
    except ValueError:
        return False


def _diff_digest(repo: Path, base_sha: str, head_sha: str) -> str:
    diff = subprocess.run(
        ["git", "-C", str(repo), "diff", f"{base_sha}...{head_sha}"],
        capture_output=True,
        timeout=120,
    )
    if diff.returncode != 0:
        raise ValueError("git_diff_failed")
    return hashlib.sha256(diff.stdout).hexdigest()


def verify_receipt(receipt: Dict[str, Any], repo: Path) -> Dict[str, Any]:
    """Return {valid, errors[], warnings[]} for one audit receipt."""
    errors: List[str] = []
    warnings: List[str] = []

    for field in (
        "base_sha", "head_sha", "diff_digest", "author", "reviewer_identity",
        "protocol_version", "behavior_scope", "threat_model", "test_evidence",
        "findings", "verdict",
    ):
        if field not in receipt or receipt[field] in (None, ""):
            # test_evidence may legitimately be empty only when verdict is BLOCKED
            if field == "test_evidence" and receipt.get("verdict") == "BLOCKED":
                continue
            errors.append("missing_field:" + field)
        elif field == "findings" and not isinstance(receipt[field], list):
            errors.append("missing_field:findings")
    if errors:
        return {"valid": False, "errors": errors, "warnings": warnings}

    if receipt.get("verdict") not in VERDICTS:
        errors.append("verdict_not_closed:" + str(receipt.get("verdict")))

    for sha_field in ("base_sha", "head_sha"):
        sha = str(receipt.get(sha_field) or "")
        if not _commit_exists(repo, sha):
            errors.append("unknown_commit:" + sha_field + ":" + sha[:12])

    if receipt.get("author") == receipt.get("reviewer_identity"):
        errors.append("reviewer_not_independent")

    if not errors:
        try:
            actual = _diff_digest(repo, str(receipt["base_sha"]), str(receipt["head_sha"]))
        except ValueError as exc:
            errors.append(str(exc))
        else:
            if actual != receipt.get("diff_digest"):
                errors.append("diff_digest_mismatch:receipt_stale_or_tampered")

    evidence = receipt.get("test_evidence") or {}
    if isinstance(evidence, dict) and not evidence.get("commands") and receipt.get("verdict") == "PASS":
        warnings.append("pass_without_test_commands")

    return {"valid": not errors, "errors": errors, "warnings": warnings}


def load_receipt(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


__all__ = ["SCHEMA_VERSION", "VERDICTS", "load_receipt", "verify_receipt"]
