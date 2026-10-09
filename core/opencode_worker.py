"""Governed OpenCode CLI worker adapter for ACE.

This worker is the only OpenCode invocation face ACE has: the miner-pool
provider and the daemon delivery stage both land here, so instruction policy
belongs to the worker rather than being re-decided by each caller.

Instruction staging (instruction_mode) is off by default. OpenCode V2
recognises AGENTS.md only, so a file in the call workspace is the one supported
way to give a run persistent guidance -- but that file is also a second,
ungoverned instruction source beside the governed system contract built by
govern_model_messages(), and ACE_OMX_ADAPTATION_DECISION_20260905.md records
auto-injecting project AGENTS.md as rejected because it widens the implicit
instruction surface. So a caller opts in per worker, and every receipt states
which way it went.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from core.instruction_boundary import evaluate_instruction_set

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

# "off": no instruction file is written, behaviour unchanged. "workspace": the
# authoritative file is copied into this call's workspace as AGENTS.md before
# the CLI starts, which is the only shape OpenCode V2 loads as instructions.
INSTRUCTION_MODES = ("off", "workspace")


class OpenCodeWorker:
    """Run one bounded ACE task through the installed OpenCode CLI."""

    def __init__(
        self,
        executable: Optional[str] = None,
        timeout_seconds: int = 900,
        standalone: Optional[bool] = None,
        instruction_mode: str = "off",
        instruction_source: Optional[str] = None,
        ace_root: Optional[str] = None,
    ):
        self.executable = executable or os.environ.get(
            "OPENCODE_EXECUTABLE", r"C:\Users\Administrator\.local\bin\opencode.exe"
        )
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.instruction_mode = str(instruction_mode or "off").strip().lower()
        if self.instruction_mode not in INSTRUCTION_MODES:
            raise ValueError("opencode_instruction_mode_unknown")
        source = str(instruction_source or "").strip()
        if self.instruction_mode == "off":
            # A source without a mode reads as "instructions were staged" in the
            # caller's head. Refuse it rather than silently dropping it.
            if source:
                raise ValueError("opencode_instruction_source_without_mode")
            self.instruction_source: Optional[Path] = None
        else:
            if not source:
                raise ValueError("opencode_instruction_source_required")
            self.instruction_source = Path(source).expanduser().resolve()
        self._version_cache: Optional[str] = None
        # Where the instruction classification records live. None resolves to
        # the checkout this module sits in; tests point it at a fixture root.
        self.ace_root = str(ace_root).strip() if ace_root else None
        # The interactive UI uses the background OpenCode service. Reuse it by
        # default so CLI workers see the same auth/model/quota context. Set
        # OPENCODE_STANDALONE=1 only when an isolated service is intentional.
        self.standalone = (
            os.environ.get("OPENCODE_STANDALONE", "").strip().lower() in {"1", "true", "yes"}
            if standalone is None else bool(standalone)
        )

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

    @staticmethod
    def models() -> Dict[str, str]:
        """The registry of routable models this worker can be asked for."""
        return dict(OPENCODE_MODELS)

    @staticmethod
    def _parse_result(raw: str) -> Optional[Dict[str, Any]]:
        texts: List[str] = []
        for line in raw.splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            part = event.get("part", {})
            if event.get("type") == "text" and isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str):
                    texts.append(text)
        for text in reversed(texts):
            try:
                value = json.loads(text.strip())
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                return value
        return None

    def _run_command(
        self, command: List[str], cwd: str, timeout: Optional[int] = None,
    ) -> subprocess.CompletedProcess:
        """Run the CLI, killing the whole process tree when time runs out.

        subprocess.run(timeout=...) terminates only the direct child. The CLI
        spawns helpers of its own, so a timeout used to strand those helpers
        as orphans long after their workspace was cleaned (14 such python
        orphans had accumulated). taskkill /T takes the tree; on POSIX the
        process group is signalled instead.
        """
        popen_kwargs: Dict[str, Any] = {}
        if os.name == "nt":
            popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            popen_kwargs["start_new_session"] = True
        process = subprocess.Popen(
            command, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace", **popen_kwargs,
        )
        budget = self.timeout_seconds if timeout is None else max(1, int(timeout))
        try:
            stdout, stderr = process.communicate(timeout=budget)
        except subprocess.TimeoutExpired:
            self._kill_tree(process)
            try:
                stdout, stderr = process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                stdout, stderr = "", ""
            raise subprocess.TimeoutExpired(command, budget, stdout, stderr)
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)

    @staticmethod
    def _kill_tree(process: "subprocess.Popen") -> None:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                capture_output=True, timeout=60, check=False,
            )
            return
        try:
            import signal

            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except (OSError, AttributeError):
            try:
                process.kill()
            except OSError:
                pass

    def _cli_version(self, workspace: Path) -> str:
        """Best-effort CLI version for the receipt.

        Diagnostic only, so it fails soft rather than refusing a call: a receipt
        must not hinge on a probe answering. It goes through _run_command so a
        launcher that ignores --version has its helpers killed instead of
        stranding them. Resolved once per worker.
        """
        if self._version_cache is not None:
            return self._version_cache
        version = "UNKNOWN"
        try:
            completed = self._run_command(
                [self.executable, "--version"], cwd=str(workspace), timeout=30
            )
            text = (completed.stdout or "").strip()
            if completed.returncode == 0 and text:
                version = text.splitlines()[0].strip()
        except (OSError, subprocess.SubprocessError):
            version = "UNKNOWN"
        self._version_cache = version
        return version

    @staticmethod
    def _project_root(workspace: Path) -> Optional[Path]:
        for candidate in (workspace, *workspace.parents):
            if (candidate / ".git").exists():
                return candidate
        return None

    @staticmethod
    def _instruction_sources(workspace: Path) -> List[Dict[str, Any]]:
        """The AGENTS.md files OpenCode would combine for this workspace.

        V2 loads the global file, then every AGENTS.md from the workspace
        directory toward the home directory, stopping at the project root when
        the workspace sits outside home. Enumerating that same set is the only
        way a receipt can state what guidance a run actually had -- including
        guidance nobody staged, and including a stray ancestor file that would
        otherwise join the prompt silently.
        """
        home = Path(os.path.expanduser("~"))
        root = OpenCodeWorker._project_root(workspace)
        under_home = workspace == home or home in workspace.parents
        candidates: List[Path] = []
        if under_home:
            for candidate in (workspace, *workspace.parents):
                candidates.append(candidate)
                if candidate == home:
                    break
        else:
            stop = root or Path(workspace.anchor)
            for candidate in (workspace, *workspace.parents):
                candidates.append(candidate)
                if candidate == stop:
                    break

        global_file = home / ".config" / "opencode" / "AGENTS.md"
        found: List[Dict[str, Any]] = []
        for path in [global_file, *[item / "AGENTS.md" for item in candidates]]:
            if not path.is_file():
                continue
            payload = path.read_bytes()
            found.append({
                "path": str(path),
                "origin": "global" if path == global_file else "workspace",
                "sha256": hashlib.sha256(payload).hexdigest(),
                "bytes": len(payload),
            })
        return found

    def _instruction_context(self, workspace: Path) -> Dict[str, Any]:
        """Record the instruction set this run really carries.

        Separate from staging on purpose: a workspace-mode run also has an
        effective set, and an off-mode run usually has one anyway when its cwd
        is a repository. Without this, "the model had no ACE instructions"
        and "the model had them but nobody wrote it down" look identical.
        """
        sources = self._instruction_sources(workspace)
        digest = hashlib.sha256()
        for entry in sources:
            digest.update(f"{entry['path']}:{entry['sha256']}\n".encode("utf-8"))
        return {
            "instruction_context_sources": sources,
            "instruction_context_count": len(sources),
            "instruction_context_sha256": digest.hexdigest(),
            "instruction_context_state": "present" if sources else "none",
        }

    def _stage_instruction(self, workspace: Path) -> Dict[str, Any]:
        """Copy the authoritative instruction file into this call's workspace.

        Staged before the pre-run fingerprint on purpose: this file is ours, so
        it must not be reported as work the model did. The hash covers the
        source bytes and the copy is read back, so the receipt proves the model
        was handed this exact text rather than whatever the directory happened
        to contain. Fails closed -- a workspace-mode run whose source is absent
        raises instead of quietly calling without guidance.
        """
        if self.instruction_mode == "off":
            return {"instruction_mode": "off", "instruction_staged": False}

        source = self.instruction_source
        if source is None or not source.is_file():
            raise ValueError("opencode_instruction_source_missing")
        payload = source.read_bytes()
        target = workspace / "AGENTS.md"
        if target.exists() and target.resolve() == source:
            # The workspace already *is* the source -- this is the delivery
            # stage, whose cwd is the production repository root. Copying here
            # would rewrite production instructions with themselves, so record
            # the reuse instead of touching the file.
            return {
                "instruction_mode": self.instruction_mode,
                "instruction_source": str(source),
                "instruction_sha256": hashlib.sha256(payload).hexdigest(),
                "instruction_bytes": len(payload),
                "instruction_staged": False,
                "instruction_reuse": "already_in_workspace",
                "opencode_version": self._cli_version(workspace),
            }
        target.write_bytes(payload)
        if target.read_bytes() != payload:
            raise ValueError("opencode_instruction_stage_incomplete")
        return {
            "instruction_mode": self.instruction_mode,
            "instruction_source": str(source),
            "instruction_sha256": hashlib.sha256(payload).hexdigest(),
            "instruction_bytes": len(payload),
            "instruction_staged": True,
            "instruction_target": str(target),
            "opencode_version": self._cli_version(workspace),
        }

    def run(
        self, task: str, workspace: str, expected_result: str = "",
        verification_method: str = "", model_order: Optional[Iterable[str]] = None,
    ) -> Dict[str, Any]:
        path = self._validate_workspace(workspace)
        if not task.strip():
            raise ValueError("opencode_task_missing")
        if not Path(self.executable).exists():
            raise FileNotFoundError(self.executable)
        if model_order is None:
            raise ValueError("opencode_model_required")
        models = list(model_order)
        if not models or any(model not in OPENCODE_MODELS.values() for model in models):
            raise ValueError("opencode_model_not_registered")
        instruction = self._stage_instruction(path)
        context = self._instruction_context(path)
        gate = evaluate_instruction_set(
            context["instruction_context_sources"], root=self.ace_root,
        )
        if not gate["instruction_gate_allowed"]:
            # Before any subprocess. The verdict travels in the receipt so the
            # refusal explains itself instead of looking like a model failure.
            return {
                "success": False,
                "model": "",
                "workspace": str(path),
                "expected_result": expected_result,
                "verification_method": verification_method,
                "changed": False,
                "attempts": [],
                "raw_output": "",
                "stderr_output": "",
                "error": "opencode_instruction_gate_blocked",
                **context,
                **instruction,
                **gate,
            }
        before = self._fingerprint(path)
        attempts: List[Dict[str, Any]] = []
        last_raw_output = ""
        last_stderr = ""
        for model in models:
            command = [self.executable, "run"]
            if self.standalone:
                command.append("--standalone")
            command.extend(["--model", model, "--format", "json", task])
            try:
                completed = self._run_command(command, cwd=str(path))
                raw = (completed.stdout or "").strip()
                stderr = (completed.stderr or "").strip()
                last_raw_output = raw
                last_stderr = stderr
                parsed_result = self._parse_result(raw)
                attempt = {
                    "model": model,
                    "returncode": completed.returncode,
                    "output_bytes": len(raw),
                    "stderr_bytes": len(stderr),
                    "raw_output": raw,
                    "stderr_output": stderr,
                    "parsed_result": parsed_result,
                }
                if completed.returncode != 0:
                    attempt["error"] = "opencode_nonzero_exit"
                attempts.append(attempt)
                if completed.returncode == 0 and raw:
                    after = self._fingerprint(path)
                    return {
                        "success": True,
                        "model": model,
                        "workspace": str(path),
                        "expected_result": expected_result,
                        "verification_method": verification_method,
                        "changed": before != after,
                        "attempts": attempts,
                        "raw_output": raw,
                        "stderr_output": stderr,
                        "parsed_result": parsed_result,
                        **context,
                        **instruction,
                        **gate,
                    }
            except subprocess.TimeoutExpired as timeout:
                attempts.append({"model": model, "timeout": self.timeout_seconds})
                last_raw_output = str(timeout.stdout or "")
                last_stderr = str(timeout.stderr or "")
        return {
            "success": False,
            "model": "",
            "workspace": str(path),
            "expected_result": expected_result,
            "verification_method": verification_method,
            "changed": before != self._fingerprint(path),
            "attempts": attempts,
            "raw_output": last_raw_output,
            "stderr_output": last_stderr,
            "error": "opencode_all_models_failed",
            **context,
            **instruction,
            **gate,
        }
