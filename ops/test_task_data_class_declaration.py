"""A task's data class must describe its payload, not inherit a default.

Measured 2026-10-19. Every task was born `data_class=PRIVATE` because that is
`create_task`'s default and nothing ever changed it: 1418 of 2173 tasks carried
PRIVATE, none by explicit request, and of the 94 that recorded whether a model
took part, zero did. Every attempt hit
`DATA_BOUNDARY_BLOCKED:sensitive_data_cannot_egress`.

The three tasks this audit submitted to test closure show what that costs. They
are research tasks whose entire method is a model call, they ran the full
lifecycle, and they finished with `candidate_basis: title_keywords_only` - a
tokenisation of their own titles - then archived with an outcome receipt. The
receipt said PENDING_EXTERNAL_VERIFICATION, so the system was honest about the
result; what was broken is upstream, where a label nobody chose prevented the
work from ever happening.

The boundary rule is not what changed and must not: PRIVATE and CORE still
cannot reach MODEL_CONTEXT, and credential-like content is still refused at
every egress target whatever the class says. What changed is that a discovery
candidate now declares its class from what it will actually carry, and the
default remains the safe answer - a candidate has to earn its way out.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from core.observation_to_task import _declare_data_class
from core.mirror_constitution import contains_credential_like_content, validate_data_boundary

# Long enough to match the credential patterns, which require 20-24+ characters
# so that ordinary prose does not trip them.
LONG_SK = "sk-proj-abcdefghijklmnopqrstuvwxyz0123456789"
LONG_GHP = "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ012345"


def test_local_facts_declare_public():
    """git output, counts and pointers are what a research prompt is made of."""
    admission = {"evidence": [
        {"source_ref": "git:rev-list --left-right --count main...HEAD"},
        {"source_ref": "audit:main_merge_decision_20261018.json"},
    ]}
    assert _declare_data_class(admission) == "PUBLIC"


def test_credential_shaped_evidence_stays_private():
    for blob in (
        f"api_key={LONG_SK}",
        f"token: {LONG_GHP}",
        f"authorization: Bearer {LONG_SK}",
    ):
        assert _declare_data_class(
            {"evidence": [{"source_ref": "config:x", "detail": blob}]}
        ) == "PRIVATE", f"credential-shaped detail escaped: {blob}"


def test_uncertain_shapes_fall_back_to_private():
    """Everything the function cannot read confidently must stay PRIVATE.

    Each of these is a way for real content to hide from a whitelist check:
    no evidence at all, a bare string instead of a record, or a nested
    structure where quoted document bytes could sit.
    """
    for admission in (
        {"evidence": []},
        {},
        {"evidence": ["a bare string"]},
        {"evidence": [{"source_ref": "x", "nested": {"quoted": "bytes"}}]},
        {"evidence": [{"source_ref": "x", "blob": ["a", "b"]}]},
    ):
        assert _declare_data_class(admission) == "PRIVATE", admission


def test_a_declared_public_class_does_not_weaken_the_boundary():
    """The label earns egress; the rules still govern what leaves."""
    assert validate_data_boundary({"data_class": "PUBLIC"}, target="MODEL_CONTEXT")["valid"]
    for blocked in ("PRIVATE", "CORE"):
        result = validate_data_boundary({"data_class": blocked}, target="MODEL_CONTEXT")
        assert not result["valid"], f"{blocked} must still be refused"
        assert "sensitive_data_cannot_egress" in result["errors"]

    # Credential content is refused at every egress target, whatever the class.
    for dc in ("PUBLIC", "CAPABILITY", "STRUCTURE"):
        result = validate_data_boundary(
            {"data_class": dc}, target="PUBLIC", payload=f"key={LONG_SK}"
        )
        assert not result["valid"], f"{dc} leaked credential content"
        assert "credential_like_content_detected" in result["errors"]


def test_the_default_is_untouched():
    """PRIVATE stays the default, so callers that say nothing lose nothing."""
    import inspect

    from core.task import TaskPool

    sig = inspect.signature(TaskPool.create_task)
    assert sig.parameters["data_class"].default == "PRIVATE"


def test_provenance_is_recorded_on_the_task():
    """A reader must be able to tell a chosen class from an inherited one."""
    import inspect

    from core.task import TaskPool

    src = inspect.getsource(TaskPool.create_task)
    assert "data_class_provenance" in src, (
        "the source of the class must be written onto the record"
    )


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))