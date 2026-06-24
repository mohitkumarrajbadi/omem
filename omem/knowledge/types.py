"""Public data types for the v2 knowledge layer (Phase 4).

All types are fully serializable (to_dict / from_dict) and carry enough
information for callers to display, reason about, and persist results
without importing any internal graph primitives.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class EdgeRecord:
    """A single typed relation between two entities.

    Intentionally flat — avoids exposing the internal ``Edge`` dataclass
    from ``omem.core.graph.knowledge``.
    """

    id: str
    source: str
    target: str
    predicate: str          # EdgeType.value, e.g. "uses", "related_to"
    confidence: float = 1.0
    weight: float = 1.0
    memory_id: str = ""
    evidence_count: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "predicate": self.predicate,
            "confidence": self.confidence,
            "weight": self.weight,
            "memory_id": self.memory_id,
            "evidence_count": self.evidence_count,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EdgeRecord":
        return cls(
            id=d["id"],
            source=d["source"],
            target=d["target"],
            predicate=d["predicate"],
            confidence=d.get("confidence", 1.0),
            weight=d.get("weight", 1.0),
            memory_id=d.get("memory_id", ""),
            evidence_count=d.get("evidence_count", 1),
        )


@dataclass
class GraphSubgraph:
    """A slice of the knowledge graph centred on a root entity.

    Contains the full set of reachable nodes and edges within ``depth`` hops,
    plus the memory IDs linked to those entities — so callers can load the
    backing memories without a second lookup.
    """

    root_entity: str
    depth: int = 1
    nodes: List[Any] = field(default_factory=list)      # List[GraphNode]
    edges: List[EdgeRecord] = field(default_factory=list)
    entity_count: int = 0
    edge_count: int = 0
    related_memory_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "root_entity": self.root_entity,
            "depth": self.depth,
            "nodes": [
                {"id": n.id, "label": n.label, "kind": n.kind.value,
                 "entity_type": n.entity_type, "confidence": n.confidence}
                for n in self.nodes
            ],
            "edges": [e.to_dict() for e in self.edges],
            "entity_count": self.entity_count,
            "edge_count": self.edge_count,
            "related_memory_ids": self.related_memory_ids,
        }


@dataclass
class InferenceResult:
    """A single inferred statement produced by the reasoning engine.

    ``reasoning_path`` holds the chain of entities traversed to produce
    the statement.  ``inference_type`` is either ``"direct"`` (1-hop fact)
    or ``"transitive"`` (multi-hop inference — lower confidence).
    """

    statement: str
    confidence: float
    supporting_memory_ids: List[str] = field(default_factory=list)
    reasoning_path: List[str] = field(default_factory=list)
    inference_type: str = "direct"  # "direct" | "transitive"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "statement": self.statement,
            "confidence": self.confidence,
            "supporting_memory_ids": self.supporting_memory_ids,
            "reasoning_path": self.reasoning_path,
            "inference_type": self.inference_type,
        }


@dataclass
class KnowledgeStats:
    """Aggregate statistics about the current knowledge graph state."""

    total_entities: int = 0
    total_nodes: int = 0
    total_edges: int = 0
    top_entities: List[Tuple[str, float]] = field(default_factory=list)
    edge_type_distribution: Dict[str, int] = field(default_factory=dict)
    avg_centrality: float = 0.0
    causal_links: int = 0
    dependency_links: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total_entities": self.total_entities,
            "total_nodes": self.total_nodes,
            "total_edges": self.total_edges,
            "top_entities": [
                {"name": name, "centrality": round(c, 4)}
                for name, c in self.top_entities
            ],
            "edge_type_distribution": self.edge_type_distribution,
            "avg_centrality": round(self.avg_centrality, 4),
            "causal_links": self.causal_links,
            "dependency_links": self.dependency_links,
        }
