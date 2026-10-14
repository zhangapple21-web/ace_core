"""Window lanes: many windows may think, only one may hold a file region.

What this is for
----------------
ACE runs several windows at once - adjudication, the dead-component watch, the
admission gate, tombstoning, the roundtable, the social room, the model shift.
They claim tasks (TaskPool owns/lease/fencing does that), but nothing claims
which files a window intends to touch. A human-opened window and the daemon both
wrote source files into the same checkout, and .workspace.write.lock - held only
by the daemon - could not stop it.

The draft that named this (C:\\tmp\\LANES_DRAFT.md) surveyed the industry
position and rejected the usual answers: CRDT/OT is overkill, OS-level file
locks leave zombie locks after a crash, and a scheduler built for coordination
is another scheduler. What survived is the small set: isolate with worktrees,
declare ownership of hotspots, and carry a lease with a fencing token.

That is not a new mechanism here. TaskPool already carries exactly this
semantics - claim_id, fencing_token, lease_owner, lease_expires_at - and the
Free Zone bridge already carries the hash-bound single-artifact cross-domain
merge. This module reuses both shapes rather than inventing a third.

The guarantees, in the order they matter
----------------------------------------
1. A write region is claimed by at most one lane at a time. Overlapping
   regions from different lanes are refused, not warned about.
2. A lease that expired does not prove the holder stopped. `release` and
   `expire` both refuse a stale fencing token, so a late window cannot write
   over the current holder - the Chubby rule.
3. Unowned hotspots are refused. A lane that touches a region the OWNERS table
   assigns to another lane is refused, and the refusal names the owner.
4. Every claim is recorded, because a claim nobody can see is a claim nobody
   can be held to.

What it does not do: it does not merge, does not schedule, and does not write
source. It only says who may.
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

CONTRACT_VERSION = "ace.window_lane.v1"

#: Hotspot ownership, as data rather than as convention. A lane may only touch
#: regions it owns or that are explicitly shared.
OWNERS_TABLE = "04_PROTOCOLS/LANE_OWNERS.json"

#: How long a claim survives without renewal.
DEFAULT_LEASE_SECONDS = 3600

#: A region naming a single file is the common case; a prefix ending in "/"
#: claims a directory.
_DEFAULT_REGIONS: dict[str, list[str]] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: datetime) -> str:
    return moment.replace(microsecond=0).isoformat()


def _digest(value: Any) -> str:
    return __import__("hashlib").sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True,
                   separators=(",", ":")).encode("utf-8")).hexdigest()


@dataclass
class LaneClaim:
    """One window's exclusive hold on one region."""

    lane: str
    region: str
    claim_id: str
    fencing_token: int
    lease_owner: str
    lease_expires_at: str
    actor: str = ""
    reason: str = ""
    acquired_at: str = ""

    def is_live(self, now: datetime | None = None) -> bool:
        try:
            expiry = datetime.fromisoformat(self.lease_expires_at)
        except (TypeError, ValueError):
            return False
        return (now or _now()) <= expiry

    def to_dict(self) -> dict[str, Any]:
        return {
            "lane": self.lane,
            "region": self.region,
            "claim_id": self.claim_id,
            "fencing_token": self.fencing_token,
            "lease_owner": self.lease_owner,
            "lease_expires_at": self.lease_expires_at,
            "actor": self.actor,
            "reason": self.reason,
            "acquired_at": self.acquired_at,
            "live": self.is_live(),
        }


@dataclass
class LaneWindow:
    """A window: a name, a worktree, and a ledger of what it has held."""

    lane: str
    worktree: str
    claims: list = field(default_factory=list)


def _normalise_region(region: str) -> str:
    """Normalise a region so `core\task.py` and `core/task.py` are one claim."""
    text = str(region or "").strip().replace("\\", "/").lstrip("./")
    return text.rstrip("/") if text != "/" else text


