"""Minimized, zero-privilege context features for ACE Environment Awareness.

This module deliberately has no desktop, browser, clipboard, calendar, chat,
screen, process, network, daemon, TaskPool, model, or persistence dependency.
It implements only the first, opt-in implementation gate from
``ACE_ENVIRONMENT_AWARENESS_ARCHAEOLOGY_001``: a caller may describe the
identity of its current workspace as a short-lived feature, then turn that
feature into a *non-executing* shadow candidate for human review.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable


CONTRACT_VERSION = "ace.environment_context.v1"
PROJECT_SCOPE = "PROJECT"
_REQUIRED_KEYS = {
    "contract_version",
    "scope",
    "feature",
    "observed_at",
    "expires_at",
    "source_ref",
    "raw_retention",
    "production_integration",
}


def _as_utc(value: datetime | None) -> datetime:
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise ValueError("observed_at must include a timezone")
    return value.astimezone(timezone.utc)


def observe_workspace_identity(
    workspace: str | Path,
    *,
    observed_at: datetime | None = None,
    ttl_seconds: int = 900,
) -> dict[str, Any]:
    """Describe only a workspace's final path component as a context feature.

    This is intentionally not a filesystem scan: it neither lists, reads nor
    hashes project files.  The caller explicitly supplies the workspace it
    wants represented in its local audit/UI.
    """
    if ttl_seconds <= 0:
        raise ValueError("ttl_seconds must be positive")
    project_name = Path(workspace).name
    if not project_name:
        raise ValueError("workspace must name a project")
    observed = _as_utc(observed_at)
    return {
        "contract_version": CONTRACT_VERSION,
        "scope": PROJECT_SCOPE,
        "feature": f"project_identity={project_name}",
        "observed_at": observed.isoformat(),
        "expires_at": (observed + timedelta(seconds=ttl_seconds)).isoformat(),
        "source_ref": "local.workspace_identity.v1",
        "raw_retention": "NONE",
        "production_integration": False,
    }


def validate_context_feature(feature: dict[str, Any], *, now: datetime | None = None) -> None:
    """Enforce the narrow initial scope and reject raw or executable input."""
    missing = _REQUIRED_KEYS.difference(feature)
    if missing:
        raise ValueError(f"missing context fields: {sorted(missing)}")
    forbidden_raw = [key for key in feature if key.lower().startswith("raw") and key != "raw_retention"]
    if forbidden_raw:
        raise ValueError("raw environment payloads are forbidden")
    if feature["contract_version"] != CONTRACT_VERSION:
        raise ValueError("unsupported context contract version")
    if feature["scope"] != PROJECT_SCOPE:
        raise ValueError("only PROJECT scope is enabled by the first implementation gate")
    if feature["raw_retention"] != "NONE":
        raise ValueError("raw_retention must be NONE")
    if feature["production_integration"] is not False:
        raise ValueError("production_integration must be false")
    if not isinstance(feature["feature"], str) or not feature["feature"].startswith("project_identity="):
        raise ValueError("PROJECT feature must be a minimized project identity")

    observed_at = datetime.fromisoformat(str(feature["observed_at"]))
    expires_at = datetime.fromisoformat(str(feature["expires_at"]))
    if observed_at.tzinfo is None or expires_at.tzinfo is None:
        raise ValueError("context timestamps must include a timezone")
    if expires_at <= observed_at:
        raise ValueError("expires_at must be after observed_at")
    if expires_at <= _as_utc(now):
        raise ValueError("context feature has expired")


def build_shadow_candidate(
    features: Iterable[dict[str, Any]], *, generated_at: datetime | None = None
) -> dict[str, Any]:
    """Turn valid context into a deliberately inconclusive review candidate.

    Project identity by itself is never evidence of a user's intent.  This
    function therefore cannot create work, call a model, or identify a task.
    """
    created = _as_utc(generated_at)
    accepted = list(features)
    for feature in accepted:
        validate_context_feature(feature, now=created)
    return {
        "contract_version": "ace.shadow_context_candidate.v1",
        "candidate_kind": "SHADOW_CONTEXT_CANDIDATE",
        "generated_at": created.isoformat(),
        "status": "INCONCLUSIVE",
        "reason": "PROJECT identity alone cannot establish user intent or a research need.",
        "source_refs": [feature["source_ref"] for feature in accepted],
        "context_features": [feature["feature"] for feature in accepted],
        "human_confirmation_required": True,
        "egress": "EXISTING_WORK_DISCOVERY_AFTER_EXPLICIT_CONFIRMATION",
        "taskpool_task_created": False,
        "model_called": False,
        "production_integration": False,
        "forbidden_actions": [
            "automatic_task_creation",
            "model_call",
            "file_mutation",
            "message_send",
            "finance_decision",
        ],
    }
