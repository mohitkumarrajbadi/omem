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

    # Usage-based utility (issue 0001). Heuristic importance is only the prior.
    initial_importance: float = 0.5
    retrieved_count: int = 0
    packed_count: int = 0
    cited_count: int = 0

    # Bi-temporal belief window. None valid_to = still current.
    valid_from: Optional[float] = None
    valid_to: Optional[float] = None

    _RUNTIME_META_KEY = "_omem_runtime"

    def metadata_for_persist(self) -> Dict[str, Any]:
        """Metadata blob written to backends, including runtime fields."""
        meta = dict(self.metadata or {})
        meta[self._RUNTIME_META_KEY] = {
            "type_confidence": self.type_confidence,
            "initial_importance": self.initial_importance,
            "packed_count": self.packed_count,
            "cited_count": self.cited_count,
            "retrieved_count": self.retrieved_count,
            "valid_from": self.valid_from,
            "valid_to": self.valid_to,
            "lifecycle_stage": self.lifecycle_stage,
            "level": self.level,
            "superseded_by": self.superseded_by,
            "tier": self.tier.name if hasattr(self.tier, "name") else str(self.tier),
            "priority": self.priority.name if hasattr(self.priority, "name") else str(self.priority),
        }
        return meta

    def hydrate_runtime_fields(self) -> "Memory":
        """Restore runtime fields packed into ``metadata`` by backends."""
        rt = (self.metadata or {}).get(self._RUNTIME_META_KEY) or {}
        if rt:
            self.type_confidence = float(rt.get("type_confidence", self.type_confidence))
            self.initial_importance = float(rt.get("initial_importance", self.importance))
            self.packed_count = int(rt.get("packed_count", 0))
            self.cited_count = int(rt.get("cited_count", 0))
            self.retrieved_count = int(rt.get("retrieved_count", self.access_count))
            vf = rt.get("valid_from")
            vt = rt.get("valid_to")
            self.valid_from = float(vf) if vf is not None else self.timestamp
            self.valid_to = float(vt) if vt is not None else None
            if rt.get("lifecycle_stage"):
                self.lifecycle_stage = rt["lifecycle_stage"]
            if rt.get("level"):
                self.level = rt["level"]
            if rt.get("superseded_by") is not None:
                self.superseded_by = rt["superseded_by"]
            # Keep public metadata equal to what the caller stored.
            self.metadata = dict(self.metadata)
            self.metadata.pop(self._RUNTIME_META_KEY, None)
        else:
            if self.valid_from is None:
                self.valid_from = self.timestamp
            if not self.initial_importance:
                self.initial_importance = self.importance
        return self

    def is_current(self, now: Optional[float] = None) -> bool:
        """True when this belief is still valid at ``now``."""
        t = now if now is not None else time.time()
        if self.valid_to is not None and self.valid_to <= t:
            return False
        if self.valid_from is not None and self.valid_from > t:
            return False
        return True

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
            "initial_importance": self.initial_importance,
            "retrieved_count": self.retrieved_count,
            "packed_count": self.packed_count,
            "cited_count": self.cited_count,
            "valid_from": self.valid_from,
            "valid_to": self.valid_to,
            "superseded_by": self.superseded_by,
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


# ---------------------------------------------------------------------------
# OMem v1 — Run / RunEvent (durable history + live cursor dual-write)
# See: yc-w27-materials/OMEM_V1_ENGINEERING_SPEC.md §0A, §4
# ---------------------------------------------------------------------------

# Closed core vocabulary. Namespaced ``custom.<name>`` is also accepted by the writer.
RUN_EVENT_TYPES = frozenset({
    "run_started",
    "user_message",
    "model_decision",
    "tool_call",
    "tool_result",
    "observation",
    "state_mutation",
    "memory_write",
    "checkpoint",
    "approval_requested",
    "approval_granted",
    "run_crashed",
    "run_resumed",
    "run_completed",
    "fork_created",
})

RUN_STATUSES = frozenset({
    "running",
    "paused",
    "failed",
    "crashed",
    "done",
})


