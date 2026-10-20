"""Mengpo runtime: forgetting is real, selective, bounded, and reversible.

The design question this module answers is the owner's: "what to forget matters
more than what to remember". Concretely, that means a dirty artifact with
nothing to replace it is REFUSED - because forgetting it removes what no other
artifact can carry. Every test below pins either that refusal or one of the
bounds that make deletion survivable.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.governance.mengpo_runtime import (
    MAX_PER_RUN,
    MengpoRuntime,
    assess,
    find_substitution,
)


def _concept(cid, name, category="fact", **extra):
    payload = {"id": cid, "name": name, "category": category}
    payload.update(extra)
    return payload


@pytest.fixture()
def runtime(tmp_path):
    return MengpoRuntime(tmp_path, protected=[])


# ------------------------------------------------------------------ substitution

def test_a_superseding_artifact_is_a_substitute():
    artifact = _concept("c1", "Gateway Log Shape")
    lexicon = {"concepts": [artifact,
                            _concept("c2", "Gateway Log Shape", superseded_by="c2")]}
    substitution = find_substitution(artifact, lexicon=lexicon)
    assert substitution is not None and substitution.kind == "substitute"


def test_a_memory_line_covering_the_category_is_a_substitute():
    artifact = _concept("c1", "some noisy detail", category="note")
    lines = [{"id": "L1", "category": "note"}]
    substitution = find_substitution(artifact, memory_lines=lines)
    assert substitution is not None and substitution.kind == "structured"


def test_a_later_artifact_citing_this_one_absorbs_it():
    artifact = {"experience_id": "EXP-A", "related": []}
    later = {"experience_id": "EXP-B", "related": ["EXP-A"]}
    substitution = find_substitution(artifact, experiences=[later])
    assert substitution is not None and substitution.kind == "absorbed"


def test_nothing_means_no_substitution():
    artifact = _concept("c1", "unique irreplaceable thing")
    assert find_substitution(artifact, lexicon={"concepts": [artifact]}) is None


# ------------------------------------------------------------------ the gate

def test_dirty_but_irreplaceable_is_refused():
    """The central refusal: forgetting this would punch a hole."""
    artifact = _concept("c1", "only record of a shape nothing else covers")
    verdict = assess(artifact, pollution_score=0.9,
                     lexicon={"concepts": [artifact]})
    assert verdict.forgettable is False
    assert "no substitution" in verdict.reason


def test_clean_but_substitutable_is_not_forgotten():
    """Dirty is the other half. Substitution alone is not a reason to forget."""
    artifact = _concept("c1", "shape")
    lexicon = {"concepts": [artifact, _concept("c2", "shape", superseded_by="c2")]}
    verdict = assess(artifact, pollution_score=0.0, lexicon=lexicon)
    assert verdict.forgettable is False
    assert "not polluted" in verdict.reason


def test_core_typed_is_never_forgettable_even_when_substitutable():
    artifact = _concept("c1", "an axiom-shaped note", category="axiom")
    lexicon = {"concepts": [artifact, _concept("c2", "an axiom-shaped note",
                                                superseded_by="c2")]}
    verdict = assess(artifact, pollution_score=0.95, lexicon=lexicon)
    assert verdict.forgettable is False
    assert "core" in verdict.reason


def test_a_protected_artifact_is_never_forgettable():
    artifact = _concept("c1", "protected thing")
    verdict = assess(artifact, pollution_score=0.95,
                     lexicon={"concepts": [artifact]},
                     protected=["c1"])
    assert verdict.forgettable is False
    assert "protected" in verdict.reason


# ------------------------------------------------------------------ real removal

def _seeded_lexicon(path, concept):
    store = path / "06_RUNTIME" / "ace" / "data" / "memory"
    store.mkdir(parents=True, exist_ok=True)
    target = store / "lexicon.json"
    target.write_text(json.dumps({"concepts": [concept]}, ensure_ascii=False),
                      encoding="utf-8")
    return target


def test_forgetting_removes_the_artifact_from_the_store(tmp_path, runtime):
    """This is what the original forget() never did."""
    concept = _concept("c1", "noisy shape")
    lexicon_path = _seeded_lexicon(tmp_path, concept)
    store_before = json.loads(lexicon_path.read_text(encoding="utf-8"))
    assert len(store_before["concepts"]) == 1

    report = runtime.run(
        lexicon={"concepts": [concept]},
        pollution_scores={"c1": 0.95},
    )
    # refused, because nothing substitutes it - and the store is untouched
    assert report["counts"]["forgotten"] == 0
    assert report["refused"] and "no substitution" in report["refused"][0]["reason"]
    assert json.loads(lexicon_path.read_text(encoding="utf-8"))["concepts"], (
        "a refused forget must leave the store exactly as it was"
    )


def test_forgetting_a_substituted_artifact_removes_it_and_keeps_a_tombstone(tmp_path, runtime):
    concept = _concept("c1", "shape")
    _seeded_lexicon(tmp_path, concept)
    lexicon = {"concepts": [concept, _concept("c2", "shape", superseded_by="c2")]}

    report = runtime.run(lexicon=lexicon, pollution_scores={"c1": 0.95})
    assert report["counts"]["forgotten"] == 1, report
    entry = report["forgotten"][0]
    assert entry["applied"] is True
    assert entry["substitution"]["kind"] == "substitute"

    store = json.loads((tmp_path / "06_RUNTIME" / "ace" / "data" / "memory"
                        / "lexicon.json").read_text(encoding="utf-8"))
    assert [c["id"] for c in store["concepts"]] == [], (
        "the forgotten artifact must actually be gone from the store"
    )
    tombstones = list((tmp_path / "08_GOVERNANCE" / "civilization" / "graveyard"
                       / "runtime").glob("*.json"))
    assert len(tombstones) == 1
    tombstone = json.loads(tombstones[0].read_text(encoding="utf-8"))
    assert tombstone["payload"]["id"] == "c1", "recoverable: the payload is kept"

    # and the record now names what it affected - the field the old forget() left empty
    line = (tmp_path / "08_GOVERNANCE" / "decisions" / "mengpo_records.jsonl") \
        .read_text(encoding="utf-8").strip()
    record = json.loads(line.splitlines()[-1])
    assert record["affected_items"], "a real forget must name what it removed"
    assert record["substitution"]["kind"] == "substitute"


def test_a_dry_run_changes_nothing(tmp_path, runtime):
    concept = _concept("c1", "shape")
    _seeded_lexicon(tmp_path, concept)
    lexicon = {"concepts": [concept, _concept("c2", "shape", superseded_by="c2")]}
    before = (tmp_path / "06_RUNTIME" / "ace" / "data" / "memory"
              / "lexicon.json").read_text(encoding="utf-8")

    report = runtime.run(lexicon=lexicon, pollution_scores={"c1": 0.95},
                         dry_run=True)
    assert report["status"] == "DRY_RUN"
    assert report["counts"]["forgotten"] == 1
    assert report["forgotten"][0]["applied"] is False
    after = (tmp_path / "06_RUNTIME" / "ace" / "data" / "memory"
             / "lexicon.json").read_text(encoding="utf-8")
    assert before == after, "a dry run must not touch the store"
    assert not list((tmp_path / "08_GOVERNANCE" / "civilization" / "graveyard"
                     / "runtime").glob("*.json")), "and must not write a tombstone"


# ------------------------------------------------------------------ bounds

def test_a_refusal_still_records_the_run(tmp_path, runtime):
    concept = _concept("c1", "unique")
    _seeded_lexicon(tmp_path, concept)
    lexicon = {"concepts": [concept]}
    report = runtime.run(lexicon=lexicon, pollution_scores={"c1": 0.9})
    assert report["counts"]["refused"] == 1
    # cooldown applies even to a run that forgot nothing
    second = runtime.run(lexicon=lexicon, pollution_scores={"c1": 0.9})
    assert second["status"] == "NOT_DUE"
    assert "cooldown" in second["reason"]


def test_daily_cap_bounds_how_often_it_runs(tmp_path, runtime):
    from datetime import datetime, timedelta, timezone

    state_path = tmp_path / "08_GOVERNANCE" / "decisions" / "mengpo_runtime_state.json"
    past = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps({"runs": {datetime.now(timezone.utc)
                                               .date().isoformat(): 99},
                                      "last_run_at": past}), encoding="utf-8")
    report = runtime.run(lexicon={"concepts": []}, pollution_scores={})
    assert report["status"] == "NOT_DUE"
    assert "cap" in report["reason"]


def test_per_run_cap_bounds_a_single_sweep(tmp_path, runtime):
    """Even when everything qualifies, one run forgets at most MAX_PER_RUN."""
    concepts = [_concept(f"c{i}", "shape") for i in range(MAX_PER_RUN + 3)]
    substitute = _concept("sub", "shape", superseded_by="sub")
    lexicon = {"concepts": concepts + [substitute]}
    lexicon_path = _seeded_lexicon(tmp_path, concepts[0])
    lexicon_path.write_text(json.dumps(lexicon), encoding="utf-8")
    report = runtime.run(lexicon=lexicon,
                         pollution_scores={f"c{i}": 0.9 for i in range(MAX_PER_RUN + 3)},
                         dry_run=True)
    assert report["counts"]["forgotten"] == MAX_PER_RUN, (
        "one run must not unbuckle the whole store"
    )
