from core.memory_gateway import MemoryGateway


class _FakeMemoryIndex:
    index_file = "memory_index.json"

    def __init__(self):
        self.calls = []

    def add(self, *args, **kwargs):
        self.calls.append(("add", args, kwargs))
        return "mem-1"

    def search(self, **kwargs):
        self.calls.append(("search", (), kwargs))
        return [{"id": "mem-1"}]

    def get_by_concept(self, concept_name, limit=20):
        self.calls.append(("get_by_concept", (concept_name,), {"limit": limit}))
        return [{"id": "mem-1"}]

    def get_recent(self, limit=20):
        self.calls.append(("get_recent", (), {"limit": limit}))
        return [{"id": "mem-1"}]

    def get_stats(self):
        self.calls.append(("get_stats", (), {}))
        return {"total": 1}

    def get_concept_graph(self, depth=2):
        self.calls.append(("get_concept_graph", (), {"depth": depth}))
        return {"nodes": [], "edges": []}


def test_gateway_is_a_narrow_legacy_compatible_facade():
    backend = _FakeMemoryIndex()
    gateway = MemoryGateway(backend)

    assert gateway.backend_name == "MemoryIndex"
    assert gateway.index_file == "memory_index.json"
    assert gateway.add(title="t", content="c") == "mem-1"
    assert gateway.search(keyword="term", limit=3) == [{"id": "mem-1"}]
    assert gateway.get_by_concept("concept", limit=4) == [{"id": "mem-1"}]
    assert gateway.get_recent(limit=5) == [{"id": "mem-1"}]
    assert gateway.get_stats() == {"total": 1}
    assert gateway.get_concept_graph(depth=1) == {"nodes": [], "edges": []}
    assert [call[0] for call in backend.calls] == [
        "add",
        "search",
        "get_by_concept",
        "get_recent",
        "get_stats",
        "get_concept_graph",
    ]

    # The production facade cannot accidentally become the staged migration
    # or candidate-query route.
    assert not hasattr(gateway, "search_governed")
    assert not hasattr(gateway, "import_records")


def test_daemon_injects_one_gateway_into_wired_consumers(tmp_path):
    from ace_daemon import AceDaemon

    daemon = AceDaemon(tmp_path, {})
    gateway = daemon.memory_gateway

    assert isinstance(gateway, MemoryGateway)
    assert daemon.memory_index is gateway  # compatibility alias, not another backend
    assert daemon.disk_scanner.memory_index is gateway
    wired = {
        name: component
        for name, component in vars(daemon).items()
        if hasattr(component, "memory_index")
    }
    assert wired
    assert all(component.memory_index is gateway for component in wired.values())

    from pathlib import Path

    daemon_source = (Path(__file__).resolve().parent.parent / "ace_daemon.py").read_text(
        encoding="utf-8"
    )
    assert "memory_index=self.memory_index" not in daemon_source
    assert "self.memory_index.search(" not in daemon_source
    assert "self.memory_index.add(" not in daemon_source


def test_real_rollback_helper_rejects_non_private_data(tmp_path):
    import json

    import pytest

    from ops.run_memory_index_real_rollback import _inspect_private_index

    source = tmp_path / "fixture.json"
    source.write_text(
        json.dumps({"entries": [{"id": "fixture", "data_class": "PUBLIC"}]}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="rollback_requires_all_private_source"):
        _inspect_private_index(source)
