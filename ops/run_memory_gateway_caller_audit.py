"""Record a bounded, local smoke audit of ACE's single memory entrypoint."""

from __future__ import annotations

import hashlib
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from ace_daemon import AceDaemon


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_VERSION = "ace.memory_gateway.caller_unification.v1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit() -> dict:
    daemon_source = ROOT / "ace_daemon.py"
    cli_source = ROOT / "ace.py"
    daemon_text = daemon_source.read_text(encoding="utf-8")
    cli_text = cli_source.read_text(encoding="utf-8")

    # This audit targets memory wiring, not workstation resource discovery.
    # Use a disposable workspace and explicit no-assets config so it never
    # scans the operator's home folders or contacts a provider.
    AceDaemon._find_eco_layer = lambda self: []
    AceDaemon._find_omega_final = lambda self: []
    AceDaemon._find_mine_seed = lambda self: None
    with tempfile.TemporaryDirectory(prefix="ace-memory-gateway-audit-") as temp_name:
        daemon = AceDaemon(
            Path(temp_name),
            {"runtime": {"miner_pool_assets_path": str(Path(temp_name) / "no-assets")}},
        )
        gateway = daemon.memory_gateway
        consumers = [
            component
            for component in vars(daemon).values()
            if hasattr(component, "memory_index")
        ]
        checks = {
            "single_gateway_backend": (
                gateway.backend_name == "MemoryIndex"
                and daemon.memory_index is gateway
                and daemon.disk_scanner.memory_index is gateway
                and daemon_text.count("MemoryIndex(self.data_dir") == 1
                and "self.memory_gateway = MemoryGateway(" in daemon_text
            ),
            "all_wired_consumers_share_gateway": bool(consumers)
            and all(component.memory_index is gateway for component in consumers),
            "daemon_has_no_direct_memory_index_reads_or_writes": not any(
                token in daemon_text
                for token in (
                    "self.memory_index.add(",
                    "self.memory_index.search(",
                    "self.memory_index.get_",
                )
            ),
            "candidate_kernel_not_in_daemon_path": (
                "from core.memory_kernel import MemoryKernel" not in daemon_text
                and "MemoryKernel(" not in daemon_text
            ),
            "legacy_cli_fails_closed": (
                'if cmd in {"test", "lexicon", "mem", "scan", "scan-fragments"}' in cli_text
                and cli_text.index('if cmd in {"test", "lexicon", "mem", "scan", "scan-fragments"}')
                < cli_text.index("from ace_daemon import AceDaemon")
            ),
        }
        status = "PASS_SINGLE_GATEWAY_RUNTIME_AUDIT" if all(checks.values()) else "FAIL"
        return {
            "contract_version": CONTRACT_VERSION,
            "status": status,
            "occurred_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "daemon_source_sha256": _sha256(daemon_source),
            "cli_source_sha256": _sha256(cli_source),
            "wired_consumer_count": len(consumers),
            "checks": checks,
            "provider_calls": 0,
            "production_data_writes": 0,
            "execution_authorized": False,
            "production_integration": False,
            "evidence_authenticated": False,
        }


def main() -> int:
    receipt = audit()
    output = ROOT / "08_GOVERNANCE" / "evidence" / "memory_gateway_caller_unification_20260928.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt["receipt_ref"] = output.relative_to(ROOT).as_posix()
    output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0 if receipt["status"] == "PASS_SINGLE_GATEWAY_RUNTIME_AUDIT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
