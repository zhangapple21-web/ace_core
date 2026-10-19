#!/usr/bin/env python3
"""Which free models the CLI serves right now, and the moment that roster changes.

The free tier rotates on someone else's schedule. On 2026-10-19 four of the nine
ids the runtime had pinned were gone, and five models the CLI was serving had
never been named at all - including the two replacement writing models. The
resolution half of that is being fixed beside this file: roles hold candidate
chains and the CLI is asked which candidate is live. This file is the other half,
the one the owner named directly - *when a worker rotates the system does not
know*. Adapting silently is still not knowing: nothing on disk said that
fledge-alpha-free had retired, or when, or that the roster a running daemon
imported is not the roster a fresh process would read.

So this is not a watch and it detects no failure. It is a receipt, refreshed by
the same hourly tick that already runs as SYSTEM, and it answers four questions
from one file:

  what is live    the free ids the CLI serves, asked of the CLI by
                  free_model_discovery (reused, not reimplemented) with the
                  probe's own provenance: source, error, age, ttl.
  what each role  every role's call-time pick and its retired candidates, from
  would pick      role_status(), which until now had no consumer at all.
  when it moved   `roster_changed_at` is the write time of the first receipt that
                  observed the current roster, carried forward while the roster
                  holds. A rotation becomes a dated fact instead of a surprise.
                  `comparison_state` is the field to read first, because a null
                  `changed` has four causes, named in `compared_to`: no previous
                  receipt ("absent"), a previous receipt that could not be parsed
                  ("unreadable"), this run's probe failed ("skipped"), or the
                  previous run's probe failed - whose list is *unknown*, and unknown
                  is not empty. Reading any of those as "first run" is how a
                  rotation disappears without a trace.
  what a new      the module-level table a *fresh* process would import. A
  process reads   long-running runtime holds its import-time copy; that is the
                  one live question this receipt cannot see into, so it says so
                  in `unproven` instead of implying the table is shared.
  and every run   `opencode_roster_receipt_attempts.jsonl`, one appended line per
                  run. The receipt is a snapshot that the next run overwrites, and
                  two identities run it - the hourly tick as SYSTEM and whoever runs
                  it by hand - so without an append-only record the answer to "can
                  the identity the schedule uses reach the CLI" is erased by the
                  next successful probe. That is a measured need, not a worry: on
                  2026-10-19 the failed SYSTEM run's empty list became the next
                  run's baseline and produced a change observation for a rotation
                  that never happened.

When the roster changes, one observation is recorded through the normal channel
so the change enters the system's own memory rather than only this file. The
category is `environment_change`, which the contract already registers as
unrouted: this adds evidence, not a new admission boundary and not a new rule.

Deliberately not done
---------------------
A failed probe is recorded (`quality`, `status: PROBE_FAILED`) and does **not**
exit non-zero. The tick turns a non-zero entry into a task failure, and a
standing failure whose clearing path has not been verified in this environment is
how a real alarm turns into an ignored one. The exit code therefore reports only
whether this receipt was produced; whether the probe itself was seen is a fact
inside the file, and raising it to an alarm waits for measured SYSTEM-side
evidence instead of an assumption about it.

Usage:
    py -3 ops/opencode_roster_receipt.py                  # write the receipt
    py -3 ops/opencode_roster_receipt.py --json           # write it and print it
    py -3 ops/opencode_roster_receipt.py --print-only     # print without writing
    py -3 ops/opencode_roster_receipt.py --root <dir>
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

ROOT_DEFAULT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DEFAULT))

RECEIPT_RELPATH = Path("06_RUNTIME") / "ace" / "data" / "memory" / "opencode_roster_receipt.json"
ATTEMPTS_RELPATH = (Path("06_RUNTIME") / "ace" / "data" / "memory"
                    / "opencode_roster_receipt_attempts.jsonl")
OBSERVATIONS_RELPATH = Path("06_RUNTIME") / "ace" / "data" / "observations"

_OBSERVE = object()

# Status vocabulary, kept small on purpose: OK is a fresh reading of the roster,
# DEGRADED means it was read and something is missing - a role has no live
# candidate, or the tier served nothing at all - and PROBE_FAILED means the
# roster could not be read this time and the reported list is the cached one.
STATUS_FRESH = "OK"
STATUS_DEGRADED = "DEGRADED"
STATUS_PROBE_FAILED = "PROBE_FAILED"


# --------------------------------------------------------------------------- #
# readings
# --------------------------------------------------------------------------- #

def read_roster() -> Dict[str, Any]:
    """Ask the discovery module what the CLI serves. Never raises."""
    try:
        from core.miner_pool.providers import free_model_discovery as discovery
    except Exception as exc:  # noqa: BLE001 - a receipt reports, it does not fail the tick
        return {"available": False, "module_error": type(exc).__name__,
                "live": [], "cache": {}}
    try:
        live = list(discovery.discover_free_models(force=True))
        cache = dict(discovery.cache_state())
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "module_error": type(exc).__name__,
                "live": [], "cache": {}}
    return {"available": True, "module_error": None, "live": sorted(live), "cache": cache}


def read_roles() -> Dict[str, Any]:
    """Every role's call-time pick and retired candidates. Never raises."""
    try:
        from core.opencode_worker import (  # type: ignore[attr-defined]
            OPENCODE_MODELS,
            OPENCODE_MODEL_CANDIDATES,
            role_status,
        )
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "module_error": type(exc).__name__, "roles": {},
                "flat_table": {}, "candidate_table": {}}
    try:
        return {
            "available": True,
            "module_error": None,
            "roles": dict(role_status()),
            "flat_table": dict(OPENCODE_MODELS),
            "candidate_table": {k: list(v) for k, v in OPENCODE_MODEL_CANDIDATES.items()},
        }
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "module_error": type(exc).__name__, "roles": {},
                "flat_table": {}, "candidate_table": {}}


