import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import portable_paths
from recovery import bootstrap, path_audit, restore_from_remote as restore


def command_result(code=0, stdout="", stderr=""):
    return {"command": "mock", "returncode": code, "stdout": stdout,
            "stderr": stderr, "status": "PASS" if code == 0 else "FAIL"}


def checks(health="PASS", tests="PASS"):
    return [{"name": "compileall", "status": "PASS"},
            {"name": "health_check", "status": health},
            {"name": "pytest", "status": tests}]


class StatusTests(unittest.TestCase):
    def test_health_and_missing_tests_never_pass(self):
        for health in ("WARN", "SKIP", "NOT_READY", "FAIL"):
            with self.subTest(health=health):
                self.assertEqual(bootstrap.aggregate_status(checks(health)), "PARTIAL")
                self.assertEqual(restore.bootstrap_status(command_result(),
                                 {"status": "PASS", "checks": checks(health)}), "PARTIAL")
        for items in (checks(tests="SKIP"), checks()[:-1], [], checks()[::2]):
            with self.subTest(items=items):
                self.assertEqual(bootstrap.aggregate_status(items), "PARTIAL")
                self.assertEqual(restore.bootstrap_status(command_result(), {"checks": items}), "PARTIAL")

    def test_core_failure_takes_priority(self):
        items = checks("NOT_READY") + [{"name": "compileall", "status": "FAIL"}]
        self.assertEqual(bootstrap.aggregate_status(items), "FAIL")
        self.assertEqual(restore.bootstrap_status(command_result(3), {"checks": items}), "FAIL")
        self.assertEqual(restore.bootstrap_status(command_result(1), {"checks": checks()}), "FAIL")
        self.assertEqual(restore.bootstrap_status(command_result(), {"status": "FAIL", "checks": checks()}), "FAIL")

    def test_legacy_report_and_explicit_partial(self):
        self.assertEqual(bootstrap.aggregate_status(checks()), "PASS")
        self.assertEqual(restore.bootstrap_status(command_result(), {"checks": checks()}), "PASS")
        self.assertEqual(restore.bootstrap_status(command_result(3), {"checks": checks()}), "PARTIAL")
        self.assertEqual(restore.bootstrap_status(command_result(), {"status": "PARTIAL", "checks": checks()}), "PARTIAL")
        self.assertEqual(restore.bootstrap_status(command_result(), {"checks": checks()}, skip_tests=True), "PARTIAL")
        for malformed in ({}, {"checks": None}, {"checks": [None]}):
            self.assertEqual(restore.bootstrap_status(command_result(), malformed), "PARTIAL")

    def test_output_is_not_truncated(self):
        output = "x" * 10000
        proc = subprocess.CompletedProcess(["mock"], 1, output, output)
        with patch.object(bootstrap.subprocess, "run", return_value=proc):
            result = bootstrap.run(["mock"], Path("."), allow_warning=True)
        self.assertEqual(result["stdout"], output)
        self.assertEqual(result["stderr"], output)
        self.assertEqual(result["status"], "WARN")


class BootstrapTests(unittest.TestCase):
    def test_real_health_command_and_exit_codes(self):
        for health_code, skip, compile_code, expected in (
                (0, False, 0, 0), (1, False, 0, 3), (2, False, 0, 3),
                (0, True, 0, 3), (2, False, 1, 1)):
            with self.subTest(health_code=health_code, skip=skip, compile_code=compile_code):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    (root / ".git").mkdir()
                    (root / "recovery").mkdir()
                    (root / "recovery/path_audit.py").touch()
                    (root / "ops").mkdir()
                    (root / "ops/health_check.py").touch()
                    (root / "ops/test_task.py").touch()
                    (root / "ace_config.example.json").write_text('{"runtime": {}}', encoding="utf-8")
                    (root / "ace_config.local.json").write_text("preserve", encoding="utf-8")
                    commands = []

                    def fake_run(cmd, cwd, **kwargs):
                        commands.append(cmd)
                        if "--json" in cmd:
                            result = command_result(health_code, "health evidence", "health stderr")
                            result["status"] = "PASS" if health_code == 0 else "WARN"
                            return result
                        if "compileall" in cmd:
                            return command_result(compile_code)
                        return command_result(stdout="a" * 40)

                    argv = ["bootstrap", "--workspace-root", str(root)] + (["--skip-tests"] if skip else [])
                    with patch.object(bootstrap.sys, "argv", argv), patch.object(bootstrap.shutil, "which", return_value="git"), \
                            patch.object(bootstrap, "run", side_effect=fake_run), \
                            patch.object(bootstrap.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)), \
                            contextlib.redirect_stdout(io.StringIO()):
                        self.assertEqual(bootstrap.main(), expected)
                    report = json.loads((root / "recovery/bootstrap_report.json").read_text(encoding="utf-8"))
                    self.assertEqual(report["status"], {0: "PASS", 3: "PARTIAL", 1: "FAIL"}[expected])
                    health = next(item for item in report["checks"] if item["name"] == "health_check")
                    self.assertEqual(health["stdout"], "health evidence")
                    self.assertEqual(health["returncode"], health_code)
                    self.assertIn([bootstrap.sys.executable, str(root / "ops/health_check.py"), "--json"], commands)
                    self.assertEqual((root / "ace_config.local.json").read_text(), "preserve")
                    self.assertIn([bootstrap.sys.executable, str(root / "recovery/path_audit.py"),
                                   "--workspace-root", str(root)], commands)
                    self.assertEqual(report["portable_paths"]["runtime"], str(root / "runtime"))


