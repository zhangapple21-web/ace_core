"""Regression tests for the zero-privilege Environment Awareness boundary."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.environment_context import (
    build_shadow_candidate,
    observe_workspace_identity,
    validate_context_feature,
)


NOW = datetime(2026, 8, 27, 18, 30, tzinfo=timezone.utc)


def test_workspace_identity_observation_is_minimized_and_non_executing(tmp_path):
    workspace = tmp_path / "ace_core"
    workspace.mkdir()

    feature = observe_workspace_identity(workspace, observed_at=NOW, ttl_seconds=300)

    assert feature == {
        "contract_version": "ace.environment_context.v1",
        "scope": "PROJECT",
        "feature": "project_identity=ace_core",
        "observed_at": "2026-08-27T18:30:00+00:00",
        "expires_at": "2026-08-27T18:35:00+00:00",
        "source_ref": "local.workspace_identity.v1",
        "raw_retention": "NONE",
        "production_integration": False,
    }


def test_only_project_scope_is_accepted_in_the_first_implementation_gate():
    feature = observe_workspace_identity("C:/tmp/ace_core", observed_at=NOW)
    feature["scope"] = "BROWSER_DOMAIN"

    with pytest.raises(ValueError, match="PROJECT"):
        validate_context_feature(feature, now=NOW)


def test_raw_payload_and_production_flags_are_rejected():
    feature = observe_workspace_identity("C:/tmp/ace_core", observed_at=NOW)
    feature["raw_payload"] = "sensitive"

    with pytest.raises(ValueError, match="raw"):
        validate_context_feature(feature, now=NOW)

    feature.pop("raw_payload")
    feature["production_integration"] = True
    with pytest.raises(ValueError, match="production_integration"):
        validate_context_feature(feature, now=NOW)


def test_context_only_forms_an_inconclusive_shadow_candidate():
    feature = observe_workspace_identity("C:/tmp/ace_core", observed_at=NOW)

    candidate = build_shadow_candidate([feature], generated_at=NOW)

    assert candidate["candidate_kind"] == "SHADOW_CONTEXT_CANDIDATE"
    assert candidate["status"] == "INCONCLUSIVE"
    assert candidate["human_confirmation_required"] is True
    assert candidate["taskpool_task_created"] is False
    assert candidate["model_called"] is False
    assert candidate["production_integration"] is False