def _quality_of(roster: Dict[str, Any]) -> str:
    """fresh | empty_tier | failed, read from the probe's own provenance.

    `no_free_models_offered` is a successful answer that says the tier is empty,
    not a failed probe: the distinction matters because one is a roster of zero
    and the other is a roster of unknown.
    """
    if not roster.get("available"):
        return "failed"
    cache = roster.get("cache") or {}
    error = cache.get("error")
    if error is None:
        return "fresh"
    if error == "no_free_models_offered":
        return "empty_tier"
    return "failed"


def _read_previous(path: Path) -> Dict[str, Any]:
    """The previous receipt, or a *named* reason there is none to compare against.

    Returns {"state": "absent"|"ok"|"unreadable", "receipt": dict, "reason": str}.

    Two things here are load-bearing. A file that exists but cannot be parsed must
    not read as "first receipt": that resets the comparison silently and the next
    rotation would be reported as a beginning instead of a change. And utf-8-sig,
    because a receipt written by a tool that emits a BOM is still a receipt - the
    counterexample run that found this wrote exactly such a file.
    """
    if not path.is_file():
        return {"state": "absent", "receipt": {}, "reason": "no previous receipt on disk"}
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        return {"state": "unreadable", "receipt": {},
                "reason": f"{type(exc).__name__}: {exc}"}
    if not isinstance(value, dict):
        return {"state": "unreadable", "receipt": {},
                "reason": f"previous receipt is {type(value).__name__}, not an object"}
    return {"state": "ok", "receipt": value, "reason": "previous receipt read"}


def _role_selection(roles: Dict[str, Any]) -> Dict[str, Optional[str]]:
    out: Dict[str, Optional[str]] = {}
    for role, info in (roles.get("roles") or {}).items():
        if isinstance(info, dict):
            out[role] = info.get("selected")
    return out


def _sha12(*parts: str) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8"))
    return digest.hexdigest()[:12]


# --------------------------------------------------------------------------- #
# the receipt
# --------------------------------------------------------------------------- #