def is_valid_run_event_type(event_type: str) -> bool:
    """True for core types or safe ``custom.<name>`` extensions."""
    if event_type in RUN_EVENT_TYPES:
        return True
    if event_type.startswith("custom.") and len(event_type) > 7:
        rest = event_type[7:]
        return rest.replace("_", "").replace("-", "").isalnum()
    return False


@dataclass
class Run:
    """One execution within a Thread (``session_id``).

    Live cursor remains ``StatePayload`` / checkpoints (Mode A resume).
    ``run_events`` are the append-only history / audit SoT.
    """

    run_id: str
    session_id: str
    namespace: str = "default"
    agent_id: Optional[str] = None
    status: str = "running"  # running | paused | failed | crashed | done
    parent_run_id: Optional[str] = None
    fork_checkpoint_id: Optional[str] = None
    fork_seq: Optional[int] = None
    label: Optional[str] = None
    goal: Optional[str] = None
    lease_owner: Optional[str] = None
    lease_until: Optional[float] = None
    heartbeat_ms: int = 30000
    needs_reconcile: bool = False
    last_checkpoint_id: Optional[str] = None
    last_event_seq: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "session_id": self.session_id,
            "namespace": self.namespace,
            "agent_id": self.agent_id,
            "status": self.status,
            "parent_run_id": self.parent_run_id,
            "fork_checkpoint_id": self.fork_checkpoint_id,
            "fork_seq": self.fork_seq,
            "label": self.label,
            "goal": self.goal,
            "lease_owner": self.lease_owner,
            "lease_until": self.lease_until,
            "heartbeat_ms": self.heartbeat_ms,
            "needs_reconcile": self.needs_reconcile,
            "last_checkpoint_id": self.last_checkpoint_id,
            "last_event_seq": self.last_event_seq,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Run":
        return cls(
            run_id=d["run_id"],
            session_id=d["session_id"],
            namespace=d.get("namespace", "default"),
            agent_id=d.get("agent_id"),
            status=d.get("status", "running"),
            parent_run_id=d.get("parent_run_id"),
            fork_checkpoint_id=d.get("fork_checkpoint_id"),
            fork_seq=d.get("fork_seq"),
            label=d.get("label"),
            goal=d.get("goal"),
            lease_owner=d.get("lease_owner"),
            lease_until=d.get("lease_until"),
            heartbeat_ms=int(d.get("heartbeat_ms", 30000)),
            needs_reconcile=bool(d.get("needs_reconcile", False)),
            last_checkpoint_id=d.get("last_checkpoint_id"),
            last_event_seq=int(d.get("last_event_seq", 0)),
            created_at=float(d.get("created_at", time.time())),
            updated_at=float(d.get("updated_at", time.time())),
        )


@dataclass
class RunEvent:
    """Append-only durable execution / audit event (history SoT)."""

    event_id: str
    run_id: str
    sequence: int
    type: str
    actor: str = "agent"  # user | agent | system | human
    timestamp: float = field(default_factory=time.time)
    causation_id: Optional[str] = None
    correlation_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    payload: Dict[str, Any] = field(default_factory=dict)
    payload_ref: Optional[str] = None
    schema_version: int = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "run_id": self.run_id,
            "sequence": self.sequence,
            "type": self.type,
            "actor": self.actor,
            "timestamp": self.timestamp,
            "causation_id": self.causation_id,
            "correlation_id": self.correlation_id,
            "idempotency_key": self.idempotency_key,
            "payload": self.payload,
            "payload_ref": self.payload_ref,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RunEvent":
        return cls(
            event_id=d["event_id"],
            run_id=d["run_id"],
            sequence=int(d["sequence"]),
            type=d["type"],
            actor=d.get("actor", "agent"),
            timestamp=float(d.get("timestamp", time.time())),
            causation_id=d.get("causation_id"),
            correlation_id=d.get("correlation_id"),
            idempotency_key=d.get("idempotency_key"),
            payload=dict(d.get("payload") or {}),
            payload_ref=d.get("payload_ref"),
            schema_version=int(d.get("schema_version", 1)),
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
