"""Engine Mixin: Retrieval Pipeline."""

import heapq
import time
from typing import Dict, List, Optional

import numpy as np

from ...types import Memory, MemoryTier, level_matches, resolve_hierarchy_level
from ..retrieval.fusion import FusionWeights
from ..retrieval.ranker import (
    apply_reinforcement,
    compute_signals,
    rank_memories,
    score_candidate,
    weights_for_mode,
)
from ..utils.concurrency import ReadContext
from .utils import _HAS_RUST

try:
    import omem_rust
except ImportError:
    pass

from ..utils.structured_logging import get_logger

logger = get_logger(__name__)

from .utils import _W_IMPORTANCE, _W_KEYWORD, _W_RECENCY, _W_VECTOR  # noqa: E402


def _passes_tier_filter(
    mem: Memory,
    tiers: Optional[List[MemoryTier]] = None,
    level: Optional[str] = None,
    include_archive: bool = False,
) -> bool:
    """Filter memories by tier enum and/or hierarchy level."""
    level = resolve_hierarchy_level(level) if level else level
    if mem.tier == MemoryTier.FORGOTTEN:
        return False
    if mem.tier == MemoryTier.ARCHIVE and not include_archive and level != "archive":
        return False
    if tiers and mem.tier not in tiers:
        return False
    if level:
        if level == "working":
            return mem.level == "working"
        if level == "short_term":
            return mem.level in ("working", "short_term")
        if level == "long_term":
            return mem.level == "long_term" or mem.tier in (
                MemoryTier.CORE,
                MemoryTier.INSIGHT,
            )
        if level == "archive":
            return mem.tier == MemoryTier.ARCHIVE
        return level_matches(level, mem.tier)
    if mem.tier in (MemoryTier.ARCHIVE, MemoryTier.FORGOTTEN) and not include_archive:
        return False
    return True


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
        fusion_weights: Optional[FusionWeights] = None,
        tiers: Optional[List[MemoryTier]] = None,
        level: Optional[str] = None,
        include_archive: bool = False,
    ) -> List[Memory]:
        if mode == "strong":
            return self._rag_strong(
                query,
                top_k=top_k,
                namespace=namespace,
                include_inactive=include_inactive,
            )

        query_key = f"{query}:{namespace}:{mode}:{top_k}:{level}"
        cached = self.working_memory.get(query_key)
        if cached and not explain:
            return cached

        query_vec = self.embedder.encode(query)
        if self.kv.size == 0:
            # Cold engine or post-restart pool entry — reload from durable store.
            # Must happen *before* taking the read lock: reload_from_backend()
            # acquires the write lock internally, and this RWLock is not
            # reentrant, so calling it while holding the read lock deadlocks.
            self.reload_from_backend()
        with ReadContext(self._lock):
            if self.kv.size == 0:
                self._last_explanations = []
                return []
            f_top_k = min(top_k * 10, self.kv.size, 200)
            scores, indices = self.vector_index.search(query_vec, top_k=f_top_k)
            id_snap = list(self._id_order)

        now = time.time()
        weights = fusion_weights or weights_for_mode(
            mode, weight_overrides, getattr(self, "_fusion_weights", None)
        )
        kg = getattr(self, "knowledge_graph", None)
        query_entities = (
            [e.name for e in kg.find_entities_in_query(query)] if kg else []
        )

        vector_scores: Dict[str, float] = {}
        candidate_mems: List[Memory] = []

        for idx, vec_score in zip(indices, scores):
            idx = int(idx)
            if idx < 0 or idx >= len(id_snap):
                continue
            mem = self.kv.get(id_snap[idx])
            if mem is None or (not include_inactive and not mem.active):
                continue
            if not _passes_tier_filter(mem, tiers, level, include_archive):
                continue
            if namespace and mem.namespace != namespace:
                continue
            vector_scores[mem.id] = float(vec_score)
            candidate_mems.append(mem)

        if _HAS_RUST and candidate_mems and type_boosts:
            results = self._rag_rust_path(
                query,
                query_vec,
                candidate_mems,
                type_boosts,
                top_k,
                now,
                weights,
                kg,
                query_entities,
            )
        else:
            results, explanations = rank_memories(
                candidate_mems,
                query,
                vector_scores,
                now,
                top_k=len(candidate_mems),
                mode=mode,
                knowledge_graph=kg,
                weights=weights,
            )
            if explain:
                self._last_explanations = explanations
            results = heapq.nlargest(top_k, results, key=lambda m: m.score)

        if graph_boost > 0.0 and kg and results:
            results = self._expand_graph_neighbors(
                query,
                results,
                query_entities,
                namespace,
                top_k,
                graph_boost,
                weights,
                tiers,
                level,
                include_archive,
            )

        final_results = self._finalize_results(
            query,
            results,
            top_k,
            quality_threshold,
            context_budget_chars,
            now,
            explain,
            mode,
            weights,
            vector_scores,
        )
        self.working_memory.put(query_key, final_results)
        return final_results

    def _rag_rust_path(
        self,
        query: str,
        query_vec,
        candidate_mems,
        type_boosts,
        top_k,
        now,
        weights,
        kg,
        query_entities,
    ) -> List[Memory]:
        """Rust-accelerated path: prep signals in Python, rank via rag_fuse_batch."""
        from ...types import MEMORY_TYPE_COUNT, MemoryType
        from ..brain.importance import _RECENCY_HALF_LIFE

        n = len(candidate_mems)
        semantics = np.zeros(n, dtype=np.float32)
        keywords = np.zeros(n, dtype=np.float32)
        recencies = np.zeros(n, dtype=np.float32)
        importances = np.zeros(n, dtype=np.float32)
        confidences = np.zeros(n, dtype=np.float32)
        graphs = np.zeros(n, dtype=np.float32)
        personalizations = np.zeros(n, dtype=np.float32)
        successes = np.zeros(n, dtype=np.float32)
        goals = np.zeros(n, dtype=np.float32)
        m_types = np.zeros(n, dtype=np.uint8)

        boosts = np.ones(MEMORY_TYPE_COUNT, dtype=np.float32)
        for t_name, b in (type_boosts or {}).items():
            try:
                t_enum = (
                    MemoryType[t_name.upper()]
                    if isinstance(t_name, str)
                    else t_name
                )
                if 0 <= t_enum.value < MEMORY_TYPE_COUNT:
                    boosts[t_enum.value] = b
            except (KeyError, AttributeError):
                pass

        signal_list = []
        from ..retrieval.bm25 import keyword_bm25_blend

        overlaps = []
        query_tokens = set()
        try:
            from .utils import _TOKENIZER

            query_tokens = set(_TOKENIZER.findall(query.lower()))
        except Exception:
            pass
        for mem in candidate_mems:
            from ..retrieval.ranker import compute_keyword_score

            ov, _ = compute_keyword_score(query_tokens, mem)
            overlaps.append(ov)
        kw_blend = keyword_bm25_blend(
            [m.content for m in candidate_mems], query, overlaps
        )

        for i, mem in enumerate(candidate_mems):
            # Semantic via vector dot with query
            try:
                semantics[i] = float(np.dot(query_vec, mem.vector))
            except Exception:
                semantics[i] = 0.0
            sig = compute_signals(
                mem,
                query,
                float(semantics[i]),
                now,
                kg,
                query_entities,
                keyword_override=kw_blend[i] if i < len(kw_blend) else None,
            )
            signal_list.append(sig)
            keywords[i] = sig.keyword
            recencies[i] = sig.recency
            importances[i] = sig.importance
            confidences[i] = sig.confidence
            graphs[i] = sig.graph_combined
            personalizations[i] = sig.personalization
            successes[i] = sig.success
            goals[i] = sig.goal
            m_types[i] = mem.type.value if hasattr(mem.type, "value") else 0

        weight_vec = (
            weights.as_weight_vector()
            if hasattr(weights, "as_weight_vector")
            else [_W_VECTOR, _W_KEYWORD, _W_RECENCY, _W_IMPORTANCE, 0.08, 0.10, 0.07, 0.05, 0.05]
        )

        if hasattr(omem_rust, "rag_fuse_batch"):
            scored_indices = omem_rust.rag_fuse_batch(
                semantics,
                keywords,
                recencies,
                importances,
                confidences,
                graphs,
                personalizations,
                successes,
                goals,
                m_types,
                weight_vec,
                boosts,
                top_k * 2,
            )
            results = []
            for i_in_batch, rust_score in scored_indices:
                mem = candidate_mems[i_in_batch]
                mem.score = float(rust_score)
                # Keep frequency/status multipliers from Python for parity
                sig = signal_list[i_in_batch]
                if sig.status_multiplier == 0.0:
                    mem.score = 0.0
                else:
                    mem.score = float(
                        (rust_score + sig.frequency * 0.10) * sig.status_multiplier
                    )
                results.append(mem)
            return results

        # Fallback: legacy rag_score_batch + Python rescore
        v_vecs, b_scores, rec = [], [], []
        for mem in candidate_mems:
            age = max(now - mem.timestamp, 0.0)
            v_vecs.append(mem.vector)
            b_scores.append(mem.base_score)
            rec.append(2.0 ** (-age / _RECENCY_HALF_LIFE))

        scored_indices = omem_rust.rag_score_batch(
            query_vec.astype(np.float32),
            np.array(v_vecs, dtype=np.float32),
            np.array(b_scores, dtype=np.float32),
            np.array(rec, dtype=np.float32),
            m_types,
            [_W_VECTOR, _W_IMPORTANCE, _W_RECENCY, _W_KEYWORD],
            boosts,
            top_k * 2,
        )

        results = []
        for i_in_batch, rust_score in scored_indices:
            mem = candidate_mems[i_in_batch]
            vs = float(rust_score)
            signals = compute_signals(mem, query, vs, now, kg, query_entities)
            mem.score = score_candidate(signals, weights)
            results.append(mem)
        return results

    def _expand_graph_neighbors(
        self,
        query: str,
        top_results,
        query_entities,
        namespace,
        top_k,
        graph_boost,
        weights,
        tiers,
        level,
        include_archive,
    ):
        kg = self.knowledge_graph
        already_seen = {m.id for m in top_results}
        graph_candidates: List[Memory] = []
        seed_entity_names = list(query_entities)
        for mem in top_results:
            seed_entity_names.extend(getattr(mem, "entities", []))

        for entity_name in seed_entity_names:
            for mid in kg.get_related_memory_ids(entity_name, depth=1):
                if mid in already_seen:
                    continue
                neighbor = self.kv.get(mid)
                if neighbor is None or not neighbor.active:
                    continue
                if namespace and neighbor.namespace != namespace:
                    continue
                if not _passes_tier_filter(neighbor, tiers, level, include_archive):
                    continue
                signals = compute_signals(
                    neighbor, query, neighbor.importance, time.time(), kg, seed_entity_names
                )
                neighbor.score = score_candidate(signals, weights) * graph_boost
                graph_candidates.append(neighbor)
                already_seen.add(mid)

        if graph_candidates:
            merged = top_results + graph_candidates
            return heapq.nlargest(top_k, merged, key=lambda m: m.score)
        return top_results

    def _finalize_results(
        self,
        query: str,
        top_results,
        top_k,
        quality_threshold,
        context_budget_chars,
        now,
        explain,
        mode: str = "default",
        weights: Optional[FusionWeights] = None,
        vector_scores: Optional[Dict[str, float]] = None,
    ):
        final_results = []
        total_chars = 0
        kg = getattr(self, "knowledge_graph", None)
        vscores = vector_scores or {}

        for r in top_results[: top_k * 2]:
            if r.score < quality_threshold:
                continue
            if context_budget_chars is not None:
                if total_chars + len(r.content) > context_budget_chars:
                    break
            final_results.append(r)
            total_chars += len(r.content)
            if len(final_results) >= top_k:
                break

        for r in final_results:
            apply_reinforcement([r], now)
            self.kv.set(r.id, r)
            if hasattr(self, "write_buffer"):
                self.write_buffer.enqueue(r)

        if explain and final_results:
            _, explanations = rank_memories(
                final_results,
                query,
                vscores,
                now,
                top_k=len(final_results),
                mode=mode,
                knowledge_graph=kg,
                weights=weights,
            )
            self._last_explanations = explanations
        elif not explain:
            self._last_explanations = []

        return final_results

    def get_last_explanations(self) -> List:
        """Return explanations from the most recent explain=True retrieval."""
        return getattr(self, "_last_explanations", [])

    def set_fusion_weights(self, weights: FusionWeights) -> None:
        """Set default fusion weights for retrieval."""
        self._fusion_weights = weights

    def get_fusion_weights(self) -> FusionWeights:
        """Return current default fusion weights."""
        return getattr(self, "_fusion_weights", weights_for_mode("default"))

    def _rag_strong(
        self,
        query: str,
        *,
        top_k: int = 5,
        namespace: Optional[str] = None,
        include_inactive: bool = False,
    ) -> List[Memory]:
        """DB-authoritative recall via pgvector — read-your-writes consistency."""
        backend = getattr(self, "backend", None)
        if backend is None or not hasattr(backend, "vector_search"):
            return self.rag(
                query,
                top_k=top_k,
                namespace=namespace,
                include_inactive=include_inactive,
                mode="default",
            )

        query_vec = self.embedder.encode(query)
        model = getattr(self.embedder, "_model_name", None)
        pairs = backend.vector_search(
            query_vec,
            namespace=namespace,
            top_k=top_k,
            embedding_model=model,
        )
        if not pairs:
            return self.rag(
                query,
                top_k=top_k,
                namespace=namespace,
                include_inactive=include_inactive,
                mode="recall",
            )
        results: List[Memory] = []
        for mem, sim in pairs:
            if not include_inactive and not mem.active:
                continue
            mem.score = float(sim)
            results.append(mem)
            if len(results) >= top_k:
                break
        return results
