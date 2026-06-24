"""V2 knowledge layer — Phase 4 of the implementation plan.

Purpose: clean public API over the existing omem.core.graph substrate.
This package wraps knowledge.py, causal.py, and dependency.py behind
memory-native verbs without touching the engine.

APIs (implemented in Phase 4):
    KnowledgeOS.link()     — add a typed relation between entities
    KnowledgeOS.query()    — retrieve entity subgraph to given depth
    KnowledgeOS.reason()   — simple inference over known facts
    KnowledgeOS.entities() — list all known entities in a namespace

See: docs/roadmap/FULL_IMPLEMENTATION_PLAN.md — Phase 4
"""

from .layer import KnowledgeOS

__all__ = ["KnowledgeOS"]
