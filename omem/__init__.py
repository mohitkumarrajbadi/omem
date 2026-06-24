from importlib.metadata import PackageNotFoundError, version

# Stable v1 API — backwards compatible forever
from .api import OMem
from .core.engine import DreamResult, ForgetResult

# v2 Memory layer (shipped)
from .memory import MemoryOS, MemoryQuery

# v2 top-level product facade (Phase 5 — layers are stubs until each phase ships)
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
    # v2 memory layer
    "MemoryOS",
    "MemoryQuery",
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
