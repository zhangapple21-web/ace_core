import hashlib
import json
from pathlib import Path


def test_user_reference_sources_are_hash_anchored():
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "08_GOVERNANCE/evolution_kernel_sources.v1.json").read_text(encoding="utf-8"))
    entry = next(item for item in manifest["local_sources"] if item["id"] == "user-r1-notes")
    for reference in entry["references"]:
        path = Path(reference["path"])
        assert path.is_file(), reference["path"]
        digest = hashlib.sha256(path.read_bytes()).hexdigest().upper()
        assert digest == reference["sha256"]
    assert entry["mapping_tests"]
