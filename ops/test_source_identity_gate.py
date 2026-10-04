"""Content identity is the only identity: title is not a key.

Covers the two enforcement points of the source_fingerprint item:
  1. file_scanner._task_exists_for  (scanner-side creation gate)
  2. task_admission.duplicate_task  (admission-side dedupe)
"""
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.file_scanner import FileScanner
from core.fragment_index import FragmentIndex
from core.task import TaskPool
from core.task_admission import duplicate_task


def _admission(source, fingerprint=None):
    admission = {
        "source_type": "archaeology",
        "source_ref": str(source),
        "why_now": "material changed",
        "evidence": [{"source": str(source), "risk": "low"}],
        "expected_result": "read it",
        "verification_method": "re-read source",
        "risk": "read-only",
        "estimated_scope": "one file",
    }
    if fingerprint:
        admission["source_fingerprint"] = fingerprint
    return admission


def _scanner(pool, root):
    return FileScanner(
        task_pool=pool,
        fragment_index=FragmentIndex(str(root / "fragment_index")),
        scan_roots=[],
    )


def test_title_match_alone_never_blocks_creation():
    """A legacy record with the file name in its title is not the same file."""
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        pool = TaskPool(str(root / "pool"))
        fragment = root / "kernel_notes.md"
        fragment.write_text("# kernel\n", encoding="utf-8")
        pool.create_task(
            title=f"fragment archaeology: {fragment.name}",
            creator="observer",
            admission=_admission("legacy-ref"),
        )
        assert not _scanner(pool, root)._task_exists_for(fragment)


def test_same_path_different_content_is_not_a_duplicate():
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        pool = TaskPool(str(root / "pool"))
        fragment = root / "state.json"
        fragment.write_text('{"a": 1}', encoding="utf-8")
        scanner = _scanner(pool, root)
        first = scanner._create_archaeology_task(fragment)
        fingerprint = first.outputs["source_fingerprint"]
        assert scanner._task_exists_for(fragment), "identical content must block"

        fragment.write_text('{"a": 2}', encoding="utf-8")
        assert not scanner._task_exists_for(fragment), (
            "changed content is new work, not a duplicate"
        )
        assert fingerprint.startswith("sha256:")
        assert fingerprint != scanner._content_fingerprint(fragment)


def test_legacy_fingerprint_key_still_blocks_creation():
    """Older records spell the fingerprint 'fingerprint'; both are content ids."""
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        pool = TaskPool(str(root / "pool"))
        fragment = root / "notes.md"
        fragment.write_text("# notes\n", encoding="utf-8")
        scanner = _scanner(pool, root)
        fingerprint = scanner._content_fingerprint(fragment)
        pool.create_task(
            title="legacy archaeology",
            creator="observer",
            admission=_admission(fragment),
            outputs={"source_file": str(fragment.resolve()),
                     "fingerprint": fingerprint},
        )
        assert scanner._task_exists_for(fragment)


def test_path_only_record_does_not_block_creation():
    """Recording the path without content identity proves nothing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        pool = TaskPool(str(root / "pool"))
        fragment = root / "notes.md"
        fragment.write_text("# notes\n", encoding="utf-8")
        pool.create_task(
            title="archaeology",
            creator="observer",
            admission=_admission(fragment),
            outputs={"source_file": str(fragment.resolve())},
        )
        assert not _scanner(pool, root)._task_exists_for(fragment)


def test_admission_without_fingerprint_cannot_prove_sameness():
    task = SimpleNamespace(
        outputs={"admission": _admission(r"C:\tmp\x\state.json", "sha256:old")},
        status="pending",
    )
    same_content_missing_id = duplicate_task(
        [task],
        _admission(r"C:\tmp\x\state.json", "sha256:old"),
    )
    assert same_content_missing_id is task, "identical fingerprints dedupe"

    changed_content = duplicate_task(
        [task], _admission(r"C:\tmp\x\state.json", "sha256:new")
    )
    assert changed_content is None, "different content must not dedupe"

    unidentified = duplicate_task([task], _admission(r"C:\tmp\x\state.json"))
    assert unidentified is not None, (
        "an admission with no fingerprint still matches a recorded one"
    )
    unidentified_existing = SimpleNamespace(
        outputs={"admission": _admission(r"C:\tmp\x\state.json")}, status="pending"
    )
    assert duplicate_task(
        [unidentified_existing], _admission(r"C:\tmp\x\state.json")
    ) is unidentified_existing, "legacy pair keeps path+semantics dedupe"


def test_local_archaeologist_admission_carries_content_identity():
    """The producer that dedupes on admission must hand it a content id."""
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        pool = TaskPool(str(root / "pool"))
        material = root / "material.md"
        material.write_text("# material\n", encoding="utf-8")
        fingerprint = FileScanner._content_fingerprint(material)

        from core.local_archaeologist import LocalArchaeologist

        archaeologist = LocalArchaeologist(base_dir=root, lexicon=None,
                                        memory_index=None, task_pool=pool)
        task = archaeologist._create_absorption_task(
            {
                "path": str(material),
                "ext": ".md",
                "priority": 5,
                "source_class": "local_material",
                "fingerprint": fingerprint,
                "intake_policy": {"decision": "research", "risk": "low",
                                  "source_priority": 1},
            },
            {"keys": [], "signals": []},
        )
        assert task is not None
        assert task.outputs["admission"]["source_fingerprint"] == fingerprint
        assert task.outputs["source_fingerprint"] == fingerprint
        assert _scanner(pool, root)._task_exists_for(material), (
            "an archaeologist task must be visible to the scanner's own gate"
        )
