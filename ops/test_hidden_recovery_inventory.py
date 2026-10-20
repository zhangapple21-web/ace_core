import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from ops import remote_recovery_inventory as inventory


class HiddenRecoveryInventoryTests(unittest.TestCase):
    def test_secret_files_and_generated_environments_are_not_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("state.sqlite", "state.sqlite-wal", "events.jsonl", "uv.lock", ".env", "cookies.db", "secret.db"):
                (root / name).write_text("DO_NOT_READ_VALUE", encoding="utf-8")
            (root / ".venv").mkdir()
            (root / ".venv" / "hidden.db").touch()
            (root / ".hidden").mkdir()
            (root / ".hidden" / "memory.db").touch()
            with patch.object(Path, "read_text", side_effect=AssertionError("content read")), \
                    patch.object(Path, "read_bytes", side_effect=AssertionError("content read")):
                result = inventory.filesystem_metadata([tmp])
            names = {Path(row["path"]).name for row in result["records"]}
            self.assertEqual(names, {"state.sqlite", "state.sqlite-wal", "events.jsonl", "uv.lock", "memory.db"})
            self.assertNotIn("DO_NOT_READ_VALUE", json.dumps(result))
            self.assertEqual(result["database_consistency"], "UNVERIFIED_NO_DB_OPEN_OR_SNAPSHOT")

    def test_limits_are_not_reported_as_complete(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "state.db").touch()
            result = inventory.filesystem_metadata([tmp], max_entries=0)
            self.assertEqual(result["status"], "PARTIAL")
            self.assertTrue(result["truncated"])
        result = inventory.filesystem_metadata([str(Path(tmp) / "missing")])
        self.assertEqual(result["status"], "PARTIAL")

    def test_remote_credentials_and_stderr_never_enter_evidence(self):
        secret = "DO_NOT_PRINT_TOKEN"
        url = f"https://user:{secret}@example.org/repo.git?token={secret}"
        with patch.object(inventory, "_run", return_value=(1, "", f"fatal: {url}")):
            evidence = asdict(inventory.inventory_remote("owner/repo", url))
        self.assertNotIn(secret, json.dumps(evidence))
        self.assertEqual(evidence["recovery_state"], "REMOTE_UNAVAILABLE")
        self.assertEqual(inventory.safe_remote_url("https://example.org/repo.git"), "https://example.org/repo.git")

    def test_only_environment_names_enter_hidden_evidence(self):
        with patch.dict(inventory.os.environ, {"ACE_TEST_SECRET": "DO_NOT_PRINT_VALUE"}, clear=True), \
                patch.object(inventory, "filesystem_metadata", return_value={"repositories": []}), \
                patch.object(inventory, "windows_metadata", return_value={"status": "UNKNOWN"}), \
                patch.object(inventory, "drive_metadata", return_value=[]), \
                patch.object(inventory, "_observe", return_value={"status": "UNKNOWN"}), \
                patch.object(inventory.importlib.metadata, "distributions", return_value=[]):
            evidence = inventory.hidden_dependencies([])
        self.assertEqual(evidence["environment_names"], ["ACE_TEST_SECRET"])
        self.assertNotIn("DO_NOT_PRINT_VALUE", json.dumps(evidence))
        self.assertEqual(evidence["status"], "PARTIAL")
        self.assertFalse(evidence["policy"]["copy_venv_node_modules_cache"])


if __name__ == "__main__":
    unittest.main()
