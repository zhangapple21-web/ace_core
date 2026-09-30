"""The single production facade for ACE's existing memory backend.

The gateway deliberately wraps only ``MemoryIndex``'s established API. It has
no implicit MemoryKernel reads, dual writes, backend selector, or migration
side effects. A future backend replacement must still pass the registered
cutover gate before this one binding changes.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol


class _MemoryBackend(Protocol):
    def add(self, *args: Any, **kwargs: Any) -> str: ...
    def search(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]: ...
    def get_by_concept(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]: ...
    def get_recent(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]: ...
    def get_stats(self) -> dict[str, Any]: ...
    def get_concept_graph(self, *args: Any, **kwargs: Any) -> dict[str, Any]: ...


class MemoryGateway:
    """One compatibility boundary over the currently approved backend.

    Consumers use the legacy-compatible methods below and never receive the
    backend object. In particular, the production facade intentionally does
    not expose ``search_governed`` or ``import_records`` from the staged
    MemoryKernel candidate.
    """

    contract_version = "ace.memory_gateway.v1"
    backend_name = "MemoryIndex"

    def __init__(self, backend: _MemoryBackend) -> None:
        required = ("add", "search", "get_by_concept", "get_recent", "get_stats", "get_concept_graph")
        missing = [name for name in required if not callable(getattr(backend, name, None))]
        if missing:
            raise TypeError("memory_backend_contract_invalid:" + ",".join(missing))
        self.__backend = backend

    @property
    def index_file(self):
        """Read-only location of the active backend file for diagnostics."""
        return getattr(self.__backend, "index_file", None)

    def add(self, *args: Any, **kwargs: Any) -> str:
        return self.__backend.add(*args, **kwargs)

    def search(
        self,
        keyword: Optional[str] = None,
        memory_type: Optional[str] = None,
        category: Optional[str] = None,
        tag: Optional[str] = None,
        concept: Optional[str] = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        return self.__backend.search(
            keyword=keyword,
            memory_type=memory_type,
            category=category,
            tag=tag,
            concept=concept,
            limit=limit,
        )

    def get_by_concept(self, concept_name: str, limit: int = 20) -> list[dict[str, Any]]:
        return self.__backend.get_by_concept(concept_name, limit=limit)

    def get_recent(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.__backend.get_recent(limit=limit)

    def get_stats(self) -> dict[str, Any]:
        return self.__backend.get_stats()

    def get_concept_graph(self, depth: int = 2) -> dict[str, Any]:
        return self.__backend.get_concept_graph(depth=depth)
