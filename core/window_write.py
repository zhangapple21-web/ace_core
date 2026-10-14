"""The write chokepoint every window goes through.

A window that claims tasks and files at `ace.py start` still has a hundred other
places it can write - a sandbox record, a knowledge deposit, a receipt. Asking
permission at each one is how a registry ends up decorative, which is the exact
failure this whole layer is meant to undo.

So the lane question becomes the write itself: `window_write(path, content,
lane, ...)` is refused unless the owning lane holds the region. No window has to
remember to ask; the write is the asking.

Reuses, and invents nothing: ``MinerPool``'s data-boundary gate, this registry's
claim, the existing observation channel for a refused write. A refusal is a
value with a named reason, never a silent success.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Mapping

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from core.window_lane import LaneRegistry  # noqa: E402


class WindowRefused(RuntimeError):
    """A write refused by the lane registry. Carries its reason."""

    def __init__(self, reason: str, detail: Mapping[str, Any] | None = None):
        super().__init__(reason)
        self.reason = reason
        self.detail = dict(detail or {})


def window_write(root: str | Path, region: str, content: Any, *,
                 lane: str, registry: LaneRegistry | None = None,
                 observer: Any = None, actor: str = "",
                 allow_unclaimed: bool = False) -> dict[str, Any]:
    """Write `content` under `region` if `lane` may, or refuse and say why.

    ``allow_unclaimed`` is the escape hatch for an explicitly shared surface,
    and it is off by default: a window that can always write "somewhere else"
    makes the claim layer moot. Refusals go to the observation channel so a
    pattern of collisions becomes visible instead of being retried forever.
    """
    path = Path(root)
    registry = registry or LaneRegistry(path)
    target = str(region)
    answer = registry.may_write(lane, target)

    if not answer["allowed"]:
            reason = answer.get("reason") or "region not writable by this lane"
            detail = {
                "lane": lane, "region": target, "reason": reason,
                "owner": answer.get("owner"), "held_by": answer.get("held_by"),
            }
            if observer is not None:
                try:
                    observer.record(
                        description=(f"lane refused a write by {lane} to {target}: {reason}"),
                        system_state={"lane": lane, "region": target,
                                      "refused_by": "window_lane",
                                      "owner": answer.get("owner"),
                                      "held_by": answer.get("held_by")},
                        severity="medium", source="window_lane",
                        category="structural_gap", dedup_key=f"lane_refusal:{lane}:{target}",
                    )
                except Exception:
                    pass  # a missing observer must not turn a refusal into a write
            raise WindowRefused(reason, detail)

    if not allow_unclaimed and answer.get("owner") is None:
            # An unowned region is not a free-for-all. Registering every region
            # is the owner table's job; until it is registered, a window cannot
            # write there by default, because "I could not find an owner" is
            # exactly how a window justifies writing where it should not.
            reason = (f"region {target} is not owned or shared by any lane; "
                      f"{lane} may not write it without allow_unclaimed")
            if observer is not None:
                try:
                    observer.record(
                        description=(f"lane refused an unclaimed write by {lane} "
                                     f"to {target}"),
                        system_state={"lane": lane, "region": target,
                                      "refused_by": "window_lane",
                                      "unclaimed": True},
                        severity="medium", source="window_lane",
                        category="structural_gap",
                        dedup_key=f"lane_unclaimed:{lane}:{target}",
                    )
                except Exception:
                    pass
            raise WindowRefused(reason, {"lane": lane, "region": target,
                                         "unclaimed": True})

    # the write itself, atomic, with the lane recorded beside the content
    payload = _render(content)
    temporary = path / (str(target) + ".tmp")
    temporary.parent.mkdir(parents=True, exist_ok=True)
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(path / str(target))

    return {
        "status": "WRITTEN",
        "path": str(target),
        "lane": lane,
        "owner": answer.get("owner"),
        "actor": str(actor or ""),
    }


def _render(content: Any) -> str:
    """Content as text. Sandbox records are JSON; notes are plain text."""
    if isinstance(content, str):
        return content
    return json.dumps(content, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
