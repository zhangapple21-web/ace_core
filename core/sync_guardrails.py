"""Sync guardrails for the Repository Curator execution hand.

Every one of these rules exists because a failure to judge must stop the
write, not proceed with a guess:

* ``ALLOWED_TARGET_REPOS`` is an explicit allowlist. A repository that is not
  on it is refused. The allowlist is the primary control.
* ``SECRET_TRACKED_PATTERNS`` is a backstop for repositories that do reach
  the allowlist but version secrets. It checks what git actually tracks
  rather than trusting the repository name.
* Path checks normalise with ``resolve()`` before comparison, so ``../``,
  absolute paths and symlinks cannot slip a target outside the allowed
  prefixes. Comparison is case-insensitive because Windows is.
* The staged index is compared against the intended file list before commit,
  because ``git commit`` takes everything that is staged, not just what this
  process added.
* Staged blob content is scanned for credential shapes. This catches the
  generated files (``memory_index*.json`` and friends) that a filename check
  cannot.
"""

import fnmatch
import logging
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)


# Repositories the curator may write to. Deliberately short: adding a name
# here is a governance decision, not a convenience.
ALLOWED_TARGET_REPOS: Tuple[str, ...] = (
    "ace_core",
)

# Repository names that must never be served regardless of the allowlist.
# mine-seed-credentials exists on this machine and tracks .env, so a path
# mistake must fail closed before any file is copied.
DENIED_REPO_NAME_PATTERNS: Tuple[str, ...] = (
    "*credential*",
    "*secret*",
    "*private*",
)

# Anything git tracks matching these is treated as a secret carrier.
SECRET_TRACKED_PATTERNS: Tuple[str, ...] = (
    ".env",
    ".env.*",
    "SECRET*",
    "*credential*",
    "*.token",
    "*.pem",
    "*.key",
    "*credentials*",
)

# Allowed write roots inside a target repository, relative to its root.
# Must stay a subset of whatever can_write() permits for the caller; this
# module is the execution backstop, not a second policy source.
ALLOWED_TARGET_PATH_PREFIXES: Tuple[str, ...] = (
    "docs/",
    "outputs/",
    "08_ARCHAEOLOGY/",
    "reports/",
)

# Paths the curator may never write, even inside an allowed repository.
# Tier1 is the constitution and civilization assets; writing there would
# bypass Admission entirely.
FORBIDDEN_TARGET_PATH_PREFIXES: Tuple[str, ...] = (
    "00_root/",
    "01_core/",
    "civilization_assets/",
    "lineage/",
    "04_protocols/",
    "core/",
    "06_runtime/",
    "09_knowledge/",
    "task_pool/",
    "07_sandbox/",
    "08_governance/",
)

# Credential shapes in staged content. Pattern set is deliberately broad;
# a false positive costs one refused sync, a false negative costs a secret.
_CREDENTIAL_VALUE_PATTERNS: Tuple[str, ...] = (
    r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----",
    r"\bsk-[A-Za-z0-9]{20,}",
    r"\bghp_[A-Za-z0-9]{20,}",
    r"\bgithub_pat_[A-Za-z0-9_]{20,}",
    r"\bAKIA[0-9A-Z]{16}\b",
    r"\bxox[baprs]-[A-Za-z0-9-]{10,}",
    r"\b(?:api[_-]?key|secret[_-]?key|access[_-]?token|client[_-]?secret)"
    r"\s*[:=]\s*[\"']?[A-Za-z0-9/+_-]{16,}",
)

_CREDENTIAL_RE = re.compile("|".join(_CREDENTIAL_VALUE_PATTERNS), re.IGNORECASE)


def _norm(value: str) -> str:
    """Normalise for comparison: forward slashes, case-folded, no trailing sep."""
    text = str(value or "").replace("\\", "/").strip()
    while text.endswith("/") and len(text) > 1:
        text = text[:-1]
    return text.casefold()


class SyncRefused(Exception):
    """A guardrail refused the operation. Always fail closed."""


