"""V2 memory layer facade.

This package is the first v2 namespace. It wraps the stable ``OMem`` API with
memory-native verbs while preserving the existing engine, storage, and tests.
"""

from .layer import MemoryOS, MemoryQuery

__all__ = ["MemoryOS", "MemoryQuery"]
