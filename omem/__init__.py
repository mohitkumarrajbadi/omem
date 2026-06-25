from importlib.metadata import PackageNotFoundError, version

# v2 Phase 5 — unified facade + explicit config
from .agent_config import AgentConfig
from .agent_state import AgentState, ExplanationReport

# Stable v1 API — backwards compatible forever
from .api import OMem

# v2 Context layer (Phase 3 — shipped)
from .context import ContextBundle, ContextEngine, ContextRequest
from .core.engine import DreamResult, ForgetResult

# Phase 8: Governance
from .governance import (
    DeletionPolicy,
    DeletionReport,
    GovernanceOS,
    RetentionPolicy,
    RetentionReport,
    Role,
)

# v2 Knowledge layer (Phase 4 — shipped)
from .knowledge import EdgeRecord, GraphSubgraph, InferenceResult, KnowledgeOS, KnowledgeStats

# v2 Memory layer (Phase 1 — shipped)
from .memory import MemoryOS, MemoryQuery

# Phase 6: Observability
from .observe import ObserveOS, TraceEvent

# Phase 10: Org Memory
from .org import NamespaceInfo, NamespaceResolver, OrgMemoryOS, ShareResult

# Phase 7: Provenance
from .provenance import ProvenanceChain, ProvenanceEvent, ProvenanceOS

# Phase 9: Runtime
from .runtime import AgentRegistration, RuntimeOS

# v2 State layer (Phase 2 — shipped)
from .state import (
    InMemoryStateBackend,
    SQLiteStateBackend,
    StateBackend,
    StateCheckpoint,
    StateOS,
    StatePayload,
    StateSnapshot,
    ToolResult,
)
from .types import (
    Evidence,
    GraphNode,
    Memory,
    MemoryLevel,
    MemoryPriority,
    MemoryStatus,
    MemoryTier,
    MemoryType,
    Provenance,
    RelationEdge,
    RetrievalExplanation,
)

try:
    __version__ = version("omem-os")
except PackageNotFoundError:
    __version__ = "0.0.0+dev"

__all__ = [
    # v2 unified facade (Phase 5)
    "AgentState",
    "ExplanationReport",
    "AgentConfig",
    # v2 knowledge layer
    "KnowledgeOS",
    "GraphSubgraph",
    "EdgeRecord",
    "InferenceResult",
    "KnowledgeStats",
    # v2 context layer
    "ContextEngine",
    "ContextRequest",
    "ContextBundle",
    # v2 memory layer
    "MemoryOS",
    "MemoryQuery",
    # v2 state layer
    "StateOS",
    "StatePayload",
    "StateSnapshot",
    "StateCheckpoint",
    "ToolResult",
    "StateBackend",
    "InMemoryStateBackend",
    "SQLiteStateBackend",
    # Phase 6: observability
    "ObserveOS",
    "TraceEvent",
    # Phase 7: provenance
    "ProvenanceOS",
    "ProvenanceEvent",
    "ProvenanceChain",
    # Phase 8: governance
    "GovernanceOS",
    "RetentionPolicy",
    "DeletionPolicy",
    "DeletionReport",
    "RetentionReport",
    "Role",
    # Phase 9: runtime
    "RuntimeOS",
    "AgentRegistration",
    # Phase 10: org memory
    "OrgMemoryOS",
    "NamespaceResolver",
    "NamespaceInfo",
    "ShareResult",
    # v1 stable API
    "OMem",
    # core types
    "MemoryType",
    "MemoryTier",
    "MemoryPriority",
    "MemoryStatus",
    "Memory",
    "MemoryLevel",
    "GraphNode",
    "RelationEdge",
    "Evidence",
    "Provenance",
    "RetrievalExplanation",
    "ForgetResult",
    "DreamResult",
    "__version__",
]
