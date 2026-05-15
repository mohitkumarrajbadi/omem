"""Vector index for nearest-neighbour search.

Uses FAISS (IndexHNSWFlat) when available for sub-millisecond ANN search.
Falls back to a pure-NumPy brute-force index so the library works without
any compiled extras.  Install ``pip install omem-os[fast]`` to get FAISS.
"""

import logging
import threading
from typing import Tuple

import numpy as np

from ..utils.concurrency import RWLock, ReadContext, WriteContext

logger = logging.getLogger(__name__)

try:
    import faiss as _faiss
    _HAS_FAISS = True
except ImportError:
    _faiss = None  # type: ignore[assignment]
    _HAS_FAISS = False
    logger.debug(
        "faiss-cpu not installed — using NumPy brute-force vector index. "
        "Install omem-os[fast] for faster ANN search."
    )


class _NumpyVectorIndex:
    """Pure-NumPy brute-force cosine similarity index.

    Vectors must be L2-normalised before insertion (same contract as FAISS
    wrapper below).  O(N·dim) per query — perfectly adequate for <10 k memories.
    """

    def __init__(self, dim: int = 384, **_kwargs):
        self.dim = dim
        self._vectors: list = []          # list of (dim,) float32 arrays
        self._lock = threading.Lock()

    @property
    def ntotal(self) -> int:
        return len(self._vectors)

    def add(self, vec: np.ndarray) -> None:
        v = np.ascontiguousarray(vec, dtype=np.float32)
        if v.ndim == 1:
            v = v.reshape(1, -1)
        with self._lock:
            for row in v:
                self._vectors.append(row.copy())

    def search(self, query: np.ndarray, k: int) -> Tuple[np.ndarray, np.ndarray]:
        with self._lock:
            n = len(self._vectors)
            if n == 0:
                return np.array([], dtype=np.float32), np.array([], dtype=np.int64)
            k = min(k, n)
            mat = np.stack(self._vectors)          # (N, dim)
        q = np.ascontiguousarray(query, dtype=np.float32).reshape(-1)
        scores = mat @ q                            # cosine sim (L2-norm assumed)
        top_idx = np.argpartition(scores, -k)[-k:]
        top_idx = top_idx[np.argsort(scores[top_idx])[::-1]]
        return scores[top_idx], top_idx.astype(np.int64)

    def reset(self) -> None:
        with self._lock:
            self._vectors.clear()


class VectorIndex:
    """Thread-safe vector index — FAISS when available, NumPy otherwise.

    Vectors **must** be L2-normalised before insertion so that inner-product
    equals cosine similarity.
    """

    def __init__(self, dim: int = 384, ef_search: int = 64, m: int = 32):
        self.dim = dim
        self._lock = RWLock()

        if _HAS_FAISS:
            self._index = _faiss.IndexHNSWFlat(dim, m, _faiss.METRIC_INNER_PRODUCT)
            self._index.hnsw.efSearch = ef_search
            self._index.hnsw.efConstruction = 40
            self._backend = "faiss"
        else:
            self._index = _NumpyVectorIndex(dim)
            self._backend = "numpy"

    @property
    def size(self) -> int:
        with ReadContext(self._lock):
            if self._backend == "faiss":
                return self._index.ntotal
            return self._index.ntotal

    def add(self, vector: np.ndarray) -> None:
        """Add a single vector ``(dim,)`` or batch ``(N, dim)``."""
        vec = np.ascontiguousarray(vector, dtype=np.float32)
        if vec.ndim == 1:
            vec = vec.reshape(1, -1)
        with WriteContext(self._lock):
            self._index.add(vec)

    def search(
        self, query: np.ndarray, top_k: int = 5
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Return ``(scores, indices)`` arrays of shape ``(top_k,)``."""
        q = np.ascontiguousarray(query, dtype=np.float32).reshape(1, -1)
        with ReadContext(self._lock):
            if self._backend == "faiss":
                n = self._index.ntotal
                k = min(top_k, n) if n > 0 else 0
                if k == 0:
                    return np.array([], dtype=np.float32), np.array([], dtype=np.int64)
                if n < 1_000:
                    self._index.hnsw.efSearch = 32
                elif n < 10_000:
                    self._index.hnsw.efSearch = 64
                else:
                    self._index.hnsw.efSearch = 128
                scores, indices = self._index.search(q, k)
                return scores[0], indices[0]
            else:
                return self._index.search(q[0], top_k)

    def reset(self) -> None:
        """Remove all vectors."""
        with WriteContext(self._lock):
            self._index.reset()

    def rebuild(self, vectors: np.ndarray) -> None:
        """Rebuild the index from a new set of vectors.

        Args:
            vectors: (N, dim) array of L2-normalized vectors.
        """
        vec = np.ascontiguousarray(vectors, dtype=np.float32)
        with WriteContext(self._lock):
            self._index.reset()
            if len(vec) > 0:
                self._index.add(vec)
        logger.info("Vector index rebuilt with %d vectors (%s backend)", len(vec), self._backend)