class CloneTests(unittest.TestCase):
    def test_sha_parsing(self):
        for length in (40, 64):
            sha = "A" * length
            self.assertEqual(restore.parse_remote_head(f"{sha}\trefs/heads/main\n", "main"), sha.lower())
            self.assertEqual(restore.parse_remote_head(f"{sha}\trefs/heads/main\n", "refs/heads/main"), sha.lower())
        for output in ("", "bad refs/heads/main", f"{'a' * 40} refs/heads/other",
                       f"{'a' * 40} refs/heads/main\n{'b' * 40} refs/heads/main"):
            with self.subTest(output=output), self.assertRaises(RuntimeError):
                restore.parse_remote_head(output, "main")

    def test_head_mismatch_retains_failure_evidence(self):
        outputs = [f"{'a' * 40}\trefs/heads/main", "", "main", "b" * 40]
        result = {}
        with tempfile.TemporaryDirectory() as tmp, patch.object(restore, "run", side_effect=[command_result(stdout=x) for x in outputs]):
            with self.assertRaises(RuntimeError):
                restore.clone("offline", "main", Path(tmp) / "checkout", result=result)
        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(result["ref_match"])
        self.assertEqual(result["remote_head"], "a" * 40)
        self.assertEqual(result["checked_out_head"], "b" * 40)
        self.assertEqual(len(result["commands"]), 4)

    def test_refuse_overwrite_before_any_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            asset = root / "user_asset.txt"
            asset.write_text("keep", encoding="utf-8")
            with patch.object(restore, "run") as run:
                with self.assertRaises(RuntimeError):
                    restore.clone("offline", "main", root)
                run.assert_not_called()
            with patch.object(restore.sys, "argv", ["restore", "--workspace-root", str(root)]), \
                    patch.object(restore, "run") as run, contextlib.redirect_stderr(io.StringIO()):
                self.assertNotEqual(restore.main(), 0)
                run.assert_not_called()
            self.assertEqual(asset.read_text(), "keep")
            self.assertEqual(list(root.iterdir()), [asset])

    def test_coze_remote(self):
        self.assertIn(("coze-assets", "https://github.com/ACEE0011/coze-assets.git", "main"), restore.OPTIONAL_REPOS)


