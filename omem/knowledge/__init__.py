"""V2 knowledge layer — clean public API over the graph substrate (Phase 4).

This package wraps ``omem.core.graph`` (KnowledgeGraph, CausalGraph,
DependencyGraph) behind memory-native verbs without exposing internals.

Quick start::

    from omem.knowledge import KnowledgeOS

    knowledge = KnowledgeOS()
    knowledge.link("FastAPI", "uses", "Pydantic")
    subgraph = knowledge.query("FastAPI", depth=2)
    facts = knowledge.reason("What does FastAPI use?")

The Python AST codebase index is **Alpha** and is not imported here by default.
Enable with ``OMEM_ENABLE_EXPERIMENTAL_AST=1`` and import from
``omem.experimental.ast_index`` (or ``omem.knowledge.codebase`` after the flag
is set).

See: docs/roadmap/FULL_IMPLEMENTATION_PLAN.md — Phase 4
"""

from __future__ import annotations

from typing import Any

from .layer import KnowledgeOS
from .types import EdgeRecord, GraphSubgraph, InferenceResult, KnowledgeStats

__all__ = [
    "KnowledgeOS",
    "EdgeRecord",
    "GraphSubgraph",
    "InferenceResult",
    "KnowledgeStats",
]

_AST_EXPORTS = frozenset({
    "CodeSymbol",
    "SymbolType",
    "ProjectIngester",
    "ProjectGraph",
    "ProjectSync",
    "CodeRetriever",
})


def __getattr__(name: str) -> Any:
    """Lazy Alpha re-exports — only when OMEM_ENABLE_EXPERIMENTAL_AST is set."""
    if name not in _AST_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from omem.experimental import require_ast

    require_ast(f"omem.knowledge.{name}")
    from omem.knowledge import codebase as _codebase

    return getattr(_codebase, name)
