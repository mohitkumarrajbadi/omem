"""Memory type definitions and core data structures."""

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import numpy as np


class MemoryType(Enum):
    """Categories of memory stored in the system.

    Types are soft hints for ranking and extraction — not hard retention gates.
    See ``type_confidence`` on ``Memory``. Charter cognitive objects map as:

    - WorkingMemory → WORKING
    - EpisodicMemory → EPISODIC
    - SemanticMemory → SEMANTIC
    - DecisionMemory → DECISION
    - ToolMemory → TOOL
    - SkillMemory → SKILL (PROCEDURAL kept for how-to steps)
    - StateMemory → StateOS (not a MemoryType)
    """

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
    TOOL = 10  # Tool invocation traces / tool I/O
    SKILL = 11  # Reusable learned workflows / skills


# Number of MemoryType values — keep Rust type_boost arrays in sync
MEMORY_TYPE_COUNT = len(MemoryType)


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


class LifecycleStage(Enum):
    """Memory lifecycle along the Memory OS charter continuum."""

    NEW = "new"
    REINFORCED = "reinforced"
    CONSOLIDATED = "consolidated"
    COMPRESSED = "compressed"
    ARCHIVED = "archived"
    FORGOTTEN = "forgotten"


class MemoryLevel(Enum):
    """Hierarchy level for tier-targeted retrieval (CPU-style memory hierarchy).

    Charter L0–L4 aliases resolve via ``resolve_hierarchy_level``:

    - L0 Working → working
    - L1 Episodic → short_term
    - L2 Semantic → long_term (facts / decisions)
    - L3 Skill → long_term (skills / procedural)
    - L4 Archive → archive
    """

    WORKING = "working"
    SHORT_TERM = "short_term"
    LONG_TERM = "long_term"
    ARCHIVE = "archive"


# Charter L0–L4 → internal MemoryLevel.value
HIERARCHY_ALIASES: Dict[str, str] = {
    "l0": MemoryLevel.WORKING.value,
    "L0": MemoryLevel.WORKING.value,
    "working": MemoryLevel.WORKING.value,
    "l1": MemoryLevel.SHORT_TERM.value,
    "L1": MemoryLevel.SHORT_TERM.value,
    "episodic": MemoryLevel.SHORT_TERM.value,
    "short_term": MemoryLevel.SHORT_TERM.value,
    "l2": MemoryLevel.LONG_TERM.value,
    "L2": MemoryLevel.LONG_TERM.value,
    "semantic": MemoryLevel.LONG_TERM.value,
    "l3": MemoryLevel.LONG_TERM.value,
    "L3": MemoryLevel.LONG_TERM.value,
    "skill": MemoryLevel.LONG_TERM.value,
    "long_term": MemoryLevel.LONG_TERM.value,
    "l4": MemoryLevel.ARCHIVE.value,
    "L4": MemoryLevel.ARCHIVE.value,
    "archive": MemoryLevel.ARCHIVE.value,
}


def resolve_hierarchy_level(level: Optional[str]) -> Optional[str]:
    """Normalize charter L0–L4 or legacy level names to MemoryLevel values."""
    if level is None:
        return None
    key = level.strip()
    if key in HIERARCHY_ALIASES:
        return HIERARCHY_ALIASES[key]
    lowered = key.lower()
    return HIERARCHY_ALIASES.get(lowered, lowered)


# Maps hierarchy level → allowed MemoryTier values for filtering
LEVEL_TIER_MAP: Dict[str, List["MemoryTier"]] = {
    MemoryLevel.WORKING.value: [MemoryTier.SENSORY, MemoryTier.ACTIVE],
    MemoryLevel.SHORT_TERM.value: [MemoryTier.ACTIVE],
    MemoryLevel.LONG_TERM.value: [MemoryTier.ACTIVE, MemoryTier.CORE, MemoryTier.INSIGHT],
    MemoryLevel.ARCHIVE.value: [MemoryTier.ARCHIVE],
}


def level_matches(level: str, tier: MemoryTier) -> bool:
    """Return True if a memory's tier belongs to the requested hierarchy level."""
    resolved = resolve_hierarchy_level(level) or level
    allowed = LEVEL_TIER_MAP.get(resolved, [MemoryTier.ACTIVE])
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
    # Soft-hint confidence for primary MemoryType (0–1). Does not hard-gate recall.
    type_confidence: float = 1.0
    # Lifecycle stage along new → reinforced → … → forgotten
    lifecycle_stage: str = LifecycleStage.NEW.value
    # Outcome / goal signals for cognitive scoring (0–1)
    success_score: float = 0.0
    goal_alignment: float = 0.0
    # Cold L4 object-storage pointer (S3-compatible key); content may be stubbed
    cold_storage_key: Optional[str] = None

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
            "level": self.level,
            "consensus_score": self.consensus_score,
            "confidence_score": self.confidence_score,
            "type_confidence": self.type_confidence,
            "lifecycle_stage": self.lifecycle_stage,
            "success_score": self.success_score,
            "goal_alignment": self.goal_alignment,
            "cold_storage_key": self.cold_storage_key,
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


# ---------------------------------------------------------------------------
# State layer types (Phase 2)
# ---------------------------------------------------------------------------


