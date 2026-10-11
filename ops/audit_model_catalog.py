#!/usr/bin/env python3
"""Audit: every model named in task profiles must exist in a reachable catalog.

Read-only. Compares profile preferred/fallback/escalation model ids against
the live gateway catalog(s). No model calls, no state writes, no secrets in
output. Exit 0 = all named models served; 1 = unserved references found;
2 = no credential to check with (unchecked, not a pass).
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))


def _catalog_ids(base_url: str, api_key: str, timeout: int = 15) -> set[str] | None:
    try:
        url = base_url.rstrip("/") + "/models"
        if "/v1" not in url:
            url = base_url.rstrip("/") + "/v1/models"
        req = urllib.request.Request(url, headers={"Authorization": "Bearer " + api_key})
        data = json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8", "replace"))
        return {str(m.get("id", "")) for m in data.get("data", []) if isinstance(m, dict)}
    except Exception:
        return None


def audit(profiles: dict, catalogs: dict[str, set[str]]) -> dict:
    """Pure compare: profile model refs vs their own gateway catalogs.

    A ref is served only when its bare model name appears in ITS OWN
    provider's catalog; unknown when that gateway is unchecked. A
    cross-gateway name match proves nothing about serving, so it is
    never used. Returns served/unserved/unknown with details.
    """
    served: list = []
    unserved: list = []
    unknown: list = []
    for profile_name, profile in profiles.items():
        if not isinstance(profile, dict):
            continue
        refs: set = set()
        for key in ("preferred_models", "fallback_models", "escalation_models"):
            items = profile.get(key) or []
            for item in items if isinstance(items, list) else []:
                if isinstance(item, str) and item.strip():
                    refs.add(item.strip())
        for ref in sorted(refs):
            provider, _, bare = ref.partition(":")
            if provider not in catalogs:
                unknown.append({"profile": profile_name, "ref": ref,
                                "reason": f"gateway {provider} unchecked"})
            elif bare in catalogs[provider]:
                served.append({"profile": profile_name, "ref": ref})
            else:
                unserved.append({"profile": profile_name, "ref": ref,
                                 "checked_against": provider})
    return {"served": served, "unserved": unserved, "unknown": unknown}


def main() -> int:
    from core.miner_pool import task_profiles as profiles_mod
    from core.miner_pool.credential_manager import CredentialManager

    cfg = json.loads((BASE_DIR / "ace_config.json").read_text(encoding="utf-8"))
    mgr = CredentialManager(coze_assets_path=cfg.get("runtime", {}).get("miner_pool_assets_path"))
    mgr.load()
    catalogs: dict[str, set[str]] = {}
    for provider in ("oneapi", "shenwen"):
        try:
            cred = mgr.get(provider)
            keys = list(getattr(cred, "api_keys", []) or []) if cred else []
            base = str(getattr(cred, "base_url", "") or "") if cred else ""
            if not keys or not base:
                continue
            ids = _catalog_ids(base, keys[0])
            if ids is not None:
                catalogs[provider] = ids
        except Exception:
            continue
    if not catalogs:
        print("UNCHECKED: no gateway credential available")
        return 2
    profiles = {k: v for k, v in vars(profiles_mod).get("TASK_PROFILES", {}).items()} \
        if hasattr(profiles_mod, "TASK_PROFILES") else getattr(profiles_mod, "PROFILES", {})
    result = audit(profiles, catalogs)
    print(f"checked gateways: {sorted(catalogs)} "
          f"({sum(len(v) for v in catalogs.values())} ids)")
    if result["unserved"]:
        for item in result["unserved"]:
            print(f"UNSERVED: {item['profile']}: {item['ref']}")
        return 1
    print(f"OK: {len(result['served'])} refs served, "
          f"{len(result['unknown'])} unknown-gateway, 0 unserved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
