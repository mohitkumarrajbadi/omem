"""Internal engine utilities and constants."""

import re
import numpy as np
from enum import Enum


class RetrievalMode(Enum):
    """Retrieval modes that adjust type filtering and scoring weights."""

    DEFAULT = "default"
    PLANNING = "planning"
    CODING = "coding"
    CHAT = "chat"
    RECALL = "recall"


try:
    import omem_rust  # noqa: F401

    _HAS_RUST = True
except ImportError:
    _HAS_RUST = False

try:
    import xxhash

    def _fast_hash(data: str) -> str:
        return xxhash.xxh64_hexdigest(data.encode("utf-8"))[:12]

    def _token_hash(t: str) -> int:
        return xxhash.xxh64_intdigest(t.encode("utf-8"))
except ImportError:
    import hashlib

    def _fast_hash(data: str) -> str:
        return hashlib.md5(data.encode("utf-8")).hexdigest()[:12]

    def _token_hash(t: str) -> int:
        return int(hashlib.md5(t.encode("utf-8")).hexdigest(), 16) & 0xFFFFFFFFFFFFFFFF


# Pre-compiled tokenizer regex
_TOKENIZER = re.compile(r"\w+")

# ── Hybrid scoring weights (default) ──
_W_VECTOR = 0.35
_W_KEYWORD = 0.15
_W_IMPORTANCE = 0.25
_W_RECENCY = 0.15
_W_FREQUENCY = 0.10

_RECENCY_HALF_LIFE = 3600.0 * 24  # 24h
_DEDUP_THRESHOLD = 0.95


try:
    import numba as _numba

    @_numba.njit(parallel=True, fastmath=True)
    def fast_hybrid_score(
        v_vec: np.ndarray,
        v_imp: np.ndarray,
        v_ts: np.ndarray,
        v_ac: np.ndarray,
        v_kw: np.ndarray,
        now: float,
        w_vector: float,
        w_keyword: float,
        w_importance: float,
        w_recency: float,
        w_frequency: float,
        recency_half_life: float,
        frequency_log_base: float,
        max_frequency_bonus: float,
    ) -> np.ndarray:
        n = v_vec.shape[0]
        out = np.empty(n, dtype=np.float32)
        for i in _numba.prange(n):
            age = max(now - v_ts[i], 0.0)
            recency = 2.0 ** (-age / recency_half_life)
            freq = min(np.log1p(v_ac[i]) / np.log(frequency_log_base), max_frequency_bonus)
            out[i] = (
                w_vector * v_vec[i]
                + w_keyword * v_kw[i]
                + w_importance * v_imp[i]
                + w_recency * recency
                + w_frequency * freq
            )
        return out

    @_numba.njit(fastmath=True)
    def fast_intersect(a: np.ndarray, b: np.ndarray) -> int:
        i, j, count = 0, 0, 0
        na, nb = a.shape[0], b.shape[0]
        while i < na and j < nb:
            if a[i] == b[j]:
                count += 1
                i += 1
                j += 1
            elif a[i] < b[j]:
                i += 1
            else:
                j += 1
        return count

except ImportError:
    # Pure-NumPy fallbacks — same signatures, no JIT overhead
    def fast_hybrid_score(  # type: ignore[misc]
        v_vec: np.ndarray,
        v_imp: np.ndarray,
        v_ts: np.ndarray,
        v_ac: np.ndarray,
        v_kw: np.ndarray,
        now: float,
        w_vector: float,
        w_keyword: float,
        w_importance: float,
        w_recency: float,
        w_frequency: float,
        recency_half_life: float,
        frequency_log_base: float,
        max_frequency_bonus: float,
    ) -> np.ndarray:
        ages = np.maximum(now - v_ts, 0.0)
        recency = np.power(2.0, -ages / recency_half_life)
        freq = np.minimum(
            np.log1p(v_ac) / np.log(frequency_log_base), max_frequency_bonus
        )
        return (
            w_vector * v_vec
            + w_keyword * v_kw
            + w_importance * v_imp
            + w_recency * recency
            + w_frequency * freq
        ).astype(np.float32)

    def fast_intersect(a: np.ndarray, b: np.ndarray) -> int:  # type: ignore[misc]
        """Sorted-array intersection count (pure Python)."""
        i, j, count = 0, 0, 0
        na, nb = len(a), len(b)
        while i < na and j < nb:
            if a[i] == b[j]:
                count += 1
                i += 1
                j += 1
            elif a[i] < b[j]:
                i += 1
            else:
                j += 1
        return count
