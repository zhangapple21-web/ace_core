"""Governed OpenCode CLI worker adapter for ACE.

This adapter is deliberately narrower than MinerPool: it invokes the existing
OpenCode CLI in a caller-provided workspace, records a bounded execution
receipt, and fails closed on unsafe workspace or model selection.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

OPENCODE_MODELS: Dict[str, str] = {
    "heavy_agent": "opencode/nemotron-3-ultra-free",
    "long_context": "opencode/fledge-alpha-free",
    "coding_reasoning": "opencode/mimo-v2.6-flash-free",
    "ultra_long_context": "opencode/longcat-2.5-preview-free",
    "fast_inspection": "opencode/nemotron-3.5-lightning-free",
    "lightweight": "opencode/ling-3.1-flash-free",
    "experimental": "opencode/space-bunny-free",
    "creative_candidate": "opencode/muse-spark-1.3-contributor-free",
    "legacy_fallback": "opencode/ling-3.0-flash-fin-free",
}

DEFAULT_MODEL_ORDER = [
    OPENCODE_MODELS["fast_inspection"],
    OPENCODE_MODELS["lightweight"],
    OPENCODE_MODELS["coding_reasoning"],
    OPENCODE_MODELS["long_context"],
    OPENCODE_MODELS["heavy_agent"],
]


class OpenCodeWorker:
    """Run one bounded ACE task through the installed OpenCode CLI."""

    def __init__(self, executable: Optional[str] = None, timeout_seconds: int = 900):
        self.executable = executable or os.environ.get(
            "OPENCODE_EXECUTABLE", r"C:\Users\Administrator\.local\bin\opencode.exe"
        )
        self.timeout_seconds = max(1, int(timeout_seconds))

    @staticmethod
    def _fingerprint(path: Path) -> str:
        digest = hashlib.sha256()
        if path.is_file():
            digest.update(path.read_bytes())
        else:
            for child in sorted(path.rglob("*")):
                if child.is_file() and ".git" not in child.parts:
                    digest.update(str(child.relative_to(path)).encode("utf-8"))
                    digest.update(child.read_bytes())
        return digest.hexdigest()

    @staticmethod
    def _validate_workspace(workspace: str) -> Path:
        path = Path(workspace).expanduser().resolve()
        if not path.exists() or not path.is_dir():
            raise ValueError("opencode_workspace_missing")
        if path == Path(path.anchor):
            raise ValueError("opencode_workspace_too_broad")
        return path

    def run(
        self,
        task: str,
        workspace: str,
        expected_result: str = "",
        verification_method: str = "",
        model_order: Optional[Iterable[str]] = None,
    ) -> Dict[str, Any]:
        path = self._validate_workspace(workspace)
        if not task.strip():
            raise ValueError("opencode_task_missing")
        if not Path(self.executable).exists():
            raise FileNotFoundError(self.executable)
        models = list(model_order or DEFAULT_MODEL_ORDER)
        if not models or any(model not in OPENCODE_MODELS.values() for model in models):
            raise ValueError("opencode_model_not_registered")
        before = self._fingerprint(path)
        attempts: List[Dict[str, Any]] = []
        for model in models:
            command = [self.executable, "run", "--model", model, "--format", "json", task]
            try:
                completed = subprocess.run(
                    command, cwd=str(path), capture_output=True, text=True,
                    encoding="utf-8", errors="replace", timeout=self.timeout_seconds,
                    check=False,
                )
                raw = (completed.stdout or "").strip()
                attempts.append({"model": model, "returncode": completed.returncode, "output_bytes": len(raw)})
                if completed.returncode == 0 and raw:
                    after = self._fingerprint(path)
                    return {
                        "success": True, "model": model, "workspace": str(path),
                        "expected_result": expected_result, "verification_method": verification_method,
                        "changed": before != after, "attempts": attempts, "raw_output": raw,
                    }
            except subprocess.TimeoutExpired:
                attempts.append({"model": model, "timeout": self.timeout_seconds})
        return {
            "success": False, "model": "", "workspace": str(path),
            "expected_result": expected_result, "verification_method": verification_method,
            "changed": before != self._fingerprint(path), "attempts": attempts,
            "error": "opencode_all_models_failed",
        }
