"""Engine Mixin: Retrieval Pipeline."""

import heapq
import logging
import time
from typing import Dict, List, Optional

import numpy as np

from ...types import Memory, MemoryTier
from ..brain.importance import (
    _FREQUENCY_LOG_BASE,
    _MAX_FREQUENCY_BONUS,
    _RECENCY_HALF_LIFE,
)
from ..utils.concurrency import ReadContext
from .utils import _HAS_RUST, _TOKENIZER, _token_hash, fast_intersect

try:
    import omem_rust
except ImportError:
    pass

logger = logging.getLogger(__name__)

# Mode profiles
from .utils import _W_FREQUENCY, _W_IMPORTANCE, _W_KEYWORD, _W_RECENCY, _W_VECTOR  # noqa: E402


class RAGMixin:
    """Methods for memory retrieval and ranking."""

    def rag(
        self,
        query: str,
        top_k: int = 5,
        namespace: Optional[str] = None,
        include_inactive: bool = False,
        mode: str = "default",
        type_boosts: Optional[Dict] = None,
        weight_overrides: Optional[Dict] = None,
        explain: bool = False,
        quality_threshold: float = 0.0,
        context_budget_chars: Optional[int] = None,
        graph_boost: float = 0.6,
    ) -> List[Memory]:
        query_key = f"{query}:{namespace}:{mode}:{top_k}"
        cached = self.working_memory.get(query_key)
        if cached:
            return cached

        query_vec = self.embedder.encode(query)
        with ReadContext(self._lock):
            if self.kv.size == 0:
                return []
            f_top_k = min(top_k * 10, self.kv.size, 200)
            scores, indices = self.vector_index.search(query_vec, top_k=f_top_k)
            id_snap = list(self._id_order)

        now = time.time()
        query_tokens = set(_TOKENIZER.findall(query.lower()))
        q_hashes = np.sort(
            np.array([_token_hash(t) for t in query_tokens], dtype=np.uint64)
        )
        q_len = max(len(query_tokens), 1)

        results: List[Memory] = []
        if _HAS_RUST:
            # RUST ACCELERATED PATH
            candidate_mems, v_vecs, b_scores, recencies = [], [], [], []
            for idx, _ in zip(indices, scores):
                idx = int(idx)
                if idx < 0 or idx >= len(id_snap):
                    continue
                mem = self.kv.get(id_snap[idx])
                if mem is None or (not include_inactive and not mem.active):
                    continue
                if mem.tier in (MemoryTier.ARCHIVE, MemoryTier.FORGOTTEN):
                    continue
                if namespace and mem.namespace != namespace:
                    continue

                age = max(now - mem.timestamp, 0.0)
                candidate_mems.append(mem)
                v_vecs.append(mem.vector)
                b_scores.append(mem.base_score)
                recencies.append(2.0 ** (-age / _RECENCY_HALF_LIFE))

            if candidate_mems:
                from ...types import MemoryType

                m_types = np.array(
                    [
                        m.type.value if hasattr(m.type, "value") else 0
                        for m in candidate_mems
                    ],
                    dtype=np.uint8,
                )
                boosts = np.ones(10, dtype=np.float32)
                if type_boosts:
                    for t_name, b in type_boosts.items():
                        try:
                            t_enum = (
                                MemoryType[t_name.upper()]
                                if isinstance(t_name, str)
                                else t_name
                            )
                            boosts[t_enum.value] = b
                        except (KeyError, AttributeError):
                            pass

                # SIMD Scoring (v0.6.0: 8-arg signature with 10-slot boosts)
                scored_indices = omem_rust.rag_score_batch(
                    query_vec.astype(np.float32),
                    np.array(v_vecs, dtype=np.float32),
                    np.array(b_scores, dtype=np.float32),
                    np.array(recencies, dtype=np.float32),
                    m_types,
                    [_W_VECTOR, _W_IMPORTANCE, _W_RECENCY, _W_KEYWORD],
                    boosts,
                    top_k,
                )
                for i_in_batch, s in scored_indices:
                    mem = candidate_mems[i_in_batch]
                    mem.score = float(s)
                    results.append(mem)
        else:
            # PYTHON OPTIMIZED PATH (Refactored logic from engine.py 0.6.0)
            for idx, vec_score in zip(indices, scores):
                idx = int(idx)
                if idx < 0 or idx >= len(id_snap):
                    continue
                mem = self.kv.get(id_snap[idx])
                if mem is None or (not include_inactive and not mem.active):
                    continue
                if mem.tier in (MemoryTier.ARCHIVE, MemoryTier.FORGOTTEN):
                    continue
                if namespace and mem.namespace != namespace:
                    continue

                overlap = fast_intersect(q_hashes, mem.token_hashes)
                kw_score = min(overlap / q_len, 1.0)
                age = max(now - mem.timestamp, 0.0)
                recency = 2.0 ** (-age / _RECENCY_HALF_LIFE)
                freq = min(
                    np.log1p(mem.access_count) / np.log(_FREQUENCY_LOG_BASE),
                    _MAX_FREQUENCY_BONUS,
                )

                from ...types import MemoryStatus

                status_mult = 1.0
                if mem.status == MemoryStatus.CONFLICTED:
                    status_mult = 0.3  # Heavy penalty for unresolved contradictions
                elif mem.status == MemoryStatus.DEPRECATED:
                    continue  # Skip deprecated facts

                final_score = (
                    vec_score * _W_VECTOR
                    + kw_score * _W_KEYWORD
                    + recency * _W_RECENCY
                    + freq * _W_FREQUENCY
                    + mem.base_score * _W_IMPORTANCE
                ) * status_mult
                mem.score = float(final_score)
                results.append(mem)

        top_results = heapq.nlargest(top_k, results, key=lambda m: m.score)

        # ── Graph-RAG Expansion (v1.0) ──
        # After vector scoring, expand via the knowledge graph.
        # For each top result's named entities, fetch graph-neighbor memories
        # and add them to the candidate pool at a discounted score.
        # This surfaces related memories that pure vector search would miss.
        if graph_boost > 0.0 and hasattr(self, "knowledge_graph") and top_results:
            already_seen = {m.id for m in top_results}
            graph_candidates: List[Memory] = []

            # Also check entities mentioned directly in the query
            query_entities = self.knowledge_graph.find_entities_in_query(query)
            seed_entity_names = [e.name for e in query_entities]

            # Add entities from top results
            for mem in top_results:
                seed_entity_names.extend(getattr(mem, "entities", []))

            for entity_name in seed_entity_names:
                neighbor_ids = self.knowledge_graph.get_related_memory_ids(
                    entity_name, depth=1
                )
                for mid in neighbor_ids:
                    if mid in already_seen:
                        continue
                    neighbor = self.kv.get(mid)
                    if neighbor is None or not neighbor.active:
                        continue
                    if namespace and neighbor.namespace != namespace:
                        continue
                    if neighbor.tier in (MemoryTier.ARCHIVE, MemoryTier.FORGOTTEN):
                        continue
                    # Discount the score: graph neighbors are relevant but less certain
                    neighbor.score = (
                        neighbor.score * graph_boost
                        if neighbor.score > 0
                        else (neighbor.importance * graph_boost)
                    )
                    graph_candidates.append(neighbor)
                    already_seen.add(mid)

            # Merge: top vector results + graph neighbors, re-rank, take top_k
            if graph_candidates:
                merged = top_results + graph_candidates
                top_results = heapq.nlargest(top_k, merged, key=lambda m: m.score)

        # Apply quality threshold and context budget
        final_results = []
        total_chars = 0

        for r in top_results:
            if r.score < quality_threshold:
                continue

            if context_budget_chars is not None:
                if total_chars + len(r.content) > context_budget_chars:
                    if not final_results:
                        pass
                    break

            final_results.append(r)
            total_chars += len(r.content)
            r.access_count += 1
            r.last_accessed = now
            self.kv.set(r.id, r)
            if hasattr(self, "write_buffer"):
                self.write_buffer.enqueue(r)

        self.working_memory.put(query_key, final_results)
        return final_results
