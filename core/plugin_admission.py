"""Fail-closed plugin admission.

Checks host version, declared peers, and whether a plugin dependency would
shadow a host module. Does not install, execute, or exempt anything.
"""

from __future__ import annotations

HOST_MODULES = ("@deepseek-ai/dsh-settings",)


def admit_plugin(manifest: dict, *, host_version: str, resolved: dict | None = None) -> dict:
    """Return a redacted admission envelope. Never raises on bad input."""
    resolved = resolved or {}
    name = str((manifest or {}).get("name") or "unknown")
    reasons = []
    engines = ((manifest or {}).get("engines") or {}).get("dsh")
    if not engines:
        reasons.append({"code": "missing_host_engine", "component": name})
    peers = (manifest or {}).get("peerDependencies") or {}
    deps = (manifest or {}).get("dependencies") or {}
    for dep, pin in {**peers, **deps}.items():
        got = resolved.get(dep)
        if got and got != pin and pin and any(ch.isdigit() for ch in str(pin)):
            if str(pin).startswith((">", "<", "^", "~")):
                continue
            reasons.append({
                "code": "peer_pin_conflict",
                "component": dep,
                "declared": str(pin),
                "resolved": str(got),
            })
        if dep in HOST_MODULES and got and got != host_version and not str(got).startswith(host_version):
            reasons.append({
                "code": "host_module_shadow",
                "component": dep,
                "resolved": str(got),
                "host": host_version,
            })
    decision = "reject" if reasons else "allow"
    return {
        "phase": "plugin_admission",
        "component": name,
        "host_version": host_version,
        "decision": decision,
        "rollback": "isolate_plugin_tree" if decision == "reject" else "none",
        "reasons": reasons,
    }
