from pathlib import Path

from ace_daemon import AceDaemon
from core.file_scanner import FileScanner
from core.fragment_index import FragmentIndex
from core.task import TaskPool


def test_production_file_scanner_stays_inside_authorized_workspace(
    tmp_path, monkeypatch
):
    workspace = tmp_path / "workspace"
    ace_root = workspace / "ace_core"
    ace_root.mkdir(parents=True)

    outside_home = tmp_path / "operator_home"
    (outside_home / "Downloads").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: outside_home))

    daemon = AceDaemon(ace_root, {})
    authorized_root = workspace.resolve()
    scan_roots = [root.resolve() for root in daemon.file_scanner.scan_roots]

    assert scan_roots
    assert all(
        root == authorized_root or root.is_relative_to(authorized_root)
        for root in scan_roots
    ), scan_roots


def test_production_observation_only_scan_does_not_create_taskpool_work(tmp_path):
    scan_root = tmp_path / "workspace"
    scan_root.mkdir()
    fragment = scan_root / "candidate.md"
    fragment.write_text("one local observation is not independent evidence", encoding="utf-8")

    ace_root = tmp_path / "ace_core"
    pool = TaskPool(str(ace_root / "task_pool"))
    index = FragmentIndex(str(ace_root / "02_FRAGMENT_INDEX"))
    scanner = FileScanner(pool, index, [scan_root])

    result = scanner.scan_and_create(max_new=2, allow_task_creation=False)

    assert result["new_files"] == 1
    assert result["tasks_created"] == 0
    assert result["unadmitted_observations"] == 1
    assert pool.list_tasks() == []
    assert index.is_known(fragment)
    assert index.index[str(fragment.resolve())]["status"] == "observed_unadmitted"
