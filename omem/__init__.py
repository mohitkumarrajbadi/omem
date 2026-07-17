from importlib.metadata import PackageNotFoundError, version

from .agent_config import AgentConfig
from .agent_state import AgentState, ExplanationReport
from .api import OMem
from .context import ContextBundle, ContextEngine, ContextRequest
from .core.engine import DreamResult, ForgetResult
from .governance import (
    DeletionPolicy,
    DeletionReport,
    GovernanceOS,
    RetentionPolicy,
    RetentionReport,
    Role,
)
from .knowledge import EdgeRecord, GraphSubgraph, InferenceResult, KnowledgeOS, KnowledgeStats
from .memory import (
    MemoryOS,
    MemoryQuery,
    NamespaceInfo,
    NamespaceResolver,
    OrgMemoryOS,
    ShareResult,
)
from .observe import ObserveOS, TraceEvent
from .provenance import ProvenanceChain, ProvenanceEvent, ProvenanceOS
from .runtime import AgentRegistration, RuntimeOS
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
    LifecycleStage,
    Memory,
    MemoryLevel,
    MemoryPriority,
    MemoryStatus,
    MemoryTier,
    MemoryType,
    Provenance,
    RelationEdge,
    RetrievalExplanation,
    resolve_hierarchy_level,
)

try:
    __version__ = version("omem-os")
except PackageNotFoundError:
    __version__ = "0.0.3+dev"

__all__ = [
    "AgentState",
    "ExplanationReport",
    "AgentConfig",
    "KnowledgeOS",
    "GraphSubgraph",
    "EdgeRecord",
    "InferenceResult",
    "KnowledgeStats",
    "ContextEngine",
    "ContextRequest",
    "ContextBundle",
    "MemoryOS",
    "MemoryQuery",
    "StateOS",
    "StatePayload",
    "StateSnapshot",
    "StateCheckpoint",
    "ToolResult",
    "StateBackend",
    "InMemoryStateBackend",
    "SQLiteStateBackend",
    "ObserveOS",
    "TraceEvent",
    "ProvenanceOS",
    "ProvenanceEvent",
    "ProvenanceChain",
    "GovernanceOS",
    "RetentionPolicy",
    "DeletionPolicy",
    "DeletionReport",
    "RetentionReport",
    "Role",
    "RuntimeOS",
    "AgentRegistration",
    "OrgMemoryOS",
    "NamespaceResolver",
    "NamespaceInfo",
    "ShareResult",
    "OMem",
    "MemoryType",
    "MemoryTier",
    "MemoryPriority",
    "MemoryStatus",
    "Memory",
    "MemoryLevel",
    "LifecycleStage",
    "resolve_hierarchy_level",
    "GraphNode",
    "RelationEdge",
    "Evidence",
    "Provenance",
    "RetrievalExplanation",
    "ForgetResult",
    "DreamResult",
    "__version__",
]