def _rel_posix(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except (ValueError, OSError) as exc:
        # resolve() on a path that escapes the root raises, which is itself
        # the answer: refuse rather than guess.
        raise SyncRefused(f"path escapes repository root: {path}") from exc


def check_repo_allowed(repo: str, tracked_files: Optional[Sequence[str]] = None) -> None:
    """Raise SyncRefused unless the repository may be written to."""
    name = str(repo or "")
    lowered = name.casefold()

    for pattern in DENIED_REPO_NAME_PATTERNS:
        if fnmatch.fnmatch(lowered, pattern):
            raise SyncRefused(f"repo_name_denied:{name}:matches:{pattern}")

    if not any(lowered == allowed.casefold() for allowed in ALLOWED_TARGET_REPOS):
        raise SyncRefused(f"repo_not_allowlisted:{name}")

    if tracked_files is not None:
        for tracked in tracked_files:
            for pattern in SECRET_TRACKED_PATTERNS:
                if fnmatch.fnmatch(_norm(tracked), pattern.casefold()):
                    raise SyncRefused(
                        f"repo_tracks_secrets:{name}:{tracked}:matches:{pattern}"
                    )


def check_target_path(target_path: str, repo_root: Path) -> str:
    """Validate one target path inside a repository and return it normalised.

    Resolution happens before comparison so a symlink or ``..`` segment
    cannot land outside the allowed prefixes.
    """
    raw = _norm(target_path)
    if not raw:
        raise SyncRefused("target_path_empty")

    if raw.startswith("/") or re.match(r"^[a-z]:", raw):
        raise SyncRefused(f"target_path_absolute:{target_path}")

    if ".." in Path(raw).parts:
        raise SyncRefused(f"target_path_traversal:{target_path}")

    repo_root = Path(repo_root)
    candidate = (repo_root / raw).resolve()
    relative = _rel_posix(candidate, repo_root).casefold()

    for prefix in FORBIDDEN_TARGET_PATH_PREFIXES:
        if relative == prefix.rstrip("/") or relative.startswith(prefix):
            raise SyncRefused(f"target_path_forbidden_tier:{target_path}:{prefix}")

    allowed = False
    for prefix in ALLOWED_TARGET_PATH_PREFIXES:
        normalised_prefix = _norm(prefix)
        if relative == normalised_prefix.rstrip("/") or relative.startswith(normalised_prefix):
            allowed = True
            break
    if not allowed:
        raise SyncRefused(f"target_path_not_allowlisted:{target_path}")

    return relative


def git_tracked_files(repo_root: Path) -> List[str]:
    """Return what git tracks, or raise so the caller fails closed."""
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise SyncRefused(f"git_ls_files_unavailable:{exc}") from exc
    if completed.returncode != 0:
        raise SyncRefused(f"git_ls_files_failed:{completed.stderr.strip()[:120]}")
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def staged_files(repo_root: Path) -> List[str]:
    """Return the staged index, or raise so the caller fails closed."""
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise SyncRefused(f"git_diff_cached_unavailable:{exc}") from exc
    if completed.returncode != 0:
        raise SyncRefused(f"git_diff_cached_failed:{completed.stderr.strip()[:120]}")
    return sorted(_norm(line) for line in completed.stdout.splitlines() if line.strip())


def check_staged_matches_intended(repo_root: Path, intended: Sequence[str]) -> None:
    """Refuse unless the staged index is exactly what we meant to add."""
    staged = staged_files(repo_root)
    expected = sorted({_norm(item) for item in intended})
    if staged != expected:
        extra = sorted(set(staged) - set(expected))
        missing = sorted(set(expected) - set(staged))
        raise SyncRefused(f"staged_index_mismatch:extra={extra}:missing={missing}")


def scan_staged_for_secrets(repo_root: Path, staged: Sequence[str]) -> None:
    """Read the staged blob content, not the working file, and refuse on a hit."""
    for relative in staged:
        try:
            completed = subprocess.run(
                ["git", "-C", str(repo_root), "show", f":{relative}"],
                capture_output=True,
                text=True,
                timeout=30,
                encoding="utf-8",
                errors="replace",
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise SyncRefused(f"git_show_staged_unavailable:{relative}:{exc}") from exc
        if completed.returncode != 0:
            raise SyncRefused(f"git_show_staged_failed:{relative}")
        match = _CREDENTIAL_RE.search(completed.stdout or "")
        if match:
            raise SyncRefused(
                f"secret_in_staged_content:{relative}:pattern_match_at:{match.start()}"
            )


__all__ = [
    "ALLOWED_TARGET_REPOS",
    "ALLOWED_TARGET_PATH_PREFIXES",
    "DENIED_REPO_NAME_PATTERNS",
    "FORBIDDEN_TARGET_PATH_PREFIXES",
    "SECRET_TRACKED_PATTERNS",
    "SyncRefused",
    "check_repo_allowed",
    "check_staged_matches_intended",
    "check_target_path",
    "git_tracked_files",
    "scan_staged_for_secrets",
    "staged_files",
]