class OrchestratorTests(unittest.TestCase):
    def test_receipt_workspace_and_continuation(self):
        for code, health, declared, expected in (
                (0, "PASS", None, "PASS"), (0, "NOT_READY", None, "PARTIAL"),
                (0, "FAIL", "PASS", "PARTIAL"), (3, "WARN", "PARTIAL", "PARTIAL"),
                (1, "PASS", "FAIL", "FAIL")):
            with self.subTest(code=code, health=health, declared=declared), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / "restore"
                cloned = []
                commands = []

                def fake_clone(url, ref, destination, *, result):
                    cloned.append(destination.name)
                    destination.mkdir(parents=True)
                    result.update(status="PASS")
                    if destination.name == "ace_core":
                        (destination / "recovery").mkdir()
                        report = {"checks": checks(health)}
                        if declared is not None:
                            report["status"] = declared
                        (destination / "recovery/bootstrap_report.json").write_text(json.dumps(report), encoding="utf-8")
                    return result

                def fake_run(cmd, cwd):
                    commands.append(cmd)
                    return command_result(code if "recovery/bootstrap.py" in cmd else 0)

                argv = ["restore", "--workspace-root", str(root), "--with-video", "--with-optional"]
                with patch.object(restore.sys, "argv", argv), patch.object(restore.shutil, "which", return_value="git"), \
                        patch.object(restore, "clone", side_effect=fake_clone), patch.object(restore, "run", side_effect=fake_run), \
                        patch.object(restore, "OPTIONAL_REPOS", [("optional-test", "offline", "main")]), \
                        contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(restore.main(), {"PASS": 0, "PARTIAL": 3, "FAIL": 1}[expected])
                receipts = list(Path(tmp).rglob("ACE_REMOTE_RESTORE_RECEIPT.json"))
                self.assertEqual(len(receipts), 1)
                receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
                self.assertEqual(receipt["status"], expected)
                if expected == "FAIL":
                    self.assertFalse(root.exists())
                    self.assertTrue((receipts[0].parent / "workspace/ace_core").is_dir())
                    self.assertEqual(cloned, ["ace_core"])
                else:
                    self.assertTrue(root.is_dir())
                    self.assertEqual(receipts[0].parent, root)
                    self.assertEqual(cloned, ["ace_core", "ace-video-kingdom", "optional-test"])
                    self.assertEqual(len(commands), 3)


class PortableTests(unittest.TestCase):
    def test_layout_and_traversal_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "relocated workspace"
            paths = portable_paths.layout(root)
            self.assertEqual(paths["restore_core"], root / "ace_core")
            for value in paths.values():
                self.assertIn(root, value.parents)
            with self.assertRaises(ValueError):
                portable_paths.resolve(root, "restore_optional", "..", "..", "outside")
            with self.assertRaises(KeyError):
                portable_paths.resolve(root, "unknown")

    def test_subprocess_portable_environment_and_full_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = "evidence" * 2000
            proc = subprocess.CompletedProcess(["mock"], 0, output, "")
            with patch.dict(portable_paths.os.environ, {"ACE_WORKSPACE_ROOT": "stale"}):
                for module in (bootstrap, restore):
                    with patch.object(module.subprocess, "run", return_value=proc) as run:
                        result = module.run(["mock"], root)
                    self.assertEqual(run.call_args.kwargs["env"]["ACE_WORKSPACE_ROOT"], str(root))
                    self.assertEqual(result["stdout"], output)
                with patch.object(restore.subprocess, "run", return_value=proc) as run:
                    restore.run(["git", "ls-remote"])
                self.assertIsNone(run.call_args.kwargs["env"])

    def test_path_audit_missing_and_absolute_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = path_audit.audit(root)
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(len(result["findings"]), len(path_audit.CRITICAL_FILES))
            for relative in path_audit.CRITICAL_FILES:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("from portable_paths import layout\n", encoding="utf-8")
            self.assertEqual(path_audit.audit(root)["status"], "PASS")
            (root / "ace.py").write_text("ROOT = r'C:\\machine\\ace'\n", encoding="utf-8")
            result = path_audit.audit(root)
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["findings"][0]["path"], "ace.py")

    def test_bootstrap_audit_failure_and_missing_gate(self):
        for audit_present in (True, False):
            with self.subTest(audit_present=audit_present), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                (root / ".git").mkdir()
                (root / "recovery").mkdir()
                (root / "ace_config.example.json").write_text('{"runtime": {}}', encoding="utf-8")
                if audit_present:
                    (root / "recovery/path_audit.py").touch()

                def fake_run(cmd, cwd, **kwargs):
                    return command_result(1 if any(Path(arg).name == "path_audit.py" for arg in cmd) else 0)

                with patch.object(bootstrap.sys, "argv", ["bootstrap", "--workspace-root", str(root), "--skip-tests"]), \
                        patch.object(bootstrap.shutil, "which", return_value="git"), \
                        patch.object(bootstrap, "run", side_effect=fake_run), \
                        contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(bootstrap.main(), 1)
                report = json.loads((root / "recovery/bootstrap_report.json").read_text(encoding="utf-8"))
                self.assertEqual(report["status"], "FAIL")
                gate = next(item for item in report["checks"] if item["name"] == "portable_path_audit")
                self.assertEqual(gate["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
