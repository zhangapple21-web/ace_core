"""Which free models exist right now, asked of the CLI that serves them.

The roster used to be a dict literal, and the free tier retires models on its own
schedule. Measured on 2026-10-19: of nine pinned ids, four no longer resolve -
fledge-alpha-free (the writing workhorse), muse-spark-1.3-contributor-free,
ling-3.1-flash-free, ling-3.0-flash-fin-free - while five models the CLI
currently serves were never in the map at all, including the two the owner named
as the replacement path (deepseek-v4.1-flash-free, glm-5.3-flash-free).

Worse, the dead ids passed validation. `resolve_cli_model` only checked that a
slug appeared in OPENCODE_MODELS, which is the tombstone itself, so a retired
model was declared routable and only failed at the call. A liveness check has to
come from outside the pinned data or it is just the same data checked twice.

This module is that outside source: it runs `opencode models`, keeps the free
ones, and caches the answer. It is the discovery half; the allowlist decision
still lives in the provider, because refusing unknown models before any
subprocess starts remains the correct behaviour. What changed is that the
allowlist now tracks the tier instead of a snapshot of it.

Design constraints, all of them learned from the incident:
  * a discovery failure must not empty the roster - the last good answer stands,
    because a flapping CLI must not take the free tier offline;
  * the cache is stamped so a reader can tell "I asked and this is what I was
    told" from "I could not ask and this is stale";
  * nothing here decides which model a role uses. That stays a governance call.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

# Where the CLI keeps its own catalogue, when it is there. Only used as a
# secondary source: the binary is authoritative, a cached file is not.
_CLI_EXECUTABLE_CANDIDATES = (
    r"C:\Users\Administrator\.local\bin\opencode.exe",
    "opencode",
)

# Free models rotate on a scale of days-to-weeks. A minute of staleness costs
# nothing; an hour could route a cycle to a model that retired overnight.
DEFAULT_TTL_SECONDS = 900

_LOCK = threading.Lock()
_CACHE: Dict[str, object] = {
    "checked_at": None,      # float epoch of the last successful probe
    "models": [],            # list of cli ids, e.g. "opencode/glm-5.3-flash-free"
    "source": None,          # "cli" | "file" | None
    "error": None,
}


def _run_cli(timeout: int = 30) -> Optional[List[str]]:
    """Ask the CLI what it can serve. None means the probe itself failed."""
    for exe in _CLI_EXECUTABLE_CANDIDATES:
        try:
            proc = subprocess.run(
                [exe, "models"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if proc.returncode != 0:
            continue
        ids = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
        if ids:
            return ids
    return None


def _free_of(ids: List[str]) -> List[str]:
    """Free models, identified by the id the CLI prints.

    The CLI marks them with a trailing "-free" segment. Matching the segment
    rather than a hand-kept list is the whole point: a new free model is picked
    up without a code change, and a retired one disappears without one.
    """
    return sorted({i for i in ids if "-free" in i.lower()})


def discover_free_models(force: bool = False) -> List[str]:
    """Current free model ids, from the CLI, cached.

    On a failed probe the previous answer is returned unchanged. Returning an
    empty list on failure would look like "the free tier is gone" and would stop
    every free route at once; that is the one failure mode worth paying a little
    extra code to avoid.
    """
    now = time.time()
    with _LOCK:
        checked = _CACHE["checked_at"]
        fresh = (
            not force
            and isinstance(checked, (int, float))
            and (now - checked) < DEFAULT_TTL_SECONDS
        )
        if fresh and _CACHE["models"]:
            return list(_CACHE["models"])  # type: ignore[arg-type]

        try:
            ids = _run_cli()
        except Exception:
            # The guard belongs at the call site, not only inside the probe.
            # _run_cli already swallows the failures it expects, but anything
            # else - a patch in a test, an unforeseen exception type - must not
            # take the free tier offline. The whole point of this module is that
            # a bad moment leaves the previous roster standing.
            _CACHE["error"] = "cli_probe_raised"
            return list(_CACHE["models"] or [])  # type: ignore[arg-type]
        if ids is None:
            _CACHE["error"] = "cli_probe_failed"
            return list(_CACHE["models"] or [])  # type: ignore[arg-type]

        free = _free_of(ids)
        if free:
            _CACHE["checked_at"] = now
            _CACHE["models"] = free
            _CACHE["source"] = "cli"
            _CACHE["error"] = None
            return list(free)

        # The CLI answered but offered nothing free. That is real information -
        # record it, so the roster reads empty rather than lying about age.
        _CACHE["checked_at"] = now
        _CACHE["models"] = []
        _CACHE["source"] = "cli"
        _CACHE["error"] = "no_free_models_offered"
        return []


def is_live(cli_model: str, force: bool = False) -> bool:
    """True when the CLI served this model within the cache window.

    Called on the routing path, so it must be cheap and must not raise. An
    unreachable CLI returns True for a model already in the cached roster, and
    False for one that is not - the cache is the authority between probes.
    """
    try:
        live = set(discover_free_models(force=force))
    except Exception:
        return True if not cli_model else False
    if not live:
        # Probe failed or tier genuinely empty. Distinguish by asking once more
        # is too expensive here; fall back to "do not newly admit".
        return False
    return cli_model in live


def cache_state() -> Dict[str, object]:
    """Provenance for whoever asks how old this answer is."""
    with _LOCK:
        checked = _CACHE["checked_at"]
        age = None if not isinstance(checked, (int, float)) else time.time() - checked
        return {
            "checked_at": checked,
            "age_seconds": None if age is None else round(age, 1),
            "model_count": len(_CACHE["models"] or []),  # type: ignore[arg-type]
            "models": list(_CACHE["models"] or []),  # type: ignore[arg-type]
            "source": _CACHE["source"],
            "error": _CACHE["error"],
            "ttl_seconds": DEFAULT_TTL_SECONDS,
        }


def reset_cache() -> None:
    with _LOCK:
        _CACHE["checked_at"] = None
        _CACHE["models"] = []
        _CACHE["source"] = None
        _CACHE["error"] = None


__all__ = [
    "discover_free_models",
    "is_live",
    "cache_state",
    "reset_cache",
    "DEFAULT_TTL_SECONDS",
]