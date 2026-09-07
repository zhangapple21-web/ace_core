#!/usr/bin/env python3
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_configured_sekiro_skeleton_does_not_report_decryption_success():
    from core.protocols.handlers.rpc_handler import RPCHandler

    handler = RPCHandler(rpc_endpoint="http://127.0.0.1:5612")

    result = handler.unpack(b"encrypted payload")

    assert result.success is False
    assert "not implemented" in result.error.lower()


def test_configured_unidbg_skeleton_does_not_report_decryption_success():
    from core.protocols.handlers.unidbg_handler import UnidbgHandler

    handler = UnidbgHandler(
        so_path="C:/fixtures/libtarget.so",
        decrypt_func="decrypt",
    )

    result = handler.unpack(b"encrypted payload")

    assert result.success is False
    assert "not implemented" in result.error.lower()


def test_unidbg_backend_result_does_not_expose_simulated_success_fields():
    from core.protocols.handlers.unidbg_handler import UnidbgHandler

    handler = UnidbgHandler()
    result = handler._process_result(
        {
            "decrypted": True,
            "method": "unidbg_simulated",
            "status": "unavailable",
        },
        b"encrypted payload",
    )

    assert result.get("decrypted") is not True
    assert result.get("method") != "unidbg_simulated"
    assert "unidbg_simulated" not in str(result)


def test_unidbg_unimplemented_result_does_not_claim_decryption_or_simulation():
    from core.protocols.handlers.unidbg_handler import UnidbgHandler

    handler = UnidbgHandler()
    result = handler._process_result({"status": "unavailable"}, b"encrypted payload")

    assert "decrypted" not in result
    assert "method" not in result
    assert "unidbg_simulated" not in str(result)


def test_unidbg_pool_does_not_mark_unimplemented_instances_as_loaded():
    from core.protocols.unidbg_pool import UnidbgPool

    pool = UnidbgPool()
    instance = pool._create_instance("C:/fixtures/libtarget.so")

    assert instance.loaded is False
    assert instance.is_healthy() is False


def test_registry_retries_a_cached_failure_after_the_handler_recovers():
    from core.protocols.base import ProtocolHandler, UnpackResult
    from core.protocols.registry import ProtocolRegistry

    class RecoveringHandler(ProtocolHandler):
        name = "recovering"
        protocol = "recoverable"
        priority = 1

        def __init__(self):
            self.calls = 0
            self.recovered = False

        def identify(self, data):
            return True

        def unpack(self, data):
            self.calls += 1
            if not self.recovered:
                return UnpackResult.fail("backend unavailable", self.protocol, self.name)
            return UnpackResult.ok({"value": "decoded"}, self.protocol, self.name)

    handler = RecoveringHandler()
    registry = ProtocolRegistry()
    registry.register(handler)

    first = registry.unpack(b"payload", protocol="recoverable")
    handler.recovered = True
    second = registry.unpack(b"payload", protocol="recoverable")

    assert first.success is False
    assert second.success is True
    assert second.data == {"value": "decoded"}
    assert handler.calls == 2


