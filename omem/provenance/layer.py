"""Provenance layer — Phase 7 of the v2 implementation plan.

Normalises the existing ``Provenance`` / ``Evidence`` types across
memory, state, graph, and codebase indexing. Adds a queryable lineage
chain so every output can be traced back to its source.

Implementation target: docs/roadmap/FULL_IMPLEMENTATION_PLAN.md Phase 7.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ProvenanceEvent:
    """A single provenance record in a lineage chain."""

    id: str
    entity_id: str         # memory_id | snapshot_id | edge_id
    entity_type: str       # memory | snapshot | edge | state
    operation: str         # create | update | merge | forget | fork
    source: str            # user | agent | consolidation | ingestion
    timestamp: float
    namespace: str = "default"
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProvenanceChain:
    """Full lineage chain for a single entity."""

    root_id: str
    events: List[ProvenanceEvent] = field(default_factory=list)


class ProvenanceOS:
    """V2 provenance layer.

    This class is a typed stub. All methods raise ``NotImplementedError``
    until Phase 7 is implemented.

    Example (after Phase 7)::

        prov = ProvenanceOS(omem=agent.memory.omem)
        chain = prov.trace(memory_id="mem-abc123")
        for event in chain.events:
            print(event.source, event.operation, event.timestamp)
    """

    def trace(self, entity_id: str) -> ProvenanceChain:
        """Return the full lineage chain for a memory or snapshot ID."""
        raise NotImplementedError("Phase 7 — see docs/roadmap/FULL_IMPLEMENTATION_PLAN.md")

    def history(
        self,
        namespace: str,
        limit: int = 100,
        since: Optional[float] = None,
    ) -> List[ProvenanceEvent]:
        """Return recent provenance events for a namespace."""
        raise NotImplementedError("Phase 7 — see docs/roadmap/FULL_IMPLEMENTATION_PLAN.md")
