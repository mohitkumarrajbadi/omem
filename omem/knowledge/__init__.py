"""V2 knowledge layer — clean public API over the graph substrate (Phase 4).

This package wraps ``omem.core.graph`` (KnowledgeGraph, CausalGraph,
DependencyGraph) behind memory-native verbs without exposing internals.

Quick start::

    from omem.knowledge import KnowledgeOS

    knowledge = KnowledgeOS()
    knowledge.link("FastAPI", "uses", "Pydantic")
    subgraph = knowledge.query("FastAPI", depth=2)
    facts = knowledge.reason("What does FastAPI use?")

See: docs/roadmap/FULL_IMPLEMENTATION_PLAN.md — Phase 4
"""

from .layer import KnowledgeOS
from .types import EdgeRecord, GraphSubgraph, InferenceResult, KnowledgeStats

__all__ = [
    "KnowledgeOS",
    "EdgeRecord",
    "GraphSubgraph",
    "InferenceResult",
    "KnowledgeStats",
]
