"""Local OpenCode CLI provider for the miner pool.

The free HTTP relay (3001) is dead with no runnable artifact left on disk,
while the OpenCode CLI service on this same machine answers through its own
provider path. This provider lets miner traffic reach those free models
without touching the paid pools: it shells out to the installed CLI exactly
the way OpenCodeWorker already does, under the same governance gates every
other provider passes first (data boundary to MODEL_CONTEXT, governed
messages, constitution hierarchy).

It is deliberately narrow:

* chat-only. No streaming, no files, no tools beyond what the CLI session
  itself is allowed. The workspace is a fresh temp directory per call, so a
  run cannot read or modify production state through the working directory.
* Model allowlist, not open routing. Only miner model ids with a known
  opencode mapping are accepted; anything else is refused before any
  subprocess starts.
* Fail-closed everywhere a subprocess, timeout or parse can fail, with the
  same result shape the pool already handles.
"""

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.execution_contract import govern_model_messages
from core.mirror_constitution import validate_data_boundary

from . import BaseProvider

# Miner model id -> opencode --model id. Both sides are pinned by tests so a
# rename on either side fails loudly instead of silently routing elsewhere.
MODEL_MAP = {
    "mimo-v2.6-flash-free": "opencode/mimo-v2.6-flash-free",
    "fledge-alpha-free": "opencode/fledge-alpha-free",
    "longcat-2.5-preview-free": "opencode/longcat-2.5-preview-free",
    "nemotron-3-ultra-free": "opencode/nemotron-3-ultra-free",
    "nemotron-3.5-lightning-free": "opencode/nemotron-3.5-lightning-free",
    "muse-spark-1.3-contributor-free": "opencode/muse-spark-1.3-contributor-free",
    "ling-3.1-flash-free": "opencode/ling-3.1-flash-free",
    "ling-3.0-flash-fin-free": "opencode/ling-3.0-flash-fin-free",
}

_CLI_EXECUTABLE = r"C:\Users\Administrator\.local\bin\opencode.exe"


def resolve_cli_model(miner_model: str) -> Optional[str]:
    """Map a miner model id to an opencode --model id, or None to refuse."""
    if not isinstance(miner_model, str):
        return None
    slug = miner_model.split(":", 1)[-1].strip()
    if slug.startswith("opencode/"):
        candidate = slug
    else:
        candidate = MODEL_MAP.get(slug, "")
    try:
        from core.opencode_worker import OPENCODE_MODELS
    except ImportError:
        return None
    if candidate in set(OPENCODE_MODELS.values()):
        return candidate
    return None


