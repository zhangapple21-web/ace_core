"""Submit the audit's open decisions to the TaskPool through the governed path.

Three decisions were deferred to the owner during the 2026-10-18 audit. The
repository's own operating manual says not to do that:

    "Never ask the owner to perform this routine integration or to discover
     that a report was incomplete."

and the system has a path for exactly this - observation -> admission ->
TaskPool -> Researcher -> Validator -> Guardian. Writing them as candidates
instead of parking them in a report hands the choice to the machinery that was
built to make it, rather than to the one person who has to watch.

Each candidate is written with RuntimeObserver.record(), the same public API
the daemon itself uses, carrying a discovery payload shaped to
autonomous_maintenance_contract. ModelTaskAdmission then decides eligibility; a
candidate that does not earn its place is rejected with a reason rather than
silently queued.

Run read-only first (no --apply) to see what admission makes of them.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from core.observation import RuntimeObserver
from core.model_task_admission import ModelTaskAdmission

OBS_DIR = REPO / "06_RUNTIME" / "ace" / "data" / "observations"


def _candidate(
    *,
    fingerprint: str,
    title: str,
    objective: str,
    question: str,
    expected: str,
    verification: str,
    evidence: list,
    priority: str = "high",
    source: str = "audit_2026_10_18",
):
    return {
        "fingerprint": fingerprint,
        "title": title,
        "reason": "The full-domain audit deferred a decision it is not the right party to make.",
        "objective": objective,
        "completion_criteria": expected,
        "verification_method": verification,
        "priority": priority,
        "route": "governed_research",
        "candidate_source": source,
        "research_question": question,
        "expected_result": expected,
        "autonomous_maintenance": {
            "why_now": (
                "Measured on 2026-10-18 and unchanged since; the owner was asked a "
                "question the runtime is built to answer."
            ),
            "evidence": evidence,
            "priority": priority,
            "expected_result": expected,
            "verification_method": verification,
            "risk": "Governance decision only. Neither candidate authorises itself.",
            "source": source,
            "estimated_scope": "one bounded research turn",
        },
    }


CANDIDATES = [
    _candidate(
        fingerprint="audit-2026-10-18-main-merge",
        title="Decide whether to merge the 217-commit branch into main",
        objective=(
            "Produce a merge decision for core/daemon-lifecycle-resilience-20260912 "
            "into main, with the risk named."
        ),
        question=(
            "main holds one commit (0143169, lifecycle-init resilience) that this "
            "branch does not, and it edits ace_daemon.py - the file the sole running "
            "daemon executes, rewritten 225 times on this branch. Is a merge safe now?"
        ),
        expected=(
            "Either a merge plan with the ace_daemon.py conflict resolution specified, "
            "or a deferral naming the exact blocker and the evidence that would clear it."
        ),
        verification=(
            "Reproduce the protected failure (lifecycle init raising) in a scratch tree "
            "with the merged file and confirm the TaskPool survives. Never in production."
        ),
        evidence=[
            {
                "source_ref": "git:rev-list --left-right --count main...HEAD",
                "detail": "1 commit unique to main, 225 unique to the branch.",
            },
            {
                "source_ref": "audit:main_merge_decision_20261018.json",
                "detail": (
                    "0143169 touches ace_daemon.py (+49/-15). No test exercises that "
                    "failure path independently, so the suite cannot prove the merge is safe."
                ),
            },
            {
                "source_ref": "git:merge-base --is-ancestor main HEAD",
                "detail": "false - this is a real three-way merge, not a fast-forward.",
            },
        ],
    ),
    _candidate(
        fingerprint="audit-2026-10-18-knowledge-reuse",
        title="Decide whether knowledge_reuse may be enabled before its gates pass",
        objective=(
            "Decide whether KnowledgeReuseGate may run, given that its own preconditions "
            "are unmet."
        ),
        question=(
            "knowledge_reuse is wired but disabled; its join index is 9 days old against a "
            "7-day max and the A/B gate needs 300 labelled queries of which 0 exist. Is "
            "enabling it a measured step or a way to make DISABLED stop being a signal?"
        ),
        expected=(
            "A verdict on enablement, and if it is no, the smallest sequence of steps "
            "that would make it yes."
        ),
        verification=(
            "Rebuild the index and show coverage of tasks created since the last build; "
            "then run ops/assess_memory_index_migration.py to a real A/B result."
        ),
        evidence=[
            {
                "source_ref": "audit:knowledge_reuse_enablement_decision_20261018.json",
                "detail": "join_index built 2026-10-09, covers 876 of 2090 tasks, 0 of the 944 recent.",
            },
            {
                "source_ref": "core:knowledge_reuse.DEFAULTS",
                "detail": "enabled=false, mode=dry-run, index_max_age_days=7; absent from both config files.",
            },
            {
                "source_ref": "search:labelled_query_set",
                "detail": "0 artefacts across ops/**/*label*, *ab_*, *query_set*, 08_GOVERNANCE/**/*query*.",
            },
        ],
    ),
    _candidate(
        fingerprint="audit-2026-10-18-report-to-closure",
        title="Reports reach the TaskPool but never reach a repair",
        objective=(
            "Close the loop that turns a finished report into a completed fix, which the "
            "audit observed happening to itself twice."
        ),
        question=(
            "The 2026-10-17 audit and the 2026-10-18 one were both ingested as "
            "observations and both became tasks, and neither became a repair. What "
            "converts a report into a disposition, and who is accountable when it does not?"
        ),
        expected=(
            "A named owner and a transition for report-derived work, or a statement that "
            "reports are evidence only and the gap is accepted deliberately."
        ),
        verification=(
            "Trace one report end to end: file -> observation -> task -> terminal state, "
            "and show where a repair would have been decided."
        ),
        evidence=[
            {
                "source_ref": "ace_core:.task_creator_history.json",
                "detail": (
                    "2026-10-17's audit report appears in processed_files and produced "
                    "structural-gap tasks that were archived, not fixed."
                ),
            },
            {
                "source_ref": "audit:2026-10-18 report section 12bis",
                "detail": (
                    "The 2026-10-18 report was similarly turned into RQ-20261018-280/281, "
                    "both now blocked at the convergence ceiling."
                ),
            },
            {
                "source_ref": "AGENTS.md:autonomous_acceptance",
                "detail": (
                    "The manual already requires the main steward to accept or reject every "
                    "material conclusion, and forbids asking the owner to do routine integration."
                ),
            },
        ],
    ),
]


def main() -> int:
    apply = "--apply" in sys.argv
    observer = RuntimeObserver(data_dir=str(OBS_DIR))
    admission = ModelTaskAdmission()

    for cand in CANDIDATES:
        payload = {
            "source_type": "maintenance",
            "source_ref": cand["fingerprint"],
            "evidence": [
                {"source_ref": e["source_ref"], "detail": e["detail"]}
                for e in cand["autonomous_maintenance"]["evidence"]
            ],
            "research_question": cand["research_question"],
            "expected_result": cand["expected_result"],
            "verification_method": cand["verification_method"],
        }
        verdict = admission.evaluate(payload)
        print("=" * 72)
        print(cand["title"])
        print("  eligible      :", verdict["eligible"])
        print("  classification:", verdict["classification"])
        if verdict["reasons"]:
            print("  reasons       :", verdict["reasons"])
        print("  evidence_refs :", len(verdict["evidence_refs"]))

        if not verdict["eligible"]:
            print("  -> NOT submitted; admission declined it")
            continue
        if not apply:
            print("  -> would submit (dry run)")
            continue

        # `source` is not decoration. `_discovery_candidate` matches on
        # `obs.source == "discovery_mode"` (core/observation_to_task.py:173), so a
        # candidate submitted under any other label sits in the queue forever
        # looking like an unconverted observation. The first run of this script
        # used "audit" and left three candidates stranded that way - the audit
        # had spent the day finding orphaned work and then created some.
        #
        # The candidate itself carries candidate_source="audit_2026_10_18", so the
        # provenance is still on the task and visible in its tags; only the
        # channel label changes, to the one the converter recognises.
        obs = observer.record(
            description=cand["title"],
            system_state={"discovery": cand},
            severity="medium",
            source="discovery_mode",
            category="improvement",
            dedup_key=cand["fingerprint"],
        )
        print("  -> submitted as", obs.obs_id)

    print("=" * 72)
    if not apply:
        print("dry run. pass --apply to submit through the governed path.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())