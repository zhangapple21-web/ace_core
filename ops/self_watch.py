#!/usr/bin/env python3
"""Self-watch: one read-only view over the system's self-monitoring.

Introspective Evolution = surprise + drought + tension + needs + gate
decisions + watchdog ages, as recorded in daemon state and observations.
Artifact Sensing = fragment index + archaeologist + mine-seed scanner
states. Pure reads: no imports with side effects, no writes, no model
calls, no subprocess except an optional best-effort git check.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))


def _read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _age_hours(mtime: float, now: float) -> float | None:
    if not mtime:
        return None
    return round(max(0.0, now - mtime) / 3600.0, 1)


def introspection(base: Path, now: float) -> dict:
    """How the system watches itself, from its own records."""
    state = _read_json(base / "06_RUNTIME" / "ace" / "data" / "memory" / "daemon_state.json") or {}
    out: dict = {
        "daemon": {
            "pid": state.get("pid"),
            "run_status": state.get("run_status"),
            "last_run": state.get("last_run"),
        },
        "surprise": state.get("last_surprise_snapshot") or state.get("last_surprise_check"),
        "drought": state.get("last_drought_snapshot"),
        "gate_decisions": state.get("stage_gate_decisions"),
        "shift_due": (state.get("free_zone_model_shift_due") or {}).get("status"),
    }
    needs: list = []
    obs_file = base / "06_RUNTIME" / "ace" / "data" / "observations" / "observations.jsonl"
    try:
        lines = obs_file.read_text(encoding="utf-8").strip().splitlines()
    except OSError:
        lines = []
    for line in lines[-200:]:
        try:
            obs = json.loads(line)
        except ValueError:
            continue
        if obs.get("category") == "need":
            state_field = (obs.get("system_state") or {})
            needs.append({
                "obs_id": obs.get("obs_id"),
                "need": state_field.get("need"),
                "created_at": obs.get("created_at"),
            })
    out["needs_active"] = needs[-5:]
    out["needs_count"] = len(needs)
    providers: list = []
    try:
        from core.miner_pool.provider_watchdog import (
            STALE_TTL_SECONDS,
            effective_status_for,
            observation_age_hours,
        )

        snapshot = _read_json(
            base / "06_RUNTIME" / "ace" / "data" / "miner_pool" / "provider_watchdog" / "watchdog_state.json"
        ) or {}
        for name in sorted((snapshot.get("providers") or {})):
            record = snapshot["providers"][name]
            if not isinstance(record, dict):
                continue
            age = observation_age_hours(record, now=now)
            providers.append({
                "name": name,
                "stored": record.get("status"),
                "effective": effective_status_for(record, now=now, ttl_seconds=STALE_TTL_SECONDS),
                "age_hours": round(age, 1) if age is not None else None,
            })
    except Exception:
        pass
    out["providers"] = providers
    return out


def artifact_sensing(base: Path, now: float) -> dict:
    """What the system knows about the artifact world, from index files."""
    out: dict = {}
    frag_file = base / "02_FRAGMENT_INDEX" / "fragment_index.json"
    frag = _read_json(frag_file)
    by_status: dict = {}
    total = 0
    if isinstance(frag, dict):
        index = frag.get("index")
        if not isinstance(index, dict):
            index = frag
        for rec in index.values():
            status = rec.get("status", "seen") if isinstance(rec, dict) else "seen"
            by_status[status] = by_status.get(status, 0) + 1
        total = sum(by_status.values())
    try:
        mtime = frag_file.stat().st_mtime
    except OSError:
        mtime = 0.0
    out["fragment_index"] = {"total": total, "by_status": by_status, "age_hours": _age_hours(mtime, now)}

    arch = base / "06_RUNTIME" / "ace" / "data" / "local_archaeologist_state.json"
    try:
        out["archaeologist"] = {"age_hours": _age_hours(arch.stat().st_mtime, now),
                                "bytes": arch.stat().st_size}
    except OSError:
        out["archaeologist"] = None

    ms_file = base / "02_FRAGMENT_INDEX" / ".mine_seed_state.json"
    ms = _read_json(ms_file) or {}
    out["mine_seed"] = {"last_commit": (ms.get("last_commit") or "")[:12] or None}
    try:
        completed = subprocess.run(
            ["git", "-C", str(base.parent / "mine-seed"), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=30,
        )
        head = completed.stdout.strip() if completed.returncode == 0 else None
    except Exception:
        head = None
    out["mine_seed"]["head"] = head
    out["mine_seed"]["in_sync"] = bool(head and out["mine_seed"]["last_commit"] and
                                      head.startswith(out["mine_seed"]["last_commit"][:7]))
    return out


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="ACE self-watch (read-only)")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--root", default=str(BASE_DIR))
    args = parser.parse_args()
    base = Path(args.root)
    now = time.time()
    report = {
        "at": datetime.now().isoformat(timespec="seconds"),
        "introspective_evolution": introspection(base, now),
        "artifact_sensing": artifact_sensing(base, now),
    }
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
        return 0
    intro = report["introspective_evolution"]
    sens = report["artifact_sensing"]
    print("== introspective ==")
    print(f"daemon pid={intro['daemon'].get('pid')} status={intro['daemon'].get('run_status')} last_run={intro['daemon'].get('last_run')}")
    print(f"drought={intro['drought']} shift_due={intro['shift_due']} needs={intro['needs_count']}")
    print(f"gates={json.dumps(intro['gate_decisions'], ensure_ascii=False, default=str)[:200]}")
    for provider in intro["providers"]:
        print(f"  {provider['name']}: {provider['stored']}->{provider['effective']} age={provider['age_hours']}h")
    print("== artifacts ==")
    print(f"fragments={sens['fragment_index']}")
    print(f"archaeologist={sens['archaeologist']} mine_seed={sens['mine_seed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
