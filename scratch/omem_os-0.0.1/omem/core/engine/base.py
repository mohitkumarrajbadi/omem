"""OMem Engine Base — BrainTrace core orchestration."""

import time
import logging
from typing import List, Optional, Dict, Callable

from ...types import Memory, MemoryTier
from ..retrieval.embeddings import Embedder
from ..retrieval.vector import VectorIndex
from ..retrieval.kv import KVCache
from ..graph.causal import CausalGraph
from ..graph.knowledge import KnowledgeGraph
from ..utils.concurrency import RWLock, WriteContext
from ..utils.cache import LRUCache
from ..utils.write_buffer import WriteBuffer

from ..brain.quotas import MemoryQuota
from ..brain.prefetch import PrefetchEngine
from ..brain.forgetting import restore_memory
from ..brain.compression import run_compression
from ..brain.reflection import (
    reflect_on_memories,
    reflect_on_conversation,
    reflect_on_conflicts,
)
from ..brain.tms import ConflictResolver
from ..graph.dependency import DependencyGraph
from ..utils.inspector import inspect_query
from .maintenance import MaintenanceEngine

from .add import AddMixin
from .rag import RAGMixin
from .lifecycle import LifecycleMixin

logger = logging.getLogger(__name__)


class BrainTrace(AddMixin, RAGMixin, LifecycleMixin):
    """Core Memory Operating System engine (Modular Version)."""

    def __init__(
        self,
        backend: Optional[object] = None,
        model_name: str = "all-MiniLM-L6-v2",
        embedding_provider: str = "local",
    ):
        self.embedder = Embedder(model_name, provider=embedding_provider)
        self.vector_index = VectorIndex(dim=self.embedder.dim)
        self.kv = KVCache()
        self.graph = CausalGraph()
        self.knowledge_graph = KnowledgeGraph()
        self.dependency_graph = DependencyGraph()
        self.prefetcher = PrefetchEngine()
        self.quota = MemoryQuota()
        self.backend = backend
        self.write_buffer = WriteBuffer(backend=backend)
        self.write_buffer.start()
        self._lock = RWLock()
        self.working_memory = LRUCache(capacity=100)
        self.maintenance = MaintenanceEngine(self)
        self.tms = ConflictResolver(
            self.backend, kv=self.kv, dependency_graph=self.dependency_graph
        )
        self._id_order: List[str] = []
        self._noise_gate_enabled = True
        self._dedup_enabled = True
        self._start_time = time.time()

        self._load_from_backend()

    def _load_from_backend(self):
        """Load existing memories from backend into KV cache and vector index."""
        if not self.backend or not hasattr(self.backend, "all"):
            return

        try:
            stored_memories = self.backend.all()
            if not stored_memories:
                return

            import numpy as np

            vectors = []
            for mem in stored_memories:
                self.kv.set(mem.id, mem)
                self._id_order.append(mem.id)
                vectors.append(mem.vector)

            if vectors:
                vectors_array = np.array(vectors, dtype=np.float32)
                self.vector_index.rebuild(vectors_array)
        except Exception:
            pass

    def __del__(self):
        """Ensure write buffer is flushed before destruction."""
        if hasattr(self, "write_buffer"):
            self.write_buffer.flush()

    def consolidate(self, llm_fn: Optional[Callable] = None) -> Dict:
        """Deep maintenance: resolve conflicts and hierarchical reflection."""
        with WriteContext(self._lock):
            mems = self.kv.all()

            # 1. Resolve conflicts using LLM if available
            resolutions = reflect_on_conflicts(mems, summarizer=llm_fn)
            for res in resolutions:
                self.add(
                    res.content,
                    mem_type=res.type,
                    importance=res.importance,
                    source="consolidator",
                )

            # 2. Hierarchical reflection
            insights = self.reflect(summarizer=llm_fn, namespace=None)

            # 3. Optimize vector index
            self.vector_index.rebuild()

            return {
                "conflicts_resolved": len(resolutions),
                "new_insights": len(insights),
            }

    def link(self, src_id: str, dst_id: str, weight: float = 1.0, label: str = ""):
        self.graph.add_link(src_id, dst_id, weight=weight, label=label)

    def entities(self) -> List[Dict]:
        """Return all entities in the knowledge graph as dicts."""
        raw = self.knowledge_graph.all_entities()
        return [
            {
                "name": e.name,
                "type": e.type.value,
                "mentions": e.mention_count,
                "memory_ids": e.memory_ids,
            }
            for e in raw
        ]

    def graph_query(self, entity_name: str, depth: int = 2) -> List[Memory]:
        m_ids = self.knowledge_graph.query(entity_name, depth=depth)
        return [self.kv.get(mid) for mid in m_ids if self.kv.get(mid)]

    def prefetch(self) -> Dict:
        return self.prefetcher.get_predicted_queries()

    def archived(self, namespace: Optional[str] = None) -> List[Memory]:
        mems = self.kv.all()
        if namespace:
            mems = [m for m in mems if m.namespace == namespace]
        return [m for m in mems if m.tier == MemoryTier.ARCHIVE]

    def restore_memory(self, memory_id: str) -> bool:
        return restore_memory(self.kv.all(), memory_id)

    def inspect(
        self, query: str, top_k: int = 5, namespace: Optional[str] = None
    ) -> List:
        """Explain why certain memories were retrieved for a query."""
        mems = self.kv.all()
        if namespace:
            mems = [m for m in mems if m.namespace == namespace]

        # We need vector scores for inspection.
        # For simplicity in modular version, we re-run a search or use cached if available.
        query_vec = self.embedder.encode(query)
        scores, indices = self.vector_index.search(query_vec, top_k=min(len(mems), 100))

        id_snap = list(self._id_order)
        vector_scores = {}
        for idx, s in zip(indices, scores):
            if 0 <= int(idx) < len(id_snap):
                vector_scores[id_snap[int(idx)]] = float(s)

        return inspect_query(query, mems, vector_scores, top_k=top_k)

    def compress(
        self,
        threshold: float = 0.75,
        namespace: Optional[str] = None,
        min_cluster_size: int = 2,
        summarizer: Optional[Callable] = None,
    ) -> Dict:
        """Cluster and merge redundant memories."""
        with WriteContext(self._lock):
            mems = self.kv.all()
            if namespace:
                mems = [m for m in mems if m.namespace == namespace]
            new_mems, deactivated_ids = run_compression(
                mems, threshold, min_cluster_size, summarizer
            )
            for m in new_mems:
                self.kv.put(m.id, m)
                self.vector_index.add(m.vector)
                self._id_order.append(m.id)
            return {"compressed": len(new_mems), "deactivated": len(deactivated_ids)}

    def reflect(
        self,
        threshold: float = 0.65,
        namespace: Optional[str] = None,
        summarizer: Optional[Callable] = None,
    ) -> List[Memory]:
        """Generate high-order insights from current memories."""
        mems = self.kv.all()
        if namespace:
            mems = [m for m in mems if m.namespace == namespace]
        new_insights = reflect_on_memories(
            mems, embedder=self.embedder, summarizer=summarizer, threshold=threshold
        )
        for m in new_insights:
            if namespace:
                m.namespace = namespace
            self.add(
                m.content,
                mem_type=m.type,
                importance=m.importance,
                namespace=m.namespace,
            )
        return new_insights

    def start_maintenance(self, interval: float = 3600.0):
        """Start auto-maintenance loop."""
        self.maintenance.interval = interval
        self.maintenance.start()

    def stop_maintenance(self):
        """Stop auto-maintenance loop."""
        self.maintenance.stop()

    def reflect_conversation(
        self, messages: List[str], summarizer: Optional[Callable] = None
    ) -> Optional[Memory]:
        """Reflect on a conversation to produce a single insight."""
        insight = reflect_on_conversation(
            messages, embedder=self.embedder, summarizer=summarizer
        )
        if insight:
            self.add(
                insight.content, mem_type=insight.type, importance=insight.importance
            )
        return insight

    def feedback(self, memory_ids: List[str], score: float):
        """Update utility scores for a set of memories."""
        with WriteContext(self._lock):
            for mid in memory_ids:
                mem = self.kv.get(mid)
                if mem:
                    # Adaptive feedback: 0.1 increment/decrement per vote
                    # Scaled by the input score (-1 to 1)
                    adjustment = 0.1 * max(min(score, 1.0), -1.0)
                    mem.utility_score = max(
                        min(mem.utility_score + adjustment, 1.0), 0.0
                    )

                    # Update local caches and buffer
                    self.kv.put(mid, mem)
                    self.write_buffer.enqueue(mem)
        logger.info(
            "Feedback applied to %d memories (score=%.2f)", len(memory_ids), score
        )

    def __repr__(self) -> str:
        s = self.stats()
        return f"BrainTrace(total={s['total']}, inactive={s['inactive']}, ns={len(s['namespaces'])})"
