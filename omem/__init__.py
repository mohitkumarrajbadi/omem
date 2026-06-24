from importlib.metadata import PackageNotFoundError, version

# Stable v1 API — backwards compatible forever
from .api import OMem
from .core.engine import DreamResult, ForgetResult

# v2 Memory layer (Phase 1 — shipped)
from .memory import MemoryOS, MemoryQuery

# v2 Context layer (Phase 3 — shipped)
from .context import ContextBundle, ContextEngine, ContextRequest

# v2 Knowledge layer (Phase 4 — shipped)
from .knowledge import EdgeRecord, GraphSubgraph, InferenceResult, KnowledgeOS, KnowledgeStats

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

# v2 top-level product facade
from .agent_state import AgentState

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
    # v2 product facade
    "AgentState",
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
