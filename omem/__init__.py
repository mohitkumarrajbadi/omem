"""OMem — governed memory and state for AI agents.

Partner entry point: ``AgentState``. Layer packages remain importable
from their submodules (``omem.memory``, ``omem.state``, …).
"""

from importlib.metadata import PackageNotFoundError, version

from .agent_config import AgentConfig
from .agent_state import AgentState, ExplanationReport
from .api import OMem
from .core.engine import DreamResult, ForgetResult
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
