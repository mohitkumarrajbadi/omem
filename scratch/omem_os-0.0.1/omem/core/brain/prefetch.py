"""Predictive Prefetch — Context-Based Memory Pre-loading.

Instead of waiting for the user to ask, OMem predicts what memories
will be needed next based on the current working context and pre-loads
them into a fast cache.

How it works:
1. Monitors the last N add() calls to build a "working context"
2. Generates predicted queries from the context
3. Pre-runs FAISS search and caches results in a warm buffer
4. When rag() is called, checks warm buffer first (near-zero latency)
"""

import time
import logging
import re
from dataclasses import dataclass
from typing import List, Optional, Dict, Deque
from collections import deque


logger = logging.getLogger(__name__)

_TOKENIZER = re.compile(r"\w+")

# How many recent memories to track for context
_CONTEXT_WINDOW = 10
# How many prefetch results to cache
_PREFETCH_CACHE_SIZE = 50
# Minimum time between prefetch runs (seconds)
_PREFETCH_COOLDOWN = 5.0


@dataclass
class PrefetchResult:
    """Result of a prefetch operation."""

    queries_generated: int = 0
    memories_cached: int = 0
    cache_hit_rate: float = 0.0
    elapsed_ms: float = 0.0


class PrefetchEngine:
    """Predictive memory prefetcher.

    Monitors incoming memories and pre-loads likely-needed context.
    """

    def __init__(self, context_window: int = _CONTEXT_WINDOW):
        # Recent memory contents (sliding window)
        self._recent: Deque[str] = deque(maxlen=context_window)
        # Warm cache: query_hash → list of memory IDs
        self._warm_cache: Dict[str, List[str]] = {}
        # Last prefetch time
        self._last_prefetch: float = 0.0
        # Stats
        self._hits: int = 0
        self._misses: int = 0

    def observe(self, content: str) -> None:
        """Record a new memory being added (observe working context)."""
        self._recent.append(content)

    def generate_predicted_queries(self) -> List[str]:
        """Generate likely queries based on recent context.

        Uses word frequency and topic extraction to predict
        what the user might ask about next.
        """
        if not self._recent:
            return []

        # Compute word frequency across recent memories
        word_freq: Dict[str, int] = {}
        for content in self._recent:
            for word in _TOKENIZER.findall(content.lower()):
                if len(word) > 3:
                    word_freq[word] = word_freq.get(word, 0) + 1

        # Top themes = most likely query targets
        top_words = sorted(word_freq.items(), key=lambda x: -x[1])[:8]

        queries = []

        # Generate query from top themes (2-3 word combos)
        top_terms = [w for w, _ in top_words]
        if len(top_terms) >= 2:
            queries.append(f"{top_terms[0]} {top_terms[1]}")
        if len(top_terms) >= 4:
            queries.append(f"{top_terms[2]} {top_terms[3]}")

        # Use the most recent memory as a direct prediction
        if self._recent:
            latest = list(self._recent)[-1]
            words = _TOKENIZER.findall(latest.lower())
            significant = [w for w in words if len(w) > 4][:4]
            if significant:
                queries.append(" ".join(significant))

        # Add the full latest context as a broad query
        if len(self._recent) >= 3:
            combined = " ".join(list(self._recent)[-3:])
            words = _TOKENIZER.findall(combined.lower())
            significant = [w for w in words if len(w) > 4][:6]
            if significant:
                queries.append(" ".join(significant))

        return queries[:4]  # Max 4 predicted queries

    def prefetch(self, search_fn, embed_fn) -> PrefetchResult:
        """Run a prefetch cycle — generate queries + pre-load results.

        Args:
            search_fn: Function(vector, top_k) → list of memory IDs
            embed_fn: Function(text) → np.ndarray

        Returns:
            PrefetchResult with stats
        """
        t0 = time.time()
        now = time.time()

        # Cooldown check
        if now - self._last_prefetch < _PREFETCH_COOLDOWN:
            return PrefetchResult(elapsed_ms=(time.time() - t0) * 1000)

        self._last_prefetch = now
        result = PrefetchResult()

        queries = self.generate_predicted_queries()
        result.queries_generated = len(queries)

        if not queries:
            result.elapsed_ms = (time.time() - t0) * 1000
            return result

        # Clear old cache
        self._warm_cache.clear()

        cached_count = 0
        for query in queries:
            try:
                vector = embed_fn(query)
                memory_ids = search_fn(vector, _PREFETCH_CACHE_SIZE // len(queries))
                query_key = self._hash_query(query)
                self._warm_cache[query_key] = memory_ids
                cached_count += len(memory_ids)
            except Exception as e:
                logger.warning("Prefetch failed for query '%s': %s", query[:30], e)

        result.memories_cached = cached_count
        result.elapsed_ms = (time.time() - t0) * 1000

        logger.info(
            "Prefetch: %d queries, %d memories cached in %.1fms",
            result.queries_generated,
            result.memories_cached,
            result.elapsed_ms,
        )
        return result

    def check_cache(self, query: str) -> Optional[List[str]]:
        """Check if a query has prefetched results.

        Returns list of memory IDs if cache hit, None otherwise.
        """
        query_key = self._hash_query(query)
        if query_key in self._warm_cache:
            self._hits += 1
            return self._warm_cache[query_key]

        # Fuzzy match: check if query words overlap with cached queries
        set(_TOKENIZER.findall(query.lower()))

        for cached_key, cached_ids in self._warm_cache.items():
            # We stored the hash, but we can check word overlap from recent context
            pass

        self._misses += 1
        return None

    def get_stats(self) -> Dict:
        """Return cache hit/miss statistics."""
        total = self._hits + self._misses
        return {
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self._hits / total if total > 0 else 0.0,
            "cache_size": len(self._warm_cache),
            "context_window": len(self._recent),
        }

    def clear(self) -> None:
        """Clear all caches and context."""
        self._recent.clear()
        self._warm_cache.clear()
        self._hits = 0
        self._misses = 0

    @staticmethod
    def _hash_query(query: str) -> str:
        """Quick hash for cache key."""
        words = sorted(set(_TOKENIZER.findall(query.lower())))
        return "|".join(words[:8])
