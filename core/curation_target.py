"""Shared contract between the curator's decisions and the syncer's input.

The two sides disagreed for the life of the system: ``value_scorer``
returned a path prefix in a field called ``target_repo`` ("09_KNOWLEDGE/",
"core/", "04_PROTOCOLS"), while ``SyncManager`` looked that value up in a
map of repository names. The curator therefore pointed at directories and
the syncer looked for repositories, so the two could never line up.

One dataclass owns both halves now. A decision carries the repository it
belongs to and the path inside it, and nothing is allowed to put a path in
the repository field.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

CONTRACT_VERSION = "ace.curation_target.v1"

# The repository every curation target belongs to until an owner names a
# different one. Empty on purpose: no repository is authorised for writing,
# and the staging area is not a repository at all.
DEFAULT_REPO = ""

# Directories inside a repository that a curator may target. This is a
# subset of the caller's write permission; it is an execution backstop, not
# a second policy source.
ALLOWED_PATH_PREFIXES: Tuple[str, ...] = (
    "docs/",
    "outputs/",
    "08_ARCHAEOLOGY/",
    "reports/",
)


@dataclass(frozen=True)
class CurationTarget:
    """Where one artefact is allowed to land.

    ``repo`` is a repository name. ``path_prefix`` is a path inside that
    repository. Keeping them apart is the whole point: a prefix in the repo
    field is what broke the original pairing.
    """

    repo: str = DEFAULT_REPO
    path_prefix: str = ""
    path: str = ""
    contract_version: str = CONTRACT_VERSION

    def __post_init__(self) -> None:
        for name in ("repo", "path_prefix", "path"):
            value = getattr(self, name)
            if not isinstance(value, str):
                raise TypeError(f"curation_target_{name}_must_be_str")
        if self.repo and (self.repo.endswith("/") or "/" in self.repo):
            raise ValueError(
                f"curation_target_repo_is_a_path:{self.repo}:"
                "use path_prefix for in-repository paths"
            )
        if self.path_prefix and not self.path_prefix.endswith("/"):
            raise ValueError(f"curation_target_path_prefix_not_a_prefix:{self.path_prefix}")
        if not self.path:
            raise ValueError("curation_target_path_required")

    @property
    def relative_path(self) -> str:
        return f"{self.path_prefix}{self.path}" if self.path_prefix else self.path

    def to_dict(self) -> Dict[str, Any]:
        return {
            "repo": self.repo,
            "path_prefix": self.path_prefix,
            "path": self.path,
            "relative_path": self.relative_path,
            "contract_version": self.contract_version,
        }


@dataclass(frozen=True)
class CurationDecision:
    """One curator decision, bound to the shared target contract."""

    artifact_id: str
    action: str  # create / update / merge / discard
    source_path: str
    target: CurationTarget
    reason: str = ""
    tags: Tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "action": self.action,
            "source_path": self.source_path,
            "target": self.target.to_dict(),
            "reason": self.reason,
            "tags": list(self.tags),
        }


def split_prefix(value: str) -> Tuple[str, str]:
    """Split a legacy "prefix/name" or bare "prefix/" into (prefix, name).

    ``value_scorer._determine_target`` used to return one string that mixed
    both concerns. This keeps the existing rule table working while making
    the split explicit at the boundary.
    """
    text = str(value or "").replace("\\", "/").strip()
    if not text:
        return "", ""
    if text.endswith("/"):
        return text, ""
    head, _, tail = text.rpartition("/")
    return (head + "/", tail) if head else ("", text)


def decision_from_dict(payload: Dict[str, Any]) -> CurationDecision:
    """Read a decision written by the curator, refusing a malformed target."""
    target = payload.get("target") or {}
    if not isinstance(target, dict):
        raise ValueError("curation_decision_target_not_an_object")
    missing = [key for key in ("repo", "path", "path_prefix") if key not in target]
    if missing:
        raise ValueError("curation_decision_target_missing:" + ",".join(missing))
    return CurationDecision(
        artifact_id=str(payload.get("artifact_id", "")),
        action=str(payload.get("action", "")),
        source_path=str(payload.get("source_path", "")),
        target=CurationTarget(
            repo=str(target.get("repo", "")),
            path_prefix=str(target.get("path_prefix", "")),
            path=str(target.get("path", "")),
        ),
        reason=str(payload.get("reason", "")),
        tags=tuple(payload.get("tags") or ()),
    )


__all__ = [
    "ALLOWED_PATH_PREFIXES",
    "CONTRACT_VERSION",
    "DEFAULT_REPO",
    "CurationDecision",
    "CurationTarget",
    "decision_from_dict",
    "split_prefix",
]