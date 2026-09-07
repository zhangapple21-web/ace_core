import json
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_file_scanner_marks_new_task_as_known_and_allows_changed_file():
    from core.file_scanner import FileScanner
    from core.fragment_index import FragmentIndex
    from core.task import TaskPool

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        ace_root = root / "ace_core"
        scan_root = root / "fragments"
        scan_root.mkdir()
        fragment = scan_root / "evidence_graph.json"
        fragment.write_text('{"version": 1}', encoding="utf-8")
        index = FragmentIndex(str(ace_root / "02_FRAGMENT_INDEX"))
        scanner = FileScanner(TaskPool(str(ace_root / "task_pool")), index, [scan_root])

        first = scanner.scan_and_create(max_new=2)
        second = scanner.scan_and_create(max_new=2)
        assert first["tasks_created"] == 1
        assert second["new_files"] == 0
        assert second["tasks_created"] == 0
        assert index.index[str(fragment.resolve())]["status"] == "archaeologized"

        # A changed file is legitimate new evidence only after its earlier
        # archaeology task has closed; otherwise the existing open task owns
        # the source and must not be duplicated.
        first_task_id = first["tasks"][0].task_id
        assert scanner.task_pool.move_task(first_task_id, "graveyard", actor="test")
        fragment.write_text('{"version": 2}', encoding="utf-8")
        changed = scanner.scan_and_create(max_new=2)
        assert changed["tasks_created"] == 1


def test_file_scanner_duplicate_first_does_not_regress_later_files_to_pending():
    from core.file_scanner import FileScanner
    from core.fragment_index import FragmentIndex
    from core.task import TaskPool

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        ace_root = root / "ace_core"
        scan_root = root / "fragments"
        scan_root.mkdir()
        duplicate = scan_root / "a.json"
        later = scan_root / "b.json"
        duplicate.write_text('{"a": 1}', encoding="utf-8")
        later.write_text('{"b": 1}', encoding="utf-8")
        pool = TaskPool(str(ace_root / "task_pool"))
        scanner = FileScanner(pool, FragmentIndex(str(ace_root / "02_FRAGMENT_INDEX")), [scan_root])
        pool.create_task(
            "碎片考古: a.json", hypothesis="h", creator="test",
            admission={
                "source_type": "archaeology", "source_ref": "test:a",
                "why_now": "Existing work.", "evidence": [{"path": "a"}],
                "expected_result": "Bounded.", "verification_method": "Recheck.",
                "risk": "Test.", "estimated_scope": "one file",
            },
        )
        result = scanner.scan_and_create(max_new=1)
        assert result["tasks_created"] == 1
        assert scanner.fragment_index.index[str(duplicate.resolve())]["status"] == "duplicate_skip"
        assert scanner.fragment_index.index[str(later.resolve())]["status"] == "archaeologized"


def test_file_scanner_excludes_its_own_and_knowledge_aggregate_indexes():
    from core.file_scanner import FileScanner
    from core.fragment_index import FragmentIndex
    from core.task import TaskPool

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        ace_root = root / "ace_core"
        index_dir = ace_root / "02_FRAGMENT_INDEX"
        index_dir.mkdir(parents=True)
        (index_dir / "fragment_index.json").write_text("{}", encoding="utf-8")
        knowledge = ace_root / "09_KNOWLEDGE"
        knowledge.mkdir()
        (knowledge / "index.json").write_text("{}", encoding="utf-8")
        actual = root / "mine_seed" / "evidence.md"
        actual.parent.mkdir()
        actual.write_text("independent historical evidence", encoding="utf-8")
        scanner = FileScanner(TaskPool(str(root / "pool")), FragmentIndex(str(index_dir)), [root])

        result = scanner.scan_and_create(max_new=5)
        assert result["new_files"] == 1
        assert result["tasks_created"] == 1
        assert result["tasks"][0].outputs["source_file"] == str(actual)


def _archive(pool, task_id):
    active = pool.move_task(task_id, "active", actor="test")
    review = pool.move_task(task_id, "review", actor="test", task=active)
    approved = pool.move_task(task_id, "approved", actor="test", task=review)
    assert pool.move_task(task_id, "archived", actor="test", task=approved)


def test_archived_persistent_fragment_incident_is_suppressed_until_recovery_then_reopens():
    from core.observation import RuntimeObserver
    from core.observation_to_task import ObservationToTaskConverter
    from core.task import TaskPool

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        observer = RuntimeObserver(str(root / "observations"))
        pool = TaskPool(str(root / "pool"))
        observer.record("fragment backlog", {"pending_scan": 501}, severity="medium", source="runtime", category="gap")
        first = ObservationToTaskConverter(observer, pool).convert()
        task_id = first["details"][0]["task_id"]
        _archive(pool, task_id)

        observer.record("same backlog", {"pending_scan": 501}, severity="medium", source="runtime", category="gap")
        suppressed = ObservationToTaskConverter(observer, pool).convert()
        assert suppressed["tasks_created"] == 0
        assert suppressed["semantic_duplicates"] == 1

        observer.record("backlog cleared", {"pending_scan": 0}, severity="medium", source="runtime", category="gap")
        ObservationToTaskConverter(observer, pool).convert()
        observer.record("backlog returned", {"pending_scan": 501}, severity="medium", source="runtime", category="gap")
        reopened = ObservationToTaskConverter(observer, pool).convert()
        assert reopened["tasks_created"] == 1


