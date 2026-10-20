#!/usr/bin/env python3
"""Fail-closed, byte-preserving state export and restore. No daemon is started."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import stat
import urllib.request
from collections import Counter
from pathlib import Path, PurePosixPath

STATE_URL = "https://github.com/zhangapple21-web/ace-civilization-backup.git"
ROOTS = ("task_pool", "09_KNOWLEDGE", "06_RUNTIME/ace")
MANIFEST = "STATE_MANIFEST.json"
MAX_BYTES = 100 * 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


def is_link(path):
    return path.is_symlink() or (path.exists() and bool(
        getattr(path.lstat(), "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)))


def verify_private(url):
    match = re.fullmatch(r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+?)(?:\.git)?", url)
    if not match:
        raise RuntimeError("State URL must be a credential-free GitHub HTTPS repository")
    owner, repo = match.groups()
    try:
        proc = subprocess.run(["git", "-c", "credential.interactive=false", "credential", "fill"],
                              input=f"protocol=https\nhost=github.com\npath={owner}/{repo}.git\n\n",
                              text=True, capture_output=True, timeout=30)
        credentials = dict(line.split("=", 1) for line in proc.stdout.splitlines() if "=" in line)
        token = credentials.get("password")
        if proc.returncode or not token:
            raise RuntimeError("Credential unavailable")
        request = urllib.request.Request(f"https://api.github.com/repos/{owner}/{repo}", headers={
            "Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
            "User-Agent": "ACE-state-recovery", "X-GitHub-Api-Version": "2022-11-28"})
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.load(response)
    except Exception:
        raise RuntimeError("Private repository verification blocked: credential or GitHub API unavailable") from None
    if result.get("private") is not True or result.get("full_name", "").lower() != f"{owner}/{repo}".lower():
        raise RuntimeError("Private repository verification blocked: private=true not established")
    return {"private": True, "permissions": result.get("permissions", {})}


def exclusion(relative):
    parts = relative.lower().split("/")
    name = parts[-1]
    if any(p == ".env" or p.startswith(".env.") for p in parts):
        return "credential configuration"
    if any(p in {"backups", "backup", "cache", "__pycache__", ".git", "runtime_claims"}
           or any(term in p for term in ("validation", "_test", "_probe", "_readiness", "_routing_audit")) for p in parts):
        return "backup/cache/test/validation/claim"
    if (name.endswith((".lock", ".pid", ".tmp", ".py", ".pyc", ".bak"))
            or any(term in name for term in ("heartbeat", "daemon", "claim", "stale"))):
        return "source or transient process state"
    if relative.startswith("06_RUNTIME/ace/") and not (relative.startswith("06_RUNTIME/ace/data/")
            or relative == "06_RUNTIME/ace/08_GOVERNANCE/governor/knowledge_governor_records.jsonl"):
        return "outside persistent runtime whitelist"
    if (relative.startswith("06_RUNTIME/ace/data/public_sentiment_evidence/")
            and Path(name).suffix.lower() == ".html"):
        return "raw downloaded external HTML evidence: hash only, not uploaded; raw evidence not restorable from snapshot"
    if Path(name).suffix.lower() not in {".json", ".jsonl", ".txt", ".md", ".html", ".csv"}:
        return "not approved text state format"
    return None


PLACEHOLDERS = {"", "none", "null", "false", "true", "unknown", "redacted", "placeholder", "test", "dummy", "example", "***", "[redacted]"}
SECRET_KEY = re.compile(r"^(?:api[_-]?key|access[_-]?token|refresh[_-]?token|token|password|passwd|secret|cookie|authorization)$", re.I)
SECRET_VALUE = re.compile(r"(?:\b(?:gh[pousr]_[A-Za-z0-9_]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,})\b|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)")
ASSIGNMENT = re.compile(r'''(?i)["']?(api[_-]?key|access[_-]?token|refresh[_-]?token|password|passwd|cookie|authorization)["']?\s*[:=]\s*["']?([^\s"',;}]+)''')


def actual_secret(value):
    if not isinstance(value, str):
        return False
    value = value.strip()
    return (value.lower() not in PLACEHOLDERS and len(value) >= 8
            and not any(term in value.lower() for term in ("your_", "your-", "example", "placeholder", "redacted", "os.environ", "getenv", "${", "<", "*")))


def scan(data, relative):
    try:
        text = data.decode("utf-8-sig")
    except UnicodeError:
        raise RuntimeError(f"Non-UTF8 state blocked: {relative}") from None
    def walk(value):
        if isinstance(value, dict):
            for key, item in value.items():
                if SECRET_KEY.fullmatch(key) and actual_secret(item):
                    raise RuntimeError(f"Potential credential blocked: {relative}")
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
    if SECRET_VALUE.search(text) or any(actual_secret(m.group(2)) for m in ASSIGNMENT.finditer(text)):
        raise RuntimeError(f"Potential credential blocked: {relative}")
    if relative.endswith(".json"):
        walk(json.loads(text))
    elif relative.endswith(".jsonl"):
        for line in text.splitlines():
            if line.strip():
                walk(json.loads(line))


def inventory(source):
    selected, excluded = {}, []
    for root in ROOTS:
        base = source / root
        if not base.is_dir() or is_link(base):
            raise RuntimeError(f"Missing or unsafe state root: {root}")
        for directory, dirs, files in os.walk(base, followlinks=False):
            for name in dirs + files:
                path = Path(directory) / name
                if is_link(path):
                    raise RuntimeError("Symlink/junction in source state")
            for name in files:
                path = Path(directory) / name
                relative = path.relative_to(source).as_posix()
                before = path.stat()
                if before.st_size > MAX_BYTES:
                    raise RuntimeError(f"Blob exceeds 100 MiB blocked: {relative}")
                reason = exclusion(relative)
                if reason == "credential configuration":
                    excluded.append({"path": relative, "reason": reason, "sha256": None})
                    continue
                data = path.read_bytes()
                if len(data) > MAX_BYTES:
                    raise RuntimeError(f"Blob exceeds 100 MiB blocked: {relative}")
                after = path.stat()
                if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                    raise RuntimeError(f"Source changed during read: {relative}")
                entry = {"path": relative, "sha256": digest(data), "bytes": len(data)}
                if reason:
                    excluded.append({**entry, "reason": reason, "restorable": False})
                else:
                    scan(data, relative)
                    selected[relative] = (entry, data)
    return selected, excluded


def counts(files):
    result = dict(Counter(next(root for root in ROOTS if item["path"].startswith(root + "/")) for item in files))
    result["evidence_files"] = sum("evidence" in item["path"].lower() for item in files)
    result["files"] = len(files)
    result["bytes"] = sum(item["bytes"] for item in files)
    return result


def export(source, destination, private):
    if private.get("private") is not True:
        raise RuntimeError("Private repository verification required before export")
    source, destination = source.resolve(), destination.absolute()
    if any(is_link(parent) for parent in (destination, *destination.parents)):
        raise RuntimeError("Unsafe snapshot destination")
    if destination == source or source in destination.parents:
        raise RuntimeError("Snapshot destination cannot be inside production")
    if destination.exists() and any(p.name != ".git" for p in destination.iterdir()):
        raise RuntimeError("Snapshot destination must be empty or an empty Git checkout")
    selected, excluded = inventory(source)
    again, excluded_again = inventory(source)
    if ({k: v[0] for k, v in selected.items()} != {k: v[0] for k, v in again.items()}
            or sorted(excluded, key=lambda x: x["path"]) != sorted(excluded_again, key=lambda x: x["path"])):
        raise RuntimeError("Selected state changed between inventories; snapshot blocked")
    manifest = {"schema": "ace.state_snapshot.v1", "private_repository": private,
                "consistency": "Two matching inventories; not a cross-file transaction",
                "roots": list(ROOTS), "files": [selected[k][0] for k in sorted(selected)],
                "excluded": sorted(excluded, key=lambda x: x["path"])}
    manifest["counts"] = counts(manifest["files"])
    destination.mkdir(parents=True, exist_ok=True)
    for relative, (_, data) in selected.items():
        target = safe_path(destination, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    raw = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
    (destination / MANIFEST).write_bytes(raw)
    (destination / (MANIFEST + ".sha256")).write_text(digest(raw) + "\n", encoding="ascii")
    return {"counts": manifest["counts"], "excluded_files": len(excluded), "manifest_sha256": digest(raw)}


def safe_path(root, relative):
    pure = PurePosixPath(relative)
    if (not relative or "\\" in relative or ":" in relative or pure.is_absolute()
            or any(part in {"..", ".", ""} for part in relative.split("/"))):
        raise RuntimeError("Unsafe snapshot path")
    path = root / relative
    for parent in (root, *path.parents, path):
        if is_link(parent):
            raise RuntimeError("Symlink/junction snapshot path")
    if root.resolve() not in path.resolve().parents:
        raise RuntimeError("Snapshot path escapes root")
    return path


def restore(snapshot, workspace):
    snapshot, workspace = snapshot.absolute(), workspace.absolute()
    raw = safe_path(snapshot, MANIFEST).read_bytes()
    expected = safe_path(snapshot, MANIFEST + ".sha256").read_text().strip()
    if digest(raw) != expected:
        raise RuntimeError("Manifest hash mismatch")
    manifest = json.loads(raw)
    if manifest.get("schema") != "ace.state_snapshot.v1" or manifest.get("roots") != list(ROOTS):
        raise RuntimeError("Unsupported state manifest")
    status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=normal"], cwd=workspace,
                            text=True, capture_output=True)
    if status.returncode or status.stdout.strip():
        raise RuntimeError("State restore requires a fresh clean code checkout")
    prepared, seen = [], set()
    for entry in manifest["files"]:
        relative = entry["path"]
        if relative.casefold() in seen or not any(relative.startswith(root + "/") for root in ROOTS) or exclusion(relative):
            raise RuntimeError("Duplicate or non-whitelisted manifest path")
        seen.add(relative.casefold())
        src, dst = safe_path(snapshot, relative), safe_path(workspace, relative)
        if entry["bytes"] > MAX_BYTES or src.stat().st_size > MAX_BYTES:
            raise RuntimeError(f"Blob exceeds 100 MiB blocked: {relative}")
        data = src.read_bytes()
        if len(data) > MAX_BYTES:
            raise RuntimeError(f"Blob exceeds 100 MiB blocked: {relative}")
        if len(data) != entry["bytes"] or digest(data) != entry["sha256"]:
            raise RuntimeError(f"State hash mismatch: {relative}")
        scan(data, relative)
        if dst.exists():
            tracked = subprocess.run(["git", "ls-files", "--error-unmatch", "--", relative], cwd=workspace,
                                     capture_output=True)
            if tracked.returncode or not dst.is_file() or dst.read_bytes() != data:
                raise RuntimeError(f"Existing data conflict: {relative}")
        else:
            prepared.append((dst, data))
    if counts(manifest["files"]) != manifest.get("counts"):
        raise RuntimeError("Manifest counts mismatch")
    for dst, data in prepared:
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)
    return {"counts": manifest["counts"], "manifest_sha256": expected, "restored_files": len(prepared)}


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    private = sub.add_parser("verify-private")
    private.add_argument("--state-url", default=STATE_URL)
    exp = sub.add_parser("export")
    exp.add_argument("--source", type=Path, required=True)
    exp.add_argument("--destination", type=Path, required=True)
    exp.add_argument("--state-url", default=STATE_URL)
    res = sub.add_parser("restore-local")
    res.add_argument("--snapshot", type=Path, required=True)
    res.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "restore-local":
            result = restore(args.snapshot, args.workspace)
        else:
            evidence = verify_private(args.state_url)
            result = evidence if args.command == "verify-private" else export(args.source, args.destination, evidence)
        print(json.dumps({"status": "PASS", **result}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "BLOCKED", "error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
