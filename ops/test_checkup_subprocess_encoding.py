"""The hourly patrol could not read the Chinese it was patrolling.

`ACE-Checkup-Hourly` runs `ops/run_checkup.py --quiet` every hour and had been
reporting failure. The cause was not the checks: `run_script` called
`subprocess.run(..., capture_output=True, text=True)` with no `encoding`, so
Python decoded the child's UTF-8 output with the host locale - GBK. Any Chinese
byte raised UnicodeDecodeError inside the reader thread, which killed the reader,
lost stdout, and made the task exit non-zero.

This is the recorded rule from NOTE_gbk_channel_false_alarm_20261004.md applied
somewhere else: judge corruption by raw bytes, not by console echo. Here the
bytes were fine and the decode was wrong - exactly the distinction the note warns
about. The first test drives the real `run_script` and asserts it can read a
child that speaks UTF-8; it fails on the old call and passes on this one.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import ops.run_checkup as run_checkup


def _write_chinese_child(ops_dir: Path, name: str) -> Path:
    script = ops_dir / name
    script.write_text(
        "import sys\n"
        "sys.stdout.write('巡检完成：状态 warning，任务 2099 个，磁盘 56.4GB\\n')\n"
        "sys.stdout.flush()\n",
        encoding="utf-8",
    )
    return script


def _child_env() -> None:
    """Note why the env is pinned, for the reader who wonders.

    A child launched from a GBK console inherits that code page, so the same
    script can write GBK under pytest and UTF-8 under a shell. PYTHONIOENCODING
    is pinned per test below so the assertion measures the parent's decoder -
    the thing under test - rather than the host's console settings.
    """


def test_run_script_reads_utf8_child_output(tmp_path, monkeypatch):
    """Drive the real function: it must not lose the child's Chinese."""
    _write_chinese_child(tmp_path, "noisy_child.py")
    monkeypatch.setattr(run_checkup, "OPS_DIR", tmp_path)
    monkeypatch.setenv("PYTHONIOENCODING", "utf-8")

    result = run_checkup.run_script("noisy_child.py")

    assert "脚本不存在" not in str(result.get("error", "")), result
    assert result["success"] is True, result
    assert "巡检完成" in result["stdout"], (
        f"the patrol could not read the text it was patrolling: {result}"
    )


def test_run_script_reports_child_failure_without_raising(tmp_path, monkeypatch):
    """A failing child is reported, not crashed on."""
    (tmp_path / "failing.py").write_text(
        "import sys\nsys.stderr.write('检查失败：数据准入无进展\\n')\nsys.exit(3)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(run_checkup, "OPS_DIR", tmp_path)
    monkeypatch.setenv("PYTHONIOENCODING", "utf-8")

    result = run_checkup.run_script("failing.py")

    assert result["success"] is False
    assert result["returncode"] == 3
    assert "检查失败" in result["stderr"], result


def test_run_script_source_declares_an_explicit_encoding():
    """Pin the missing argument itself: the bug was a call that did not say how."""
    source = Path(run_checkup.__file__).read_text(encoding="utf-8")
    start = source.index("subprocess.run(")
    call = source[start: start + 900]
    assert "text=True" in call, "sanity: the text-mode call is still there"
    assert "encoding=" in call, (
        "run_script must pass an explicit encoding to subprocess; without it the "
        "host locale (GBK here) decodes UTF-8 child output and raises"
    )
    assert "errors=" in call, "and must tolerate a malformed byte rather than abort the read"


if __name__ == "__main__":
    import pytest

    raise SystemExit(pytest.main([__file__, "-q"]))