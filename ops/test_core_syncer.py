import subprocess
import tempfile
from pathlib import Path

from core.core_syncer import CoreSyncer


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=True)
    return completed.stdout.strip()


def _repo() -> Path:
    root = Path(tempfile.mkdtemp())
    _git(root, "init")
    _git(root, "config", "user.email", "ace-test@example.invalid")
    _git(root, "config", "user.name", "ACE Test")
    (root / "README.md").write_text("base\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-m", "initial")
    return root


def _public_syncer(root: Path, **kwargs) -> CoreSyncer:
    """Tests use synthetic public-only fixture content."""
    return CoreSyncer(str(root), data_class="PUBLIC", **kwargs)


def test_manifest_admits_only_motherplate_files_and_hashes_contents():
    root = _repo()
    (root / "core").mkdir()
    (root / "outputs").mkdir()
    (root / "core" / "new.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "outputs" / "runtime.log").write_text("private runtime\n", encoding="utf-8")

    syncer = _public_syncer(root)
    manifest = syncer.build_manifest()

    assert [item["path"] for item in manifest["files"]] == ["core/new.py"]
    assert manifest["files"][0]["sha256"]
    assert manifest["sha256"]
    assert manifest["excluded"] == [{"path": "outputs/", "status": "??", "reason": "OUTSIDE_MOTHERPLATE_ALLOWLIST"}]


def test_syncer_blocks_unclassified_external_content_before_remote_probe(monkeypatch):
    root = _repo()
    (root / "core").mkdir()
    (root / "core" / "private.py").write_text("PRIVATE = True\n", encoding="utf-8")
    syncer = CoreSyncer(str(root))
    monkeypatch.setattr(syncer, "_remote_head", lambda: (_ for _ in ()).throw(AssertionError("must not probe remote")))

    result = syncer.preflight(force=True)

    assert result["status"] == "BLOCKED"
    assert result["reason"] == "DATA_BOUNDARY_BLOCKED"
    assert result["changed_files"] == []
    assert result["excluded_files"] == [
        {"path": "core/", "status": "??", "reason": "DATA_BOUNDARY_BLOCKED"}
    ]
    assert result["data_boundary"]["allowed"] is False


def test_preflight_blocks_remote_divergence_without_staging_any_file(monkeypatch):
    root = _repo()
    (root / "core").mkdir()
    (root / "core" / "new.py").write_text("VALUE = 1\n", encoding="utf-8")
    syncer = _public_syncer(root)
    monkeypatch.setattr(syncer, "_remote_head", lambda: "0" * 40)

    result = syncer.preflight(force=True)

    assert result["status"] == "BLOCKED"
    assert result["reason"] == "REMOTE_HEAD_DIFFERS_FROM_LOCAL_HEAD"
    assert _git(root, "diff", "--cached", "--name-only") == ""


def test_preflight_blocks_existing_stage_before_manifest_can_be_added():
    root = _repo()
    (root / "core").mkdir()
    (root / "core" / "new.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git(root, "add", "core/new.py")

    result = _public_syncer(root).preflight(force=True)

    assert result["status"] == "BLOCKED"
    assert result["reason"] == "PREEXISTING_STAGED_CHANGES"


def test_manifest_preserves_leading_space_in_modified_porcelain_record():
    root = _repo()
    (root / "README.md").write_text("modified\n", encoding="utf-8")

    manifest = _public_syncer(root).build_manifest()

    assert [item["path"] for item in manifest["files"]] == ["README.md"]
    assert manifest["files"][0]["status"] == " M"


def test_manifest_excludes_secret_like_source_without_recording_value():
    root = _repo()
    (root / "core").mkdir()
    credential = "a" * 40
    source = root / "core" / "candidate.py"
    source.write_text(f'api_key = "{credential}"\n', encoding="utf-8")

    manifest = _public_syncer(root).build_manifest()

    assert manifest["files"] == []
    assert manifest["excluded"] == [
        {"path": "core/candidate.py", "status": "??", "reason": "SECRET_PATTERN_DETECTED"}
    ]
    assert credential not in str(manifest)


def test_manifest_excludes_bearer_and_cloud_key_shapes_without_echoing_them():
    root = _repo()
    (root / "core").mkdir()
    bearer = root / "core" / "bearer.py"
    aws = root / "core" / "cloud.py"
    bearer_value = "Bearer " + "b" * 36
    aws_value = "AKIA" + "A" * 16
    bearer.write_text(f'Authorization: "{bearer_value}"\n', encoding="utf-8")
    aws.write_text(f'aws_access_key = "{aws_value}"\n', encoding="utf-8")

    manifest = _public_syncer(root).build_manifest()

    assert manifest["files"] == []
    assert {item["path"] for item in manifest["excluded"]} == {
        "core/bearer.py",
        "core/cloud.py",
    }
    assert bearer_value not in str(manifest)
    assert aws_value not in str(manifest)


def test_explicit_sync_pack_defers_other_eligible_files(monkeypatch):
    root = _repo()
    (root / "core").mkdir()
    (root / "ops").mkdir()
    (root / "core" / "one.py").write_text("ONE = 1\n", encoding="utf-8")
    (root / "ops" / "two.py").write_text("TWO = 2\n", encoding="utf-8")

    syncer = _public_syncer(root)
    monkeypatch.setattr(syncer, "_remote_head", lambda: "0" * 40)
    result = syncer.preflight(force=True, paths=["core/one.py"])

    assert result["status"] == "BLOCKED"  # no remote is configured in the fixture
    assert result["reason"] == "REMOTE_HEAD_DIFFERS_FROM_LOCAL_HEAD"
    assert result["changed_files"] == ["core/one.py"]
    assert any(item["path"] == "ops/two.py" and item["reason"] == "DEFERRED_NOT_IN_EXPLICIT_SYNC_PACK" for item in result["excluded_files"])


def test_automatic_sync_refuses_large_unreviewed_source_backlog():
    root = _repo()
    (root / "core").mkdir()
    for number in range(3):
        (root / "core" / f"item_{number}.py").write_text(f"VALUE = {number}\n", encoding="utf-8")

    result = _public_syncer(root, max_automatic_files=2).preflight(force=True)

    assert result["status"] == "BLOCKED"
    assert result["reason"] == "EXPLICIT_SYNC_PACK_REQUIRED"
    assert result["staged_files"] == []


