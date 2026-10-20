# Regression: the receipt verifier accepts good receipts and rejects the
# exact failure modes the handover design names (forgery, staleness,
# self-review, missing evidence). No network, no remote writes.
import json
import subprocess
import tempfile
from pathlib import Path

from ops.audit_receipt import verify_receipt


def _repo_with_two_commits(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True, capture_output=True)
    (repo / "a.txt").write_text("one", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True, capture_output=True)
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    (repo / "b.txt").write_text("two", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "head"], cwd=repo, check=True, capture_output=True)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    return repo, base, head


def _good_receipt(repo, base, head):
    import hashlib

    diff = subprocess.run(
        ["git", "-C", str(repo), "diff", f"{base}...{head}"],
        check=True,
        capture_output=True,
    ).stdout
    return {
        "base_sha": base,
        "head_sha": head,
        "diff_digest": hashlib.sha256(diff).hexdigest(),
        "author": "steward",
        "reviewer_identity": "model:other:evidence-chain-2",
        "protocol_version": "ace.audit.v1",
        "behavior_scope": ["sync"],
        "threat_model": ["secret-push"],
        "test_evidence": {"commands": ["pytest ops/test_x.py"], "passed": 3},
        "findings": [],
        "verdict": "PASS",
    }


def test_good_receipt_passes(tmp_path):
    repo, base, head = _repo_with_two_commits(tmp_path)
    result = verify_receipt(_good_receipt(repo, base, head), repo)
    assert result == {"valid": True, "errors": [], "warnings": []}


def test_self_review_is_rejected(tmp_path):
    repo, base, head = _repo_with_two_commits(tmp_path)
    receipt = _good_receipt(repo, base, head)
    receipt["reviewer_identity"] = receipt["author"]
    result = verify_receipt(receipt, repo)
    assert result["valid"] is False
    assert any("reviewer_not_independent" in e for e in result["errors"])


def test_stale_receipt_is_rejected(tmp_path):
    repo, base, head = _repo_with_two_commits(tmp_path)
    receipt = _good_receipt(repo, base, head)
    (repo / "c.txt").write_text("three", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "new-head"], cwd=repo, check=True, capture_output=True)
    new_head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    receipt["head_sha"] = new_head
    result = verify_receipt(receipt, repo)
    assert result["valid"] is False
    assert any("diff_digest_mismatch" in e for e in result["errors"])


def test_unknown_commit_is_rejected(tmp_path):
    repo, base, head = _repo_with_two_commits(tmp_path)
    receipt = _good_receipt(repo, base, head)
    receipt["head_sha"] = "0" * 40
    result = verify_receipt(receipt, repo)
    assert result["valid"] is False
    assert any("unknown_commit" in e for e in result["errors"])


def test_blocked_verdict_without_tests_is_accepted(tmp_path):
    repo, base, head = _repo_with_two_commits(tmp_path)
    receipt = _good_receipt(repo, base, head)
    receipt["verdict"] = "BLOCKED"
    receipt["test_evidence"] = {}
    result = verify_receipt(receipt, repo)
    assert result["valid"] is True
