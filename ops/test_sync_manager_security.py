import tempfile
from pathlib import Path

import pytest

from core.sync_manager import SyncManager


def test_sync_manager_without_explicit_secret_refuses_signature_and_sync_execution():
    with tempfile.TemporaryDirectory() as directory:
        manager = SyncManager(data_dir=str(Path(directory) / "data"))

        with pytest.raises(ValueError, match="secret"):
            manager._generate_signature("plan", "2026-09-05T00:00:00")

        results = manager.execute_plan({"decisions": []})

        assert results[0].success is False
        assert "secret" in results[0].error


def test_sync_manager_uses_injected_repository_map_instead_of_hardcoded_user_path():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        configured_repo = root / "configured-mine-seed"
        manager = SyncManager(
            data_dir=str(root / "data"),
            curator_secret="test-secret",
            repo_map={"mine-seed": str(configured_repo)},
        )

        result = manager._sync_repo("mine-seed", [], {})

        assert result.success is False
        assert str(configured_repo) in result.error


