from importlib.metadata import PackageNotFoundError, version

from .api import OMem
from .core.engine import DreamResult, ForgetResult
from .types import (
    Memory,
    MemoryPriority,
    MemoryStatus,
    MemoryTier,
    MemoryType,
    RetrievalExplanation,
)

try:
    __version__ = version("omem-os")
except PackageNotFoundError:
    __version__ = "0.0.0+dev"
__all__ = [
    "OMem",
    "MemoryType",
    "MemoryTier",
    "MemoryPriority",
    "MemoryStatus",
    "Memory",
    "RetrievalExplanation",
    "ForgetResult",
    "DreamResult",
    "__version__",
]