def test_observation_dedupe_caches_are_versioned_and_bounded():
    from core.observation import RuntimeObserver
    from core.observation_to_task import ObservationToTaskConverter
    from core.task import TaskPool

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        data_dir = root / "observations"
        data_dir.mkdir()
        old = (datetime.now() - timedelta(days=60)).isoformat()
        recent = datetime.now().isoformat()
        (data_dir / "triggered_obs.json").write_text(json.dumps({
            "schema_version": 1,
            "entries": {f"obs-{i}": {"last_seen_at": old if i == 0 else recent} for i in range(600)},
        }), encoding="utf-8")
        (data_dir / "semantic_incidents.json").write_text(json.dumps({
            "fragment_backlog": {
                "schema_version": 1, "signature": "abc", "task_id": "t-1",
                "last_observed_at": old, "reason": "persistent_semantic_incident",
            }
        }), encoding="utf-8")
        converter = ObservationToTaskConverter(RuntimeObserver(str(data_dir)), TaskPool(str(root / "pool")))
        assert len(converter._triggered_cache) == converter._TRIGGERED_CACHE_MAX_ENTRIES
        assert "obs-0" not in converter._triggered_cache
        assert converter._semantic_incidents == {}
        converter._mark_triggered("new-observation")
        converter._save_triggered_cache()
        saved = json.loads((data_dir / "triggered_obs.json").read_text(encoding="utf-8"))
        assert saved["schema_version"] == 1
        assert len(saved["entries"]) <= converter._TRIGGERED_CACHE_MAX_ENTRIES
        assert all("last_seen_at" in entry for entry in saved["entries"].values())


def test_task_creator_does_not_recurse_from_its_own_experience_deposit():
    from core.task import TaskPool
    from core.task_creator import TaskCreator

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        pool = TaskPool(str(root / "pool"))
        source = pool.create_task(
            "curated independent observation",
            hypothesis="h",
            creator="teacher_curator",
            admission={
                "source_type": "system_observation",
                "source_ref": "test:independent-observation",
                "why_now": "Independent observed condition needs review.",
                "evidence": [{"observation": "independent"}],
                "expected_result": "Bounded finding.",
                "verification_method": "Recheck test observation.",
                "risk": "Test only.",
                "estimated_scope": "one observation",
            },
        )
        exp_dir = root / "09_KNOWLEDGE" / "pattern"
        exp_dir.mkdir(parents=True)
        (exp_dir / "EXP-independent.json").write_text(json.dumps({
            "experience_id": "EXP-independent", "conclusion": "independent finding", "source_task_id": source.task_id,
        }), encoding="utf-8")

        creator = TaskCreator(pool, root)
        first = creator.scan_and_create(max_new=2)
        assert len(first["tasks_created"]) == 1
        child = pool.load_task(first["tasks_created"][0])
        assert child.creator == "task_creator"

        (exp_dir / "EXP-descendant.json").write_text(json.dumps({
            "experience_id": "EXP-descendant", "conclusion": "derived validation", "source_task_id": child.task_id,
        }), encoding="utf-8")
        second = TaskCreator(pool, root).scan_and_create(max_new=2)
        assert second["tasks_created"] == []


def test_task_creator_does_not_turn_automatic_observation_experience_into_followup():
    from core.task import TaskPool
    from core.task_creator import TaskCreator

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        pool = TaskPool(str(root / "pool"))
        source = pool.create_task(
            "automatic runtime incident", hypothesis="h", creator="observation_to_task",
            admission={
                "source_type": "system_observation", "source_ref": "test:auto-observation",
                "why_now": "Runtime observed the incident.", "evidence": [{"observation": "test"}],
                "expected_result": "Bounded finding.", "verification_method": "Recheck.",
                "risk": "Test only.", "estimated_scope": "one observation",
            },
        )
        exp_dir = root / "09_KNOWLEDGE" / "pattern"
        exp_dir.mkdir(parents=True)
        (exp_dir / "EXP-auto.json").write_text(json.dumps({
            "experience_id": "EXP-auto", "conclusion": "automatic incident result", "source_task_id": source.task_id,
        }), encoding="utf-8")
        result = TaskCreator(pool, root).scan_and_create(max_new=2)
        assert result["tasks_created"] == []


def test_daily_growth_labels_created_local_tasks_without_claiming_completion():
    from core.daily_growth import DailyGrowthLedger
    from core.task import TaskPool

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        pool = TaskPool(str(root / "pool"))
        task = pool.create_task(
            "local scanner finding", hypothesis="h", creator="file_scanner",
            admission={
                "source_type": "archaeology", "source_ref": "test:fragment",
                "why_now": "A fragment changed.", "evidence": [{"path": "test"}],
                "expected_result": "Bounded archaeology.", "verification_method": "Recheck file.",
                "risk": "Test only.", "estimated_scope": "one file",
            },
        )
        task.created_at = "2026-08-27T09:00:00"
        pool.update_task(task)
        supply = DailyGrowthLedger(pool, str(root / "daily_growth.json")).build("2026-08-27")["cognitive_work_supply"]
        assert supply["tasks_created"] == 1
        assert supply["local_tasks_created"] == 1
        assert supply["local_task_source_counts"] == {"file_scanner": 1}
        assert "does not mean completed" in supply["accepted_work_semantics"]


if __name__ == "__main__":
    test_file_scanner_marks_new_task_as_known_and_allows_changed_file()
    test_file_scanner_duplicate_first_does_not_regress_later_files_to_pending()
    test_file_scanner_excludes_its_own_and_knowledge_aggregate_indexes()
    test_archived_persistent_fragment_incident_is_suppressed_until_recovery_then_reopens()
    test_task_creator_does_not_recurse_from_its_own_experience_deposit()
    test_task_creator_does_not_turn_automatic_observation_experience_into_followup()
    test_daily_growth_labels_created_local_tasks_without_claiming_completion()
    print("task quality governance checks passed")