@dataclass
class ToolResult:
    """A single tool invocation result recorded in session state."""

    tool: str
    input: Dict[str, Any]
    output: Any
    timestamp: float = field(default_factory=time.time)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool": self.tool,
            "input": self.input,
            "output": self.output,
            "timestamp": self.timestamp,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ToolResult":
        return cls(
            tool=d["tool"],
            input=d.get("input", {}),
            output=d.get("output"),
            timestamp=d.get("timestamp", time.time()),
            error=d.get("error"),
        )


@dataclass
class StatePayload:
    """Full execution state of an agent session.

    Stores everything an agent needs to continue after a restart, rollback,
    or branch: goal, plan, current step, recent tool outputs, and arbitrary
    workflow state.
    """

    session_id: str
    goal: Optional[str] = None
    plan: List[str] = field(default_factory=list)
    step: int = 0
    status: str = "idle"  # idle | running | paused | failed | done
    workflow_state: Dict[str, Any] = field(default_factory=dict)
    tool_outputs: List[ToolResult] = field(default_factory=list)
    agent_metadata: Dict[str, Any] = field(default_factory=dict)
    namespace: str = "default"
    updated_at: float = field(default_factory=time.time)
    version: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "goal": self.goal,
            "plan": self.plan,
            "step": self.step,
            "status": self.status,
            "workflow_state": self.workflow_state,
            "tool_outputs": [t.to_dict() for t in self.tool_outputs],
            "agent_metadata": self.agent_metadata,
            "namespace": self.namespace,
            "updated_at": self.updated_at,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "StatePayload":
        return cls(
            session_id=d["session_id"],
            goal=d.get("goal"),
            plan=d.get("plan", []),
            step=d.get("step", 0),
            status=d.get("status", "idle"),
            workflow_state=d.get("workflow_state", {}),
            tool_outputs=[ToolResult.from_dict(t) for t in d.get("tool_outputs", [])],
            agent_metadata=d.get("agent_metadata", {}),
            namespace=d.get("namespace", "default"),
            updated_at=d.get("updated_at", time.time()),
            version=d.get("version", 1),
        )


@dataclass
class StateSnapshot:
    """Immutable point-in-time copy of a session's state.

    Snapshots are append-only. Rolling back to a snapshot never deletes
    other snapshots — it only updates the live session record.
    """

    id: str
    session_id: str
    payload: StatePayload
    label: Optional[str] = None
    parent_id: Optional[str] = None   # set when this snapshot is forked from another
    memory_snapshot_ref: Optional[str] = None
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "payload": self.payload.to_dict(),
            "label": self.label,
            "parent_id": self.parent_id,
            "memory_snapshot_ref": self.memory_snapshot_ref,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "StateSnapshot":
        return cls(
            id=d["id"],
            session_id=d["session_id"],
            payload=StatePayload.from_dict(d["payload"]),
            label=d.get("label"),
            parent_id=d.get("parent_id"),
            memory_snapshot_ref=d.get("memory_snapshot_ref"),
            created_at=d.get("created_at", time.time()),
        )


@dataclass
class StateCheckpoint:
    """Lightweight crash-recovery marker.

    Checkpoints are cheaper than full snapshots: they store the payload
    as-is without branching logic or labels. Agents write checkpoints
    frequently (e.g. after every tool call); they write snapshots when
    they want a named, fork-able save point.
    """

    id: str
    session_id: str
    payload_hash: str
    payload: StatePayload
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "payload_hash": self.payload_hash,
            "payload": self.payload.to_dict(),
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "StateCheckpoint":
        return cls(
            id=d["id"],
            session_id=d["session_id"],
            payload_hash=d["payload_hash"],
            payload=StatePayload.from_dict(d["payload"]),
            created_at=d.get("created_at", time.time()),
        )


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
    success_score: float = 0.0
    goal_alignment_score: float = 0.0
    retrieval_reason: str = ""
    contributing_factors: List[str] = field(default_factory=list)
    lookup_kind: str = "hybrid"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "final_score": self.final_score,
            "score_breakdown": {
                "semantic": self.vector_score,
                "keyword": self.keyword_score,
                "recency": self.recency_score,
                "importance": self.importance_score,
                "confidence": self.confidence_score,
                "graph": self.graph_score,
                "personalization": self.personalization_score,
                "frequency": self.frequency_bonus,
                "success": self.success_score,
                "goal": self.goal_alignment_score,
            },
            "retrieval_reason": self.retrieval_reason
            or f"hybrid fusion (mode={self.mode})",
            "contributing_factors": self.contributing_factors,
            "lookup_kind": self.lookup_kind,
            "mode": self.mode,
            "matched_keywords": self.matched_keywords,
        }

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
            f"  success:            {self.success_score:.4f}",
            f"  goal alignment:     {self.goal_alignment_score:.4f}",
            f"  priority multiplier:{self.priority_multiplier:.2f}",
        ]
        if self.retrieval_reason:
            lines.append(f"  reason:             {self.retrieval_reason}")
        if self.contributing_factors:
            lines.append(f"  factors:            {', '.join(self.contributing_factors)}")
        return "\n".join(lines)
