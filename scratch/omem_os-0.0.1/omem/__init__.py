from .types import (
    Memory,
    MemoryType,
    MemoryTier,
    MemoryPriority,
    MemoryStatus,
    RetrievalExplanation,
)
from .api import OMem
from .core.engine import ForgetResult, DreamResult

from importlib.metadata import version, PackageNotFoundError

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
