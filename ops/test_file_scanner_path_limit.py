"""A scanner that dies on one bad path also stops finding the good ones.

`FileScanner` runs every daemon cycle over `C:\\tmp`, which contains a bun
`node_modules` tree with paths past Windows' MAX_PATH.  `Path.rglob` raises on
the first such path, so the whole scan aborted and `daemon_state.json` collected
the same `file_scanner` error every cycle while real fragments went unseen.
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.file_scanner import MAX_PATH, FileScanner  # noqa: E402
from core.fragment_index import FragmentIndex  # noqa: E402
from core.task import TaskPool  # noqa: E402


def _scanner(root: Path, scan_root: Path) -> FileScanner:
    # Keep the fragment index under a sibling ace_core/ so the scan root is not
    # itself inside the ACE tree (which the scanner excludes by design).
    ace_root = root / "ace_core"
    (ace_root / "02_FRAGMENT_INDEX").mkdir(parents=True, exist_ok=True)
    return FileScanner(
        TaskPool(str(ace_root / "task_pool")),
        FragmentIndex(str(ace_root / "02_FRAGMENT_INDEX")),
        [scan_root],
        max_depth=6,
    )


def test_overlong_directory_does_not_abort_the_scan():
    """The regression: one over-long subtree must not hide the good files.

    The fixture is built under a short root so the over-long path can actually be
    created; pytest's own tmp_path is already deep enough that the mkdir fails.
    """
    import os
    import shutil
    import tempfile

    base = Path(tempfile.mkdtemp(dir="C:/tmp", prefix="fs_"))
    try:
        scan_root = base / "s"
        scan_root.mkdir()
        (scan_root / "good.json").write_text('{"ok": true}', encoding="utf-8")

        # Walk past MAX_PATH using the extended-length prefix, which is how such
        # trees exist on disk in the first place.
        long_name = "d" * 90
        deep = scan_root
        for _ in range(4):
            deep = deep / long_name
            extended = "\\\\?\\" + str(deep)
            try:
                os.mkdir(extended)
            except FileExistsError:
                pass
        extended_file = "\\\\?\\" + str(deep / "deep.md")
        with open(extended_file, "w", encoding="utf-8") as handle:
            handle.write("deep")

        assert len(str(deep / "deep.md")) > MAX_PATH, "fixture is not over-long"

        scanner = _scanner(base, scan_root)
        result = scanner._scan_new_fragments()

        paths = [p.name for p in result["new"]]
        assert "good.json" in paths, f"good file lost behind the bad path: {result}"
        assert result["skipped"], "an unreadable subtree must be reported, not raised"
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_scan_and_create_reports_unreadable_instead_of_raising(tmp_path):
    scan_root = tmp_path / "scan"
    scan_root.mkdir()
    (scan_root / "note.md").write_text("hello", encoding="utf-8")

    scanner = _scanner(tmp_path, scan_root)
    result = scanner.scan_and_create(max_new=5)

    assert result["new_files"] == 1
    assert result["unreadable"] == 0
    assert "unreadable_examples" not in result


def test_max_path_is_below_the_windows_limit():
    # 260 is the classic limit; leave headroom so the check triggers first.
    assert 0 < MAX_PATH < 260


def test_walk_survives_a_directory_it_cannot_list(tmp_path, monkeypatch):
    scan_root = tmp_path / "scan"
    scan_root.mkdir()
    (scan_root / "a.md").write_text("a", encoding="utf-8")
    bad = scan_root / "bad"
    bad.mkdir()

    scanner = _scanner(tmp_path, scan_root)
    skipped = []
    real_scandir = __import__("os").scandir

    def fake_scandir(path, *args, **kwargs):
        if str(path).endswith("bad"):
            raise PermissionError("denied")
        return real_scandir(path, *args, **kwargs)

    monkeypatch.setattr("core.file_scanner.os.scandir", fake_scandir)
    walked = list(scanner._walk(scan_root, skipped))

    assert any(p.name == "a.md" for p in walked)
    assert skipped and "PermissionError" in skipped[0]