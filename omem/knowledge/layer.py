"""Knowledge layer facade — Phase 4 of the v2 implementation plan.

Delegates to the mature ``omem.core.graph`` substrate
(``knowledge.py``, ``causal.py``, ``dependency.py``) via the ``OMem`` API.
No new logic is added — this is purely a clean package boundary.

Implementation target: docs/roadmap/FULL_IMPLEMENTATION_PLAN.md Phase 4.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class GraphSubgraph:
    """A slice of the knowledge graph centred on an entity."""

    root_entity: str
    nodes: List[Dict[str, Any]] = field(default_factory=list)
    edges: List[Dict[str, Any]] = field(default_factory=list)
    depth: int = 1


@dataclass
class InferenceResult:
    """A single inferred fact with confidence."""

    statement: str
    confidence: float
    supporting_memory_ids: List[str] = field(default_factory=list)


class KnowledgeOS:
    """V2 knowledge layer.

    ``KnowledgeOS`` exposes the graph substrate with clean, high-level verbs.
    Internally it calls ``OMem.link_entities``, ``assert_fact``,
    ``get_graph_context``, etc.

    This class is a typed stub. All methods raise ``NotImplementedError``
    until Phase 4 is implemented.

    Example (after Phase 4)::

        knowledge = KnowledgeOS(omem=agent.memory.omem)
        knowledge.link("FastAPI", "uses", "Pydantic")
        subgraph = knowledge.query("FastAPI", depth=2)
    """

    def link(
        self,
        subject: str,
        predicate: str,
        obj: str,
        confidence: float = 1.0,
        namespace: str = "default",
        **kwargs: Any,
    ) -> str:
        """Assert a typed relation between two entities. Returns edge ID."""
        raise NotImplementedError("Phase 4 — see docs/roadmap/FULL_IMPLEMENTATION_PLAN.md")

    def query(
        self,
        entity: str,
        depth: int = 2,
        namespace: Optional[str] = None,
    ) -> GraphSubgraph:
        """Return the subgraph centred on an entity up to the given depth."""
        raise NotImplementedError("Phase 4 — see docs/roadmap/FULL_IMPLEMENTATION_PLAN.md")

    def reason(
        self,
        question: str,
        namespace: Optional[str] = None,
    ) -> List[InferenceResult]:
        """Apply heuristic inference over known facts to answer a question."""
        raise NotImplementedError("Phase 4 — see docs/roadmap/FULL_IMPLEMENTATION_PLAN.md")

    def entities(
        self,
        namespace: Optional[str] = None,
        entity_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List all known entities, optionally filtered by namespace or type."""
        raise NotImplementedError("Phase 4 — see docs/roadmap/FULL_IMPLEMENTATION_PLAN.md")
