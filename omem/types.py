"""Memory type definitions and core data structures."""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import numpy as np


class MemoryType(Enum):
    """Categories of memory stored in the system."""

    WORKING = 0  # Short-term data
    EPISODIC = 1  # Events and experiences
    SEMANTIC = 2  # General knowledge
    CAUSAL = 3  # Cause-effect links
    DECISION = 4  # Logged decisions
    PROCEDURAL = 5  # How-to steps
    ACTIVE = 6  # High-priority context
    REFLECTION = 7  # Auto-generated insights
    INSIGHT = 8  # Consolidated summaries
    SENSORY = 9  # Raw, short-lived input


class MemoryStatus(Enum):
    """Logical status of a memory."""

    ACTIVE = 0
    DEPRECATED = 1
    CONFLICTED = 2
    ARCHIVED = 3


class MemoryTier(Enum):
    """Lifecycle stages of a memory."""

    CORE = 0  # Never forgotten
    ACTIVE = 1  # Normal state
    ARCHIVE = 2  # Temporarily hidden
    FORGOTTEN = 3  # Deleted
    SENSORY = 4  # Brief storage
    INSIGHT = 5  # Consolidated results


class MemoryLevel(Enum):
    """Hierarchy level for tier-targeted retrieval (CPU-style memory hierarchy)."""

    WORKING = "working"
    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"
    ARCHIVE = "archive"


# Maps hierarchy level → allowed MemoryTier values for filtering
LEVEL_TIER_MAP: Dict[str, List["MemoryTier"]] = {
    MemoryLevel.WORKING.value: [MemoryTier.SENSORY, MemoryTier.ACTIVE],
    MemoryLevel.SHORT_TERM.value: [MemoryTier.ACTIVE],
    MemoryLevel.LONG_TERM.value: [MemoryTier.ACTIVE, MemoryTier.CORE, MemoryTier.INSIGHT],
    MemoryLevel.ARCHIVE.value: [MemoryTier.ARCHIVE],
}


def level_matches(level: str, tier: MemoryTier) -> bool:
    """Return True if a memory's tier belongs to the requested hierarchy level."""
    allowed = LEVEL_TIER_MAP.get(level, [MemoryTier.ACTIVE])
    return tier in allowed


class MemoryPriority(Enum):
    """Weighting for retrieval scores."""

    CORE = 0  # Critical (Identity, etc.)
    HIGH = 1  # Important (Goals, etc.)
    NORMAL = 2  # Standard
    LOW = 3  # Minor


class NodeKind(Enum):
    """Graph node categories in the memory substrate."""

    ENTITY = "entity"
    CONCEPT = "concept"
    INSIGHT = "insight"
    EVIDENCE = "evidence"


# Score multipliers for each priority level
PRIORITY_MULTIPLIER = {
    MemoryPriority.CORE: 2.0,
    MemoryPriority.HIGH: 1.5,
    MemoryPriority.NORMAL: 1.0,
    MemoryPriority.LOW: 0.7,
}


@dataclass
class Provenance:
    """Origin metadata for graph-backed memory units."""

    source: str = "user"
    memory_id: str = ""
    timestamp: float = field(default_factory=time.time)
    namespace: str = "default"


@dataclass
class Evidence:
    """Supporting evidence attached to a node or relation."""

    id: str
    memory_id: str
    content: str
    confidence: float = 1.0
    provenance: Provenance = field(default_factory=Provenance)
    timestamp: float = field(default_factory=time.time)


@dataclass
class GraphNode:
    """First-class graph node — entity, concept, or consolidated insight."""

    id: str
    label: str
    kind: NodeKind = NodeKind.ENTITY
    entity_type: str = "concept"
    memory_ids: List[str] = field(default_factory=list)
    mention_count: int = 1
    confidence: float = 1.0
    evidence_count: int = 1
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


@dataclass
class RelationEdge:
    """Typed, weighted edge with evidence and provenance."""

    id: str
    source_id: str
    target_id: str
    edge_type: str
    weight: float = 1.0
    strength: float = 1.0
    memory_id: str = ""
    evidence_count: int = 1
    confidence: float = 1.0
    provenance: Provenance = field(default_factory=Provenance)
    label: str = ""


