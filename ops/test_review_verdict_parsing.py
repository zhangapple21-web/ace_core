"""Tests for parse_review_verdict: the verdict line, never the prose.

On 2026-10-13 the "CONTRADICTED" count across a whole sweep turned out to be
reviews *discussing* the word while concluding CANNOT_ASSESS - one wrote
"应为CANNOT_ASSESS而非CONTRADICTED", another "confirmed or contradicted the
pattern" before its VERDICT: CANNOT_ASSESS line. Substring matching counted
the discussion as the verdict and manufactured dissent where the readers
agreed. These tests use those shapes verbatim so the bug cannot return.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.free_zone_external_reviewer import parse_review_verdict  # noqa: E402


def test_clean_verdict_lines_parse():
    assert parse_review_verdict("INDEPENDENT: x\nGAP: y\nVERDICT: SUPPORTED") == "SUPPORTED"
    assert parse_review_verdict("VERDICT: CONTRADICTED") == "CONTRADICTED"
    assert parse_review_verdict("verdict: cannot_assess") == "CANNOT_ASSESS"


def test_markdown_bold_verdict_label_is_parsed():
    detail = (
        "**INDEPENDENT:** The current snapshot is not independently verified.\n"
        "**GAP:** Inspect the source data.\n"
        "**VERDICT:** CANNOT_ASSESS — the source data was not supplied."
    )
    assert parse_review_verdict(detail) == "CANNOT_ASSESS"


def test_observed_markdown_bold_verdict_is_parsed():
    import json
    from pathlib import Path

    report = (
        Path(__file__).resolve().parents[1]
        / "07_SANDBOX"
        / "free_research"
        / "reports"
        / "external_review"
        / "EXP-EXTREVIEW-A3A6F3BCD80A18BD.json"
    )
    payload = json.loads(report.read_text(encoding="utf-8"))
    entry = next(
        review for review in payload["reviews"]
        if review.get("task_id") == "RQ-20261018-292"
        and review.get("reviewer") == "longcat"
    )
    assert parse_review_verdict(entry["detail"]) == "CANNOT_ASSESS"


def test_review_consumers_count_markdown_bold_verdict(tmp_path):
    import json

    from ops.external_evidence_gate import collect_reviews
    from ops.process_blocked_backlog import _outside_readers

    review_dir = (
        tmp_path
        / "07_SANDBOX"
        / "free_research"
        / "reports"
        / "external_review"
    )
    review_dir.mkdir(parents=True)
    report = {
        "tasks": ["RQ-BOLD-VERDICT-001"],
        "reviews": [{
            "reviewer": "longcat",
            "status": "REVIEWED",
            "detail": "**VERDICT:** CANNOT_ASSESS — missing source data.",
        }],
    }
    (review_dir / "EXP-EXTREVIEW-test.json").write_text(
        json.dumps(report), encoding="utf-8"
    )

    gate = collect_reviews(tmp_path)["RQ-BOLD-VERDICT-001"]
    backlog = _outside_readers(tmp_path)["RQ-BOLD-VERDICT-001"]
    assert gate.cannot_assess == 1
    assert gate.unparsed == 0
    assert backlog["cannot_assess"] == 1


def test_markdown_emphasis_is_allowed_around_verdict_label_and_value():
    assert parse_review_verdict("VERDICT:** CANNOT_ASSESS") == "CANNOT_ASSESS"
    assert parse_review_verdict("VERDICT: **CANNOT_ASSESS**") == "CANNOT_ASSESS"
    assert parse_review_verdict("**VERDICT**: **CANNOT_ASSESS**") == "CANNOT_ASSESS"


def test_discussion_of_a_verdict_is_not_the_verdict():
    """The live false positive: a review reasoning about CONTRADICTED."""
    detail = (
        "INDEPENDENT: 证据只提到巡检为error。\n"
        "GAP: 应检查失败明细。\n"
        "VERDICT: 能否撑起主张存疑。应为CANNOT_ASSESS而非CONTRADICTED，"
        "因为无可核细节。\n"
        "VERDICT: CANNOT_ASSESS"
    )
    assert parse_review_verdict(detail) == "CANNOT_ASSESS"


def test_confirmed_or_contradicted_in_prose_is_not_a_contradiction():
    """The second live false positive: 'confirmed or contradicted the pattern'."""
    detail = (
        "INDEPENDENT: The snippet contains no findings.\n"
        "GAP: check whether RQ-20261008-007 confirmed or contradicted the pattern.\n"
        "VERDICT: CANNOT_ASSESS"
    )
    assert parse_review_verdict(detail) == "CANNOT_ASSESS"


def test_the_last_verdict_line_wins():
    """A review reasons before it concludes; the conclusion is what counts."""
    detail = "VERDICT: SUPPORTED\non reflection, VERDICT: CANNOT_ASSESS"
    assert parse_review_verdict(detail) == "CANNOT_ASSESS"


def test_a_review_without_a_verdict_line_is_none():
    assert parse_review_verdict("INDEPENDENT: x\nGAP: y") is None
    assert parse_review_verdict("") is None
    assert parse_review_verdict("SUPPORTED appears here but never as a verdict") is None


def test_histogram_counts_parsed_verdicts_not_substrings():
    from core.free_zone_external_reviewer import FreeZoneExternalReviewer

    reviews = [
        {"status": "REVIEWED",
         "detail": "discusses CONTRADICTED at length\nVERDICT: CANNOT_ASSESS"},
        {"status": "REVIEWED", "detail": "VERDICT: SUPPORTED"},
        {"status": "REVIEWED", "detail": "no verdict line at all"},
        {"status": "UNAVAILABLE", "detail": ""},
    ]
    histogram = FreeZoneExternalReviewer._histogram(reviews)
    assert histogram.get("CANNOT_ASSESS") == 1
    assert histogram.get("SUPPORTED") == 1
    assert histogram.get("CONTRADICTED", 0) == 0
    assert histogram.get("REVIEWED_WITHOUT_VERDICT") == 1
    assert histogram.get("UNAVAILABLE") == 1
