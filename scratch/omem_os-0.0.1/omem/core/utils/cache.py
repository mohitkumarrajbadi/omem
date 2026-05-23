"""Semantic Context Cache for OMem.

Stores recently retrieved contexts to bypass the expensive vector search layer
for repetitive or highly frequent queries.
"""

import hashlib
from typing import List, Optional, Dict, Any


class LRUCache:
    """A simple LRU-style cache for memories and retrieval results."""

    def __init__(self, capacity: int = 100):
        self.capacity = capacity
        self._cache: Dict[str, Any] = {}
        self._access_order: List[str] = []

    def get(self, key: str) -> Optional[Any]:
        """Retrieve cached results for a key."""
        if key in self._cache:
            # Move to end (most recent)
            self._access_order.remove(key)
            self._access_order.append(key)
            return self._cache[key]
        return None

    def put(self, key: str, value: Any):
        """Alias for set()."""
        self.set(key, value)

    def set(self, key: str, value: Any):
        """Cache results."""
        if key in self._cache:
            self._access_order.remove(key)

        self._cache[key] = value
        self._access_order.append(key)

        # Evict old entries
        if len(self._access_order) > self.capacity:
            oldest = self._access_order.pop(0)
            del self._cache[oldest]

    def clear(self):
        """Clear the cache."""
        self._cache.clear()
        self._access_order.clear()

    def _hash_query(self, query: str) -> str:
        """Normalize and hash the query string (utility)."""
        normalized = query.strip().lower()
        return hashlib.md5(normalized.encode()).hexdigest()