@dataclass
class Memory:
    """A single memory record with importance, decay, and namespace support."""

    id: str
    type: MemoryType
    content: str
    vector: np.ndarray
    timestamp: float = field(default_factory=time.time)
    importance: float = 0.5  # 0.0 to 1.0
    utility_score: float = 0.0  # User/Agent feedback value
    access_count: int = 0
    last_accessed: float = 0.0
    namespace: str = "default"
    source: str = ""
    superseded_by: Optional[str] = None
    active: bool = True
    level: str = "working"
    status: MemoryStatus = MemoryStatus.ACTIVE

    tokens: set = field(default_factory=set)
    token_hashes: np.ndarray = field(
        default_factory=lambda: np.array([], dtype=np.uint64)
    )

    tier: MemoryTier = MemoryTier.ACTIVE
    priority: MemoryPriority = MemoryPriority.NORMAL
    archived_at: float = 0.0

    entities: List[str] = field(default_factory=list)
    node_ids: List[str] = field(default_factory=list)
    edge_ids: List[str] = field(default_factory=list)
    insight_sources: List[str] = field(default_factory=list)
    consolidation_count: int = 0

    consensus_score: float = 0.0
    confidence_score: float = 1.0  # 0.0 to 1.0 (source reliability + consistency)
    evidence_count: int = 1
    provenance: str = ""
    freshness: float = field(default_factory=time.time)
    dependencies: List[str] = field(
        default_factory=list
    )  # IDs of memories this one depends on

    verifiers: List[str] = field(default_factory=list)
    logical_hash: str = ""

    metadata: Dict[str, Any] = field(default_factory=dict)

    score: float = 0.0  # Dynamic retrieval score
    base_score: float = 0.0
    type_mask: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.name,
            "content": self.content,
            "timestamp": self.timestamp,
            "score": self.score,
            "importance": self.importance,
            "utility_score": self.utility_score,
            "access_count": self.access_count,
            "last_accessed": self.last_accessed,
            "namespace": self.namespace,
            "source": self.source,
            "active": self.active,
            "status": self.status.name,
            "tier": self.tier.name,
            "priority": self.priority.name,
            "consensus_score": self.consensus_score,
            "confidence_score": self.confidence_score,
            "evidence_count": self.evidence_count,
            "node_ids": self.node_ids,
            "edge_ids": self.edge_ids,
            "provenance": self.provenance,
            "freshness": self.freshness,
            "dependencies": self.dependencies,
            "logical_hash": self.logical_hash,
            "metadata": self.metadata,
        }

    def __repr__(self) -> str:
        preview = self.content[:60] + "..." if len(self.content) > 60 else self.content
        st = f" [{self.status.name}]" if self.status != MemoryStatus.ACTIVE else ""
        return f"Memory({self.type.name}{st}, score={self.score:.3f}, imp={self.importance:.2f}, util={self.utility_score:.2f}, '{preview}')"


@dataclass
class RetrievalExplanation:
    """Breakdown of why a memory was retrieved — for observability."""

    memory_id: str
    final_score: float
    vector_score: float
    keyword_score: float
    recency_score: float
    importance_score: float
    frequency_bonus: float
    query: str
    priority_multiplier: float = 1.0
    mode: str = "default"
    matched_keywords: List[str] = field(default_factory=list)
    confidence_score: float = 0.0
    graph_score: float = 0.0
    personalization_score: float = 0.0

    def explain(self) -> str:
        lines = [
            f"Memory {self.memory_id} — score {self.final_score:.4f} (mode={self.mode})",
            f"  vector similarity:  {self.vector_score:.4f}",
            f"  keyword match:      {self.keyword_score:.4f}  {self.matched_keywords}",
            f"  recency:            {self.recency_score:.4f}",
            f"  importance:         {self.importance_score:.4f}",
            f"  frequency bonus:    {self.frequency_bonus:.4f}",
            f"  confidence:         {self.confidence_score:.4f}",
            f"  graph proximity:    {self.graph_score:.4f}",
            f"  personalization:    {self.personalization_score:.4f}",
            f"  priority multiplier:{self.priority_multiplier:.2f}",
        ]
        return "\n".join(lines)
