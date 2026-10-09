"""Canonical resolution for the sibling civilization repositories.

The curator, the syncer and the validation scripts must all agree on where
`mine-seed` lives. Hardcoding a Trae workspace path inside one script is how
a validation ends up quietly exercising nothing: the directory does not
exist, the run reports success-shaped output, and nobody notices.

One resolver, one answer, and a caller that refuses to continue when the
answer is empty or missing.
"""

import os
from pathlib import Path
from typing import Optional

# Environment override wins, so a relocated checkout needs no code edit.
ENV_MINE_SEED = "ACE_MINE_SEED_PATH"

# Ordered candidates. Only paths that actually exist are returned; a
# candidate that does not exist is skipped rather than invented.
CANDIDATES = (
    "C:/tmp/mine-seed",
    "C:/tmp/r1-archaeology",
)


def resolve_mine_seed(repo_root: Optional[Path] = None) -> Optional[Path]:
    """Return the real mine-seed working copy, or None when there is none."""
    override = os.environ.get(ENV_MINE_SEED, "").strip()
    if override:
        candidate = Path(override)
        if candidate.is_dir():
            return candidate.resolve()
        # An override that points nowhere is a configuration error, not a
        # reason to silently fall back somewhere else.
        raise FileNotFoundError(f"{ENV_MINE_SEED} points at a missing directory: {candidate}")

    root = Path(repo_root) if repo_root else Path(__file__).resolve().parent.parent
    for relative in CANDIDATES:
        candidate = Path(relative)
        if not candidate.is_absolute():
            candidate = root / relative
        if candidate.is_dir():
            return candidate.resolve()

    sibling = root.parent / "mine-seed"
    if sibling.is_dir():
        return sibling.resolve()
    return None


__all__ = ["CANDIDATES", "ENV_MINE_SEED", "resolve_mine_seed"]