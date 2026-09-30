"""Portable ACE configuration loading.

The checkout must remain usable after moving to another machine.  The
canonical ``ace_config.json`` therefore contains environment placeholders,
while an untracked ``ace_config.local.json`` may provide operator-specific
values.  Secrets are never read from Git or written by this module.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _expand(value: Any) -> Any:
    if isinstance(value, str):
        return os.path.expandvars(value)
    if isinstance(value, list):
        return [_expand(item) for item in value]
    if isinstance(value, dict):
        return {key: _expand(item) for key, item in value.items()}
    return value


def load_config(base_dir: Path) -> dict[str, Any]:
    """Load canonical config plus an optional local, untracked override.

    ``ACE_CONFIG_PATH`` can point at a private config outside the checkout.
    The local override is intentionally optional and is never created here.
    """

    base_dir = Path(base_dir).resolve()
    explicit = os.environ.get("ACE_CONFIG_PATH")
    canonical_path = Path(explicit).expanduser() if explicit else base_dir / "ace_config.json"
    config: dict[str, Any] = {}
    if canonical_path.is_file():
        config = json.loads(canonical_path.read_text(encoding="utf-8"))
    local_path = base_dir / "ace_config.local.json"
    if local_path.is_file() and local_path.resolve() != canonical_path.resolve():
        local = json.loads(local_path.read_text(encoding="utf-8"))
        if not isinstance(local, dict):
            raise ValueError("ace_config.local.json must contain a JSON object")
        config = _deep_merge(config, local)
    return _expand(config)