def build_receipt(
    root: Path,
    *,
    roster: Any = _OBSERVE,
    roles: Any = _OBSERVE,
    previous: Any = _OBSERVE,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    root = Path(root).resolve()
    receipt_path = root / RECEIPT_RELPATH
    observed_at = datetime.now() if now is None else datetime.fromtimestamp(now)
    written_at = observed_at.isoformat()

    if roster is _OBSERVE:
        roster = read_roster()
    if roles is _OBSERVE:
        roles = read_roles()
    if previous is _OBSERVE:
        loaded = _read_previous(receipt_path)
    else:
        loaded = {"state": "ok" if previous else "absent", "receipt": previous or {},
                  "reason": "injected for comparison"}
    previous = loaded["receipt"]
    previous_state = loaded["state"]
    previous_reason = loaded["reason"]

    live = sorted(set(roster.get("live") or []))
    quality = _quality_of(roster)

    prev_quality = previous.get("quality") if previous else None
    prev_live = set(previous.get("roster", {}).get("live") or []) if previous else None
    prev_origin = (previous.get("roster") or {}).get("origin") if previous else None
    # A list is trustworthy when a probe produced it, or when a failed run carried a
    # trustworthy list forward and labelled it. `quality: failed` alone cannot decide:
    # on a fresh process the discovery cache is empty, so a failed probe returns [].
    prev_list_trusted = (
        prev_quality in ("fresh", "empty_tier")
        or (prev_quality == "failed"
            and prev_origin == "carried_forward_after_failed_probe"))

    # A failed probe in a fresh process returns [] - the discovery cache lives in
    # the process, not on disk - so a failed receipt's empty list means "unknown",
    # not "empty". Reported verbatim it both reads as an empty tier and, worse,
    # becomes the next successful probe's baseline: measured 2026-10-19 10:34,
    # where that produced a change observation for a rotation that never happened.
    # Carry the last trusted answer forward instead, labelled, so the baseline
    # survives the failed window - even several in a row - and the next real
    # rotation is still dated.
    roster_origin = "probe"
    if quality == "failed" and prev_list_trusted:
        live = sorted(prev_live or [])
        roster_origin = "carried_forward_after_failed_probe"
    live_set = set(live)

    role_rows = roles.get("roles") or {}
    selection = _role_selection(roles)
    starved = sorted(role for role, chosen in selection.items() if not chosen)

    # Candidates the static table still names but the CLI no longer serves. The
    # table is the part a human maintains; this is where that maintenance shows up
    # as a fact instead of as a 404 at call time.
    candidates = {c for cands in (roles.get("candidate_table") or {}).values() for c in cands}
    retired_candidates = sorted(c for c in candidates if c not in live_set)
    live_but_unnamed = sorted(live_set - candidates)

    prev_selection = (previous.get("roles", {}).get("selection") or {}) if previous else {}
    carried_changed_at = previous.get("change", {}).get("roster_changed_at") if previous else None
    carried_first_seen = previous.get("change", {}).get("roster_first_seen_at") if previous else None

    appeared: List[str] = []
    retired: List[str] = []
    role_moved: Dict[str, Dict[str, Any]] = {}

    if quality == "failed":
        # No comparison is possible: the list in hand is the module's cached copy,
        # so reporting a rotation here would be inventing one. Say unknown.
        changed: Optional[bool] = None
        roster_changed_at = carried_changed_at
        roster_first_seen_at = carried_first_seen
        comparison = "skipped: probe failed, list is the previous cached answer"
    elif prev_live is not None and prev_list_trusted:
        appeared = sorted(live_set - prev_live)
        retired = sorted(prev_live - live_set)
        for role in sorted(set(selection) | set(prev_selection)):
            was, now_choice = prev_selection.get(role), selection.get(role)
            if was != now_choice:
                role_moved[role] = {"was": was, "now": now_choice}
        changed = bool(appeared or retired or role_moved)
        roster_changed_at = written_at if changed else carried_changed_at
        roster_first_seen_at = written_at if changed else (carried_first_seen or written_at)
        comparison = (f"previous receipt written {previous.get('written_at')} "
                      f"(quality {prev_quality}, origin {prev_origin})")
    elif prev_live is not None:
        # A list is present but is not a baseline: the previous run's probe failed in
        # a process whose cache was empty, so its [] means "unknown", and comparing
        # against it invented a nine-model rotation on 2026-10-19 10:34. Claim no
        # change and say which of the two it is, instead of silently trusting it.
        reason = ("its probe failed, so its list is unknown rather than empty"
                  if prev_quality == "failed"
                  else f"its list came from an unrecognised shape (quality {prev_quality!r})")
        changed = None
        roster_changed_at = carried_changed_at
        roster_first_seen_at = carried_first_seen
        comparison = (f"no comparison: the previous receipt's list cannot be used as "
                      f"a baseline: {reason}")
    elif previous_state == "absent":
        changed = None
        roster_changed_at = None
        roster_first_seen_at = written_at
        comparison = "first receipt: no previous receipt on disk to compare against"
    else:
        # A previous receipt exists and could not be used. Reading that as "first
        # receipt" would reset the comparison silently - the next rotation would be
        # reported as a beginning - and reading it as "no change" would be a lie.
        # Claim no change, and name why there is nothing to compare against.
        changed = None
        roster_changed_at = carried_changed_at
        roster_first_seen_at = carried_first_seen
        comparison = f"no comparison: previous receipt unusable ({previous_reason})"

    # An empty tier is not OK even when no role table was read: zero live models
    # means zero capacity for every role, which is the fact this status exists for.
    degraded = bool(starved) or quality == "empty_tier"
    status = STATUS_PROBE_FAILED if quality == "failed" else (
        STATUS_DEGRADED if degraded else STATUS_FRESH)

    return {
        "schema": "ace.opencode_roster_receipt.v1",
        "status": status,
        "written_at": written_at,
        "written_by": {
            "pid": os.getpid(),
            "identity": _whoami(),
            "session": os.environ.get("SESSIONNAME") or None,
            "python": sys.executable,
            "script": "ops/opencode_roster_receipt.py",
        },
        "quality": quality,
        "source": {
            "asked": "core.miner_pool.providers.free_model_discovery.discover_free_models(force=True)",
            "probe": roster.get("cache") or {},
            "module_error": roster.get("module_error"),
        },
        "roster": {
            "live": live,
            "count": len(live),
            # "probe" = this run asked the CLI; "carried_forward_after_failed_probe"
            # = this run could not, so the list is the last trusted answer and
            # `quality` is "failed". Read them together or the list will be read as
            # a fresh reading it is not.
            "origin": roster_origin,
            "retired_candidates_named_in_table": retired_candidates,
            "live_but_unnamed_in_table": live_but_unnamed,
        },
        "roles": {
            "available": bool(roles.get("available")),
            "module_error": roles.get("module_error"),
            "selection": selection,
            "detail": role_rows,
            "starved": starved,
        },
        "worker_table": {
            # What a *fresh* process reads. The running daemon built its router once
            # from this table at its first delivery use, so this is not a claim
            # about what that process holds.
            "flat": roles.get("flat_table") or {},
        },
        "change": {
            "changed": changed,
            # "absent" (first receipt), "ok" (compared), or "unreadable" (a previous
            # receipt exists and could not be used). Grep this before reading
            # `changed`: a null there means different things in each case.
            "comparison_state": previous_state,
            "compared_to": comparison,
            "appeared": appeared,
            "retired": retired,
            "role_selection_moved": role_moved,
            "roster_changed_at": roster_changed_at,
            "roster_first_seen_at": roster_first_seen_at,
        },
        "unproven": [
            "whether the already-running daemon's delivery router still holds the "
            "model table it imported: that router is built once and this receipt "
            "can only show what a new process would read",
            "whether this receipt's own SYSTEM identity could reach the CLI when the "
            "probe failed: `quality` and `written_by.identity` are recorded together "
            "in opencode_roster_receipt_attempts.jsonl, one line per run, so the "
            "answer survives this file being overwritten by the next run",
            "that a roster observed at this moment is the roster at any other moment: "
            "the CLI is asked once, on this tick's schedule",
        ],
    }


def _whoami() -> Optional[str]:
    import subprocess

    try:
        completed = subprocess.run(["whoami"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return (completed.stdout or "").strip() or None


# --------------------------------------------------------------------------- #
# recording the change where the system can see it
# --------------------------------------------------------------------------- #

def record_change(root: Path, receipt: Dict[str, Any], *, observer: Any = _OBSERVE) -> Dict[str, Any]:
    """Record a roster change as one observation. Returns what happened.

    Only a change is recorded, and only when it was actually observed: a steady
    roster records nothing, and a failed probe records nothing, so this cannot
    become an hourly alarm. The dedup key is the change itself, so the same
    rotation seen twice is one observation and a later rotation is a new one.
    """
    change = receipt.get("change") or {}
    if change.get("changed") is not True:
        return {"recorded": False, "reason": "no observed change"}
    if observer is _OBSERVE:
        try:
            from core.observation import RuntimeObserver

            observer = RuntimeObserver(
                data_dir=str(Path(root).resolve() / OBSERVATIONS_RELPATH))
        except Exception as exc:  # noqa: BLE001
            return {"recorded": False, "reason": f"observer unavailable: {type(exc).__name__}"}
    if observer is None:
        return {"recorded": False, "reason": "observer unavailable"}

    appeared = change.get("appeared") or []
    retired = change.get("retired") or []
    role_moved = change.get("role_selection_moved") or {}
    starved = (receipt.get("roles") or {}).get("starved") or []
    bits = []
    if retired:
        bits.append(f"{len(retired)} retired ({', '.join(retired[:4])})")
    if appeared:
        bits.append(f"{len(appeared)} appeared ({', '.join(appeared[:4])})")
    if role_moved:
        bits.append(f"{len(role_moved)} role(s) moved: {', '.join(sorted(role_moved)[:4])}")
    if starved:
        bits.append(f"roles with no live candidate: {', '.join(starved)}")
    description = "the free OpenCode roster changed: " + ("; ".join(bits) or "unspecified")

    dedup_key = "opencode_roster_change:" + _sha12(
        ",".join(appeared), "|", ",".join(retired), "|", ",".join(sorted(role_moved)))
    try:
        observer.record(
            description=description,
            system_state={
                "appeared": appeared,
                "retired": retired,
                "role_selection_moved": role_moved,
                "starved": starved,
                "live_count": (receipt.get("roster") or {}).get("count"),
                "roster_changed_at": change.get("roster_changed_at"),
                "quality": receipt.get("quality"),
                "contract_version": "ace.opencode_roster_receipt.v1",
            },
            severity="high" if starved else "medium",
            source="opencode_roster_receipt",
            category="environment_change",
            dedup_key=dedup_key,
        )
    except Exception as exc:  # noqa: BLE001 - the receipt must survive this
        return {"recorded": False, "reason": f"record raised: {type(exc).__name__}",
                "dedup_key": dedup_key}
    return {"recorded": True, "dedup_key": dedup_key, "description": description}


# --------------------------------------------------------------------------- #
# writing
# --------------------------------------------------------------------------- #

def write_receipt(root: Path, receipt: Dict[str, Any]) -> Path:
    path = Path(root).resolve() / RECEIPT_RELPATH
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(receipt, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            try:
                temporary.unlink()
            except OSError:
                pass
    return path


def append_attempt(root: Path, receipt: Dict[str, Any]) -> Path:
    """One line per run, so the receipt's own overwrites stop hiding its history.

    The receipt is a snapshot: whoever writes last wins, and two identities run this
    file - the hourly tick as SYSTEM, and whoever runs it by hand as Administrator.
    That made the question this component exists downstream of unanswerable from
    disk: "can the identity the schedule uses actually reach the CLI?". Each
    successful probe erased the signature of the failed one, and a failed probe's
    empty list then became the next comparison's baseline - measured on 2026-10-19
    at 10:34, when that produced a change observation for a rotation that never
    happened. This file is append-only and keeps that answer.
    """
    path = Path(root).resolve() / ATTEMPTS_RELPATH
    path.parent.mkdir(parents=True, exist_ok=True)
    change = receipt.get("change") or {}
    probe = (receipt.get("source") or {}).get("probe") or {}
    line = {
        "written_at": receipt.get("written_at"),
        "identity": (receipt.get("written_by") or {}).get("identity"),
        "pid": (receipt.get("written_by") or {}).get("pid"),
        "status": receipt.get("status"),
        "quality": receipt.get("quality"),
        "probe_source": probe.get("source"),
        "probe_error": probe.get("error"),
        "probe_age_seconds": probe.get("age_seconds"),
        "live_count": (receipt.get("roster") or {}).get("count"),
        "live_origin": (receipt.get("roster") or {}).get("origin"),
        "changed": change.get("changed"),
        "comparison_state": change.get("comparison_state"),
        "starved": (receipt.get("roles") or {}).get("starved") or [],
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(line, ensure_ascii=False, sort_keys=True) + "\n")
    return path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT_DEFAULT))
    parser.add_argument("--json", action="store_true",
                        help="write the receipt and also print it as JSON (the tick's invocation)")
    parser.add_argument("--print-only", action="store_true",
                        help="print without writing, for reading a receipt")
    args = parser.parse_args(argv)

    root = Path(args.root)
    receipt = build_receipt(root)
    receipt["change"]["observation"] = record_change(root, receipt)

    if args.print_only:
        path = Path(root).resolve() / RECEIPT_RELPATH
    else:
        path = write_receipt(root, receipt)
        append_attempt(root, receipt)
    if args.json or args.print_only:
        print(json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    else:
        print(f"receipt written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
