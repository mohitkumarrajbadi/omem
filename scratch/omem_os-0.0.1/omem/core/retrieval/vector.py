"""FAISS-backed vector index for nearest-neighbour search."""

import logging
from typing import Tuple

import faiss
import numpy as np

from ..utils.concurrency import RWLock, ReadContext, WriteContext

logger = logging.getLogger(__name__)


class VectorIndex:
    """Thread-safe wrapper around a FAISS ``IndexHNSWFlat`` (inner-product / cosine).

    Vectors **must** be L2-normalised before insertion so that inner-product
    equals cosine similarity.  All operations are guarded by a ``threading.Lock``
    because FAISS indexes are **not** thread-safe for concurrent add+search.
    """

    def __init__(self, dim: int = 384, ef_search: int = 64, m: int = 32):
        self.dim = dim
        self.index = faiss.IndexHNSWFlat(dim, m, faiss.METRIC_INNER_PRODUCT)
        self.index.hnsw.efSearch = ef_search
        self.index.hnsw.efConstruction = 40  # faster inserts, good quality
        self._lock = RWLock()

    @property
    def size(self) -> int:
        with ReadContext(self._lock):
            return self.index.ntotal

    def add(self, vector: np.ndarray) -> None:
        """Add a single vector ``(dim,)`` or batch ``(N, dim)``."""
        vec = np.ascontiguousarray(vector, dtype=np.float32)
        if vec.ndim == 1:
            vec = vec.reshape(1, -1)
        with WriteContext(self._lock):
            self.index.add(vec)

    def search(
        self, query: np.ndarray, top_k: int = 5
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Return ``(scores, indices)`` arrays of shape ``(top_k,)``.

        Automatically adjusts efSearch based on index size for optimal
        speed/quality tradeoff.
        """
        q = np.ascontiguousarray(query, dtype=np.float32).reshape(1, -1)
        with ReadContext(self._lock):
            n = self.index.ntotal
            k = min(top_k, n) if n > 0 else 0
            if k == 0:
                return np.array([], dtype=np.float32), np.array([], dtype=np.int64)
            # Adaptive efSearch: more memories = higher quality scan needed
            if n < 1_000:
                self.index.hnsw.efSearch = 32
            elif n < 10_000:
                self.index.hnsw.efSearch = 64
            else:
                self.index.hnsw.efSearch = 128
            scores, indices = self.index.search(q, k)
        return scores[0], indices[0]

    def reset(self) -> None:
        """Remove all vectors."""
        with WriteContext(self._lock):
            self.index.reset()

    def rebuild(self, vectors: np.ndarray) -> None:
        """Rebuild the index from a new set of vectors.

        Args:
            vectors: (N, dim) array of L2-normalized vectors.
        """
        vec = np.ascontiguousarray(vectors, dtype=np.float32)
        with WriteContext(self._lock):
            self.index.reset()
            if len(vec) > 0:
                self.index.add(vec)
        logger.info("Vector index rebuilt with %d vectors", len(vec))
