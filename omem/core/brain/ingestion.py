"""Graph-first memory ingestion pipeline.

Experience → Understand → Connect

Parses text, extracts entities/relations, and binds graph structure to memories.
"""

from dataclasses import dataclass, field
from typing import List

from ...types import Memory
from ..graph.knowledge import KnowledgeGraph


@dataclass
class IngestResult:
    """Structured output from graph-first ingestion."""

    memory_id: str
    node_ids: List[str] = field(default_factory=list)
    edge_ids: List[str] = field(default_factory=list)
    entities: List[str] = field(default_factory=list)
    confidence: float = 1.0
    evidence_count: int = 1
    relation_types: List[str] = field(default_factory=list)


def ingest_experience(
    graph: KnowledgeGraph,
    memory_id: str,
    content: str,
    source: str = "user",
    confidence: float = 1.0,
    namespace: str = "default",
    user_name: str = "",
) -> IngestResult:
    """Run the graph ingestion pipeline for a new memory."""
    payload = graph.ingest_experience(
        memory_id=memory_id,
        content=content,
        source=source,
        confidence=confidence,
        namespace=namespace,
        user_name=user_name,
    )
    return IngestResult(
        memory_id=memory_id,
        node_ids=payload.get("node_ids", []),
        edge_ids=payload.get("edge_ids", []),
        entities=payload.get("entities", []),
        confidence=payload.get("confidence", confidence),
        evidence_count=payload.get("evidence_count", 1),
        relation_types=payload.get("relation_types", []),
    )


def apply_ingest_to_memory(memory: Memory, ingest: IngestResult) -> None:
    """Attach graph substrate metadata to a Memory record."""
    memory.node_ids = ingest.node_ids
    memory.edge_ids = ingest.edge_ids
    memory.entities = ingest.entities
    memory.confidence_score = ingest.confidence
    memory.evidence_count = ingest.evidence_count
    if not memory.provenance:
        memory.provenance = memory.source or "user"