class OpenCodeCliProvider(BaseProvider):
    """Miner pool provider that executes through the local OpenCode CLI."""

    provider_name = "opencode_cli"

    def list_models(self) -> List[Dict[str, Any]]:
        """The models this route can serve. Fixed set by design."""
        return [
            {"id": miner_id, "cli_model": cli_id}
            for miner_id, cli_id in sorted(MODEL_MAP.items())
        ]

    def __init__(self, api_key: str = "", base_url: str = "", provider_name: str = "", **kwargs):
        super().__init__(api_key, base_url, **kwargs)
        if provider_name:
            self.provider_name = provider_name
        self.timeout_seconds = int(kwargs.get("timeout_seconds", 300))

    def _flatten_messages(self, messages: List[Dict[str, str]]) -> str:
        lines = []
        for message in messages or []:
            if not isinstance(message, dict):
                continue
            role = str(message.get("role", "user")).strip() or "user"
            content = message.get("content", "")
            if isinstance(content, list):
                content = " ".join(
                    str(part.get("text", ""))
                    for part in content
                    if isinstance(part, dict)
                )
            lines.append(f"{role}: {content}")
        return "\n".join(lines).strip()

    @staticmethod
    def _extract_reply(raw_output: str) -> str:
        texts: List[str] = []
        for line in (raw_output or "").splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            part = event.get("part", {})
            if event.get("type") == "text" and isinstance(part, dict):
                text = part.get("text")
                if isinstance(text, str) and text.strip():
                    texts.append(text.strip())
        return "\n".join(texts).strip()

    def chat(
        self,
        messages: List[Dict[str, str]],
        model: str = "",
        temperature: float = 0.7,
        max_tokens: int = 1024,
        timeout: int = 60,
        extra_headers: Dict = None,
        **kwargs,
    ) -> Dict[str, Any]:
        start_time = time.time()
        result: Dict[str, Any] = {
            "success": False,
            "content": "",
            "model": model,
            "usage": {},
            "error": "",
            "latency_ms": 0,
            "provider": self.provider_name,
        }

        cli_model = resolve_cli_model(model)
        if not cli_model:
            result["error"] = f"opencode_cli_model_unmapped:{model}"
            return result

        boundary = validate_data_boundary(
            kwargs.pop("data_boundary", None),
            target="MODEL_CONTEXT",
            payload={"messages": messages},
        )
        if not boundary["valid"]:
            result["error"] = "DATA_BOUNDARY_BLOCKED:" + ",".join(boundary["errors"])
            result["governance"] = {
                "selected_route_state": "DATA_BOUNDARY_BLOCKED",
                "data_class": boundary.get("data_class"),
            }
            return result

        try:
            governed = govern_model_messages(
                messages,
                task_type=str(kwargs.pop("governance_task_type", "model_call")),
                task_id=str(kwargs.pop("governance_task_id", "")),
                role="opencode_cli_provider",
            )
        except RuntimeError as error:
            text = str(error)
            if text.startswith("ACE_CONSTITUTION_HIERARCHY_INVALID:"):
                result["error"] = "constitution hierarchy invalid; model call blocked"
                result["governance"] = {"selected_route_state": "CONSTITUTION_HIERARCHY_BLOCKED"}
            else:
                result["error"] = "constitution precedence unresolved; model call blocked"
                result["governance"] = {"selected_route_state": "CONSTITUTION_PRECEDENCE_BLOCKED"}
            return result

        caller_text = self._flatten_messages(messages)
        if not caller_text.replace("user:", "").replace("system:", "").replace(
            "assistant:", ""
        ).strip():
            # Checked on the caller's text before governance wraps it: the
            # governed envelope is always long, so checking after it would
            # never catch anything. A whitespace-only caller message is
            # refused here, not sent to a model that bills time answering
            # nothing.
            result["error"] = "opencode_empty_prompt"
            return result
        prompt = self._flatten_messages(governed)

        try:
            from core.opencode_worker import OpenCodeWorker
        except ImportError as error:
            result["error"] = f"opencode_worker_unavailable:{error}"
            return result

        budget = max(1, min(int(timeout or 60), self.timeout_seconds))
        try:
            workspace = Path(tempfile.mkdtemp(prefix="ace_opencode_cli_"))
            (workspace / "prompt.txt").write_text(prompt, encoding="utf-8")
            # Instruction staging stays off here on purpose. This route is
            # chat-only and already carries a governed system contract from
            # govern_model_messages(); adding ACE's ~20KB runtime manual to every
            # free-tier call would be a second ungoverned instruction surface,
            # most of it irrelevant to a question, and would push unclassified
            # workspace content into MODEL_CONTEXT past the data boundary that
            # validate_data_boundary() applies to messages only. Delivery-shaped
            # work is the case that wants instructions; that caller's decision,
            # not this one.
            worker = OpenCodeWorker(timeout_seconds=budget, instruction_mode="off")
            receipt = worker.run(
                task=prompt,
                workspace=str(workspace),
                expected_result=str(workspace / "prompt.txt"),
                verification_method="file_exists_nonempty",
                model_order=[cli_model],
            )
        except FileNotFoundError:
            result["error"] = "opencode_executable_missing"
            return result
        except ValueError as error:
            result["error"] = f"opencode_worker_refused:{error}"
            return result
        except Exception as error:
            result["error"] = f"opencode_worker_failed:{type(error).__name__}"
            return result

        reply = self._extract_reply(str(receipt.get("raw_output", "")))
        result["latency_ms"] = int((time.time() - start_time) * 1000)
        result["usage"] = {
            "via": "opencode_cli",
            "cli_model": cli_model,
            "attempts": len(receipt.get("attempts", [])),
        }
        if receipt.get("success") and reply:
            result["success"] = True
            result["content"] = reply[: max_tokens * 4] if max_tokens else reply
        else:
            result["error"] = receipt.get("error", "") or "opencode_empty_reply"
        return result


__all__ = ["MODEL_MAP", "OpenCodeCliProvider", "resolve_cli_model"]