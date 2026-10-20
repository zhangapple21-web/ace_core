from pathlib import Path

from portable_paths import ROOTS, layout, resolve


def test_all_declared_roots_stay_inside_workspace(tmp_path: Path):
    paths = layout(tmp_path)
    assert set(paths) == set(ROOTS)
    for path in paths.values():
        assert tmp_path.resolve() == path or tmp_path.resolve() in path.parents


def test_layout_is_drive_agnostic(tmp_path: Path):
    workspace = tmp_path / "X_drive" / "ace_core"
    workspace.mkdir(parents=True)
    assert resolve(workspace, "config_local") == workspace / "ace_config.local.json"
    assert resolve(workspace, "events").is_relative_to(workspace)