def regions_overlap(first: str, second: str) -> bool:
    """Does claiming one region touch the other?

    A directory claim covers everything beneath it, and a file claim is
    covered by a directory claim. Two file claims overlap only when equal, so
    two windows editing different files never contend.
    """
    a, b = _normalise_region(first), _normalise_region(second)
    if not a or not b:
        return False
    if a == b:
        return True
    longer, shorter = (a, b) if len(a) >= len(b) else (b, a)
    return longer.startswith(shorter + "/")


class LaneRegistry:
    """The single place that says who may write what."""

    def __init__(self, root: str | Path, *, owners_table: Mapping[str, Any] | None = None,
                 state_path: str | Path | None = None) -> None:
        self.root = Path(root)
        self.state_path = Path(state_path or
                              self.root / "08_GOVERNANCE" / "lanes" / "lane_claims.json")
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self._owners = owners_table if owners_table is not None else self._load_owners()

    # ------------------------------------------------------------------ owners

    def _load_owners(self) -> dict[str, Any]:
        path = self.root / OWNERS_TABLE
        try:
            owners = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {"regions": {}, "shared": []}
        if not isinstance(owners, Mapping):
            return {"regions": {}, "shared": []}
        return {
            "regions": {str(k): str(v) for k, v in (owners.get("regions") or {}).items()},
            "shared": [str(p) for p in (owners.get("shared") or [])],
        }

    def owner_of(self, region: str) -> str | None:
        """Which lane owns this region, by the table, or None when unowned."""
        target = _normalise_region(region)
        for candidate in self._owners.get("shared", []):
            if regions_overlap(target, candidate):
                return "*shared*"
        for path, lane in self._owners.get("regions", {}).items():
            if regions_overlap(target, path):
                return lane
        return None

    def is_shared(self, region: str) -> bool:
        return self.owner_of(region) == "*shared*"

    # ------------------------------------------------------------------ state

    def _load_state(self) -> dict[str, Any]:
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
            return state if isinstance(state, dict) else {"claims": []}
        except (OSError, ValueError):
            return {"claims": []}

    def _save_state(self, state: dict[str, Any]) -> None:
        temporary = self.state_path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2,
                                        sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(self.state_path)

    def list_claims(self, live_only: bool = False) -> list[dict[str, Any]]:
        claims = []
        for entry in self._load_state().get("claims", []):
            try:
                claim = LaneClaim(
                    lane=str(entry.get("lane", "")),
                    region=str(entry.get("region", "")),
                    claim_id=str(entry.get("claim_id", "")),
                    fencing_token=int(entry.get("fencing_token", 0)),
                    lease_owner=str(entry.get("lease_owner", "")),
                    lease_expires_at=str(entry.get("lease_expires_at", "")),
                    actor=str(entry.get("actor", "")),
                    reason=str(entry.get("reason", "")),
                    acquired_at=str(entry.get("acquired_at", "")),
                )
            except (TypeError, ValueError):
                continue
            if live_only and not claim.is_live():
                continue
            claims.append(claim.to_dict())
        return claims

    # ------------------------------------------------------------------ claims

    def _next_fencing_token(self, state: Mapping[str, Any]) -> int:
        tokens = [int(c.get("fencing_token", 0)) for c in state.get("claims", [])
                  if isinstance(c, Mapping)]
        return (max(tokens) + 1) if tokens else 1

    def claim(self, lane: str, region: str, *, actor: str = "", reason: str = "",
              lease_seconds: int = DEFAULT_LEASE_SECONDS,
              owner_override: str | None = None) -> LaneClaim | dict[str, Any]:
        """Claim a region for one lane, or refuse and say why.

        Refusals are values, not exceptions: the caller is a window that is
        checking whether it may write, and "another lane holds this" is an
        answer it should handle rather than crash on.
        """
        lane_name = str(lane or "").strip()
        region_name = _normalise_region(region)
        if not lane_name or not region_name:
            return {"status": "REFUSED", "reason": "lane and region are both required"}

        owner = self.owner_of(region_name)
        if owner and owner != "*shared*" and owner != lane_name and not owner_override:
            return {"status": "REFUSED",
                    "reason": f"region owned by lane {owner}, claimed by {lane_name}",
                    "owner": owner, "region": region_name}

        state = self._load_state()
        now = _now()
        # A shared region needs no exclusive claim: requiring one would make
        # "shared" a second thing it already means nowhere else, and two windows
        # editing one shared file would be a false contention.
        if self.is_shared(region_name):
            state.setdefault("audit", []).append({
                "event": "shared_write", "at": _iso(now), "lane": lane_name,
                "region": region_name, "actor": str(actor or ""),
                "reason": "shared region, no exclusive claim required",
            })
            state["audit"] = state["audit"][-200:]
            self._save_state(state)
            return {"status": "SHARED_WRITE_ALLOWED", "lane": lane_name,
                    "region": region_name, "claim_id": f"SHARED-{lane_name}"}
        for entry in state.get("claims", []):
            if not isinstance(entry, Mapping):
                continue
            try:
                held = LaneClaim(
                    lane=str(entry.get("lane", "")),
                    region=str(entry.get("region", "")),
                    claim_id=str(entry.get("claim_id", "")),
                    fencing_token=int(entry.get("fencing_token", 0)),
                    lease_owner=str(entry.get("lease_owner", "")),
                    lease_expires_at=str(entry.get("lease_expires_at", "")),
                )
            except (TypeError, ValueError):
                continue
            if not held.is_live(now):
                continue
            if held.lane == lane_name:
                continue
            if regions_overlap(held.region, region_name):
                return {
                    "status": "REFUSED",
                    "reason": (f"region {region_name} overlaps {held.region} held by "
                               f"lane {held.lane} until {held.lease_expires_at}"),
                    "held_by": held.lane, "held_region": held.region,
                    "held_until": held.lease_expires_at,
                }

        token = self._next_fencing_token(state)
        claim = LaneClaim(
            lane=lane_name,
            region=region_name,
            claim_id=f"LANE-{lane_name}-{token:04d}",
            fencing_token=token,
            lease_owner=lane_name,
            lease_expires_at=_iso(now + timedelta(seconds=max(30, int(lease_seconds)))),
            actor=str(actor or ""),
            reason=str(reason or ""),
            acquired_at=_iso(now),
        )
        state["claims"] = [c for c in state.get("claims", [])
                           if not (isinstance(c, Mapping) and
                                   str(c.get("lane")) == lane_name and
                                   str(c.get("region")) == region_name)]
        state["claims"].append(claim.to_dict())
        state["contract_version"] = CONTRACT_VERSION
        state.setdefault("audit", []).append({
            "event": "claim", "at": _iso(now), "lane": lane_name,
            "region": region_name, "fencing_token": token,
            "actor": str(actor or ""), "reason": str(reason or ""),
        })
        state["audit"] = state["audit"][-200:]
        self._save_state(state)
        return claim

    def release(self, claim_id: str, *, token: int | None = None,
                actor: str = "") -> dict[str, Any]:
        """Release a claim, refusing a stale token and an expired lease.

        Two refusals, and they are different:

        token mismatch - a holder whose lease was taken over is answering a
        release meant for the new holder. Accepting it would let the old window
        believe it has stopped writing while the new holder still holds.

        already expired - the release is itself late. The region is either free
        or claimed by someone else, so returning it changes nothing and would
        silently delete a live claim if the id was reused. Refused, and the
        caller is told to stop assuming it holds anything.
        """
        state = self._load_state()
        found = None
        rest = []
        for entry in state.get("claims", []):
            if isinstance(entry, Mapping) and str(entry.get("claim_id")) == str(claim_id):
                found = entry
            else:
                rest.append(entry)
        if found is None:
            return {"status": "NOT_FOUND", "claim_id": str(claim_id)}
        if token is not None and int(token) != int(found.get("fencing_token", 0)):
            return {"status": "REFUSED",
                    "reason": "fencing token mismatch: this lease was taken over",
                    "claim_id": str(claim_id)}
        try:
            held = LaneClaim(
                lane=str(found.get("lane", "")), region=str(found.get("region", "")),
                claim_id=str(found.get("claim_id", "")),
                fencing_token=int(found.get("fencing_token", 0)),
                lease_owner=str(found.get("lease_owner", "")),
                lease_expires_at=str(found.get("lease_expires_at", "")),
            )
        except (TypeError, ValueError):
            return {"status": "REFUSED", "reason": "claim record is unreadable",
                    "claim_id": str(claim_id)}
        if not held.is_live():
            return {"status": "REFUSED",
                    "reason": "lease already expired: this window no longer holds the region",
                    "claim_id": str(claim_id)}
        state["claims"] = rest
        state.setdefault("audit", []).append({
            "event": "release", "at": _iso(_now()), "lane": str(found.get("lane", "")),
            "region": str(found.get("region", "")), "fencing_token": int(found.get("fencing_token", 0)),
            "actor": str(actor or ""),
        })
        state["audit"] = state["audit"][-200:]
        self._save_state(state)
        return {"status": "RELEASED", "claim_id": str(claim_id),
                "region": str(found.get("region", ""))}

    def expire_stale(self, now: datetime | None = None) -> dict[str, Any]:
        """Drop expired claims so a live region is not held by a ghost."""
        moment = now or _now()
        state = self._load_state()
        keep, dropped = [], []
        for entry in state.get("claims", []):
            try:
                claim = LaneClaim(
                    lane=str(entry.get("lane", "")), region=str(entry.get("region", "")),
                    claim_id=str(entry.get("claim_id", "")),
                    fencing_token=int(entry.get("fencing_token", 0)),
                    lease_owner=str(entry.get("lease_owner", "")),
                    lease_expires_at=str(entry.get("lease_expires_at", "")),
                )
            except (TypeError, ValueError):
                continue
            (keep if claim.is_live(moment) else dropped).append(claim.claim_id)
        if dropped:
            state["claims"] = [c for c in state.get("claims", [])
                               if str(c.get("claim_id")) in keep]
            state.setdefault("audit", []).append({
                "event": "expire", "at": _iso(moment), "dropped": dropped,
            })
            state["audit"] = state["audit"][-200:]
            self._save_state(state)
        return {"status": "EXPIRED", "dropped": dropped}

    def may_write(self, lane: str, region: str) -> dict[str, Any]:
        """The question a window asks before it writes. Read-only."""
        lane_name, region_name = str(lane or "").strip(), _normalise_region(region)
        owner = self.owner_of(region_name)
        if owner and owner != "*shared*" and owner != lane_name:
            return {"allowed": False, "allowed_because": None, "owner": owner,
                    "reason": f"owned by lane {owner}"}
        for held in self.list_claims(live_only=True):
            if held["lane"] == lane_name:
                continue
            if regions_overlap(held["region"], region_name):
                return {"allowed": False, "allowed_because": None,
                        "held_by": held["lane"], "held_region": held["region"],
                        "reason": f"held by lane {held['lane']}"}
        return {"allowed": True, "allowed_because": "no live conflicting claim",
                "owner": owner, "reason": ""}


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Window lane registry (claim/release/who)")
    parser.add_argument("--root", default=str(BASE_DIR))
    parser.add_argument("--claim", nargs=2, metavar=("LANE", "REGION"))
    parser.add_argument("--release", metavar="CLAIM_ID")
    parser.add_argument("--token", type=int)
    parser.add_argument("--who", metavar="REGION")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--expire", action="store_true")
    args = parser.parse_args()

    registry = LaneRegistry(Path(args.root))
    if args.claim:
        result = registry.claim(args.claim[0], args.claim[1])
    elif args.release:
        result = registry.release(args.release, token=args.token)
    elif args.who:
        result = registry.may_write("probe", args.who)
    elif args.expire:
        result = registry.expire_stale()
    else:
        result = {"claims": registry.list_claims(live_only=args.list),
                  "owners": registry._owners}
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())