"""In-memory key-value cache for O(1) memory lookups."""

from typing import Dict, List, Optional

from ...types import Memory


class KVCache:
    """Simple dict-backed KV store for ``Memory`` objects."""

    __slots__ = ("_store",)

    def __init__(self) -> None:
        self._store: Dict[str, Memory] = {}

    @property
    def size(self) -> int:
        return len(self._store)

    def get(self, key: str) -> Optional[Memory]:
        return self._store.get(key)

    def set(self, key: str, memory: Memory) -> None:
        self._store[key] = memory

    def put(self, key: str, memory: Memory) -> None:
        """Alias for set()."""
        self.set(key, memory)

    def delete(self, key: str) -> bool:
        return self._store.pop(key, None) is not None

    def all(self) -> List[Memory]:
        return list(self._store.values())

    def clear(self, namespace: Optional[str] = None) -> None:
        if namespace:
            to_del = [k for k, v in self._store.items() if v.namespace == namespace]
            for k in to_del:
                del self._store[k]
        else:
            self._store.clear()

    def __contains__(self, key: str) -> bool:
        return key in self._store

    def __len__(self) -> int:
        return self.size
