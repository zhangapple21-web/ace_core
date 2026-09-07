import builtins
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


LEGACY_COMMANDS = [
    ["test"],
    ["lexicon", "list"],
    ["mem", "stats"],
    ["scan", str(ROOT)],
    ["scan-fragments", str(ROOT)],
]


def test_unknown_cli_command_fails_closed_without_loading_legacy_scheduler(monkeypatch, capsys):
    """No unknown command may fall through to the historical Scheduler."""
    import ace

    sys.modules.pop("core.scheduler", None)
    original_import = builtins.__import__

    def reject_scheduler(name, *args, **kwargs):
        if name == "core.scheduler":
            raise AssertionError("unknown commands must not load legacy Scheduler")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_scheduler)
    monkeypatch.setattr(ace.sys, "argv", ["ace.py", "unknown-command"])

    with pytest.raises(SystemExit) as exc_info:
        ace.main(ROOT)

    assert exc_info.value.code == 2
    assert capsys.readouterr().out == "未知命令：unknown-command。命令未执行。\n"
    assert "core.scheduler" not in sys.modules


@pytest.mark.parametrize("command", LEGACY_COMMANDS)
def test_legacy_cli_commands_fail_closed_without_loading_scheduler(monkeypatch, capsys, command):
    import ace

    sys.modules.pop("core.scheduler", None)
    original_import = builtins.__import__

    def reject_scheduler(name, *args, **kwargs):
        if name == "core.scheduler":
            raise AssertionError("legacy Scheduler must not be imported")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", reject_scheduler)
    monkeypatch.setattr(ace.sys, "argv", ["ace.py", *command])

    with pytest.raises(SystemExit) as exc_info:
        ace.main(ROOT)

    assert exc_info.value.code == 2
    assert capsys.readouterr().out == "旧 CLI 命令已弃用：请迁移到当前 ace daemon/runtime 接口。命令未执行。\n"
    assert "core.scheduler" not in sys.modules


def test_legacy_scheduler_constructor_is_fail_closed():
    """Importing the legacy lifecycle itself is fail-closed."""
    sys.modules.pop("core.scheduler", None)
    with pytest.raises(RuntimeError, match="legacy_runtime_deprecated"):
        __import__("core.scheduler")


def test_legacy_task_queue_import_is_fail_closed():
    """The historical queue cannot become a second writable authority."""
    sys.modules.pop("core.task_queue", None)

    with pytest.raises(RuntimeError, match="legacy_runtime_deprecated"):
        __import__("core.task_queue")


