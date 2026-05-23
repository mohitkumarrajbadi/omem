"""Abstract backend interface for pluggable storage."""

from abc import ABC, abstractmethod
from typing import List, Optional

from ..types import Memory


class Backend(ABC):
    """Base class for all OMem storage backends."""

    @abstractmethod
    def save(self, memory: Memory) -> None:
        """Persist a memory record."""

    @abstractmethod
    def save_batch(self, memories: List[Memory]) -> None:
        """Persist multiple memory records efficiently."""

    @abstractmethod
    def load(self, memory_id: str) -> Optional[Memory]:
        """Load a single memory by ID."""

    @abstractmethod
    def search(self, query: str, limit: int = 10) -> List[Memory]:
        """Keyword search (backend-native, e.g. SQL LIKE)."""

    @abstractmethod
    def all(self) -> List[Memory]:
        """Return every stored memory."""

    @abstractmethod
    def delete(self, memory_id: str) -> bool:
        """Delete a memory by ID. Return True if it existed."""

    @abstractmethod
    def clear(self) -> None:
        """Remove all stored memories."""

    @abstractmethod
    def count(self) -> int:
        """Return total number of stored memories."""
