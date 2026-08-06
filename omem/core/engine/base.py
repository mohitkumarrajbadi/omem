"""OMem Engine Base — BrainTrace core orchestration."""

import time
from typing import Callable, Dict, List, Optional

from ...types import Memory, MemoryTier
from ..brain.compression import run_compression
from ..brain.forgetting import restore_memory
from ..brain.prefetch import PrefetchEngine
from ..brain.quotas import MemoryQuota
from ..brain.reflection import (
    reflect_on_conflicts,
    reflect_on_conversation,
    reflect_on_memories,
)
from ..brain.tms import ConflictResolver
from ..graph.causal import CausalGraph
from ..graph.dependency import DependencyGraph
from ..graph.knowledge import KnowledgeGraph
from ..retrieval.embeddings import Embedder
from ..retrieval.fusion import DEFAULT_WEIGHTS
from ..retrieval.kv import KVCache
from ..retrieval.vector import VectorIndex
from ..utils.cache import LRUCache
from ..utils.concurrency import RWLock, ReadContext, WriteContext
from ..utils.inspector import inspect_query
from ..utils.structured_logging import get_logger
from ..utils.write_buffer import WriteBuffer
from .add import AddMixin
from .lifecycle import LifecycleMixin
from .maintenance import MaintenanceEngine
from .rag import RAGMixin

logger = get_logger(__name__)


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
        self._fusion_weights = DEFAULT_WEIGHTS
        self._start_time = time.time()

        self._load_from_backend()

    def _load_from_backend(self) -> int:
        """Load existing memories from backend into KV cache and vector index."""
        if not self.backend or not hasattr(self.backend, "all"):
            return 0

        try:
            stored_memories = self.backend.all()
            if not stored_memories:
                return 0

            import numpy as np

            vectors = []
            for mem in stored_memories:
                self.kv.set(mem.id, mem)
                self._id_order.append(mem.id)
                vectors.append(mem.vector)

            if vectors:
                vectors_array = np.array(vectors, dtype=np.float32)
                self.vector_index.rebuild(vectors_array)
            return len(stored_memories)
        except Exception as exc:
            logger.error(
                "Failed to load memories from backend — engine starts empty. Error: %s",
                exc,
                exc_info=True,
            )
            return 0

    def reload_from_backend(self) -> int:
        """Re-hydrate the in-memory index from the durable backend.

        Used after API restarts or when a pooled engine was warmed before writes
        landed in Postgres. Returns the number of memories loaded.
        """
        if not self.backend or not hasattr(self.backend, "all"):
            return 0

        try:
            stored_memories = self.backend.all()
            if not stored_memories:
                return 0

            import numpy as np

            with WriteContext(self._lock):
                self.kv.clear()
                self._id_order.clear()
                vectors = []
                for mem in stored_memories:
                    self.kv.set(mem.id, mem)
                    self._id_order.append(mem.id)
                    vectors.append(mem.vector)
                if vectors:
                    vectors_array = np.array(vectors, dtype=np.float32)
                    self.vector_index.rebuild(vectors_array)
                else:
                    self.vector_index.rebuild(
                        __import__("numpy").empty((0, self.embedder.dim), dtype="float32")
                    )
            return len(stored_memories)
        except Exception as exc:
            logger.error("Failed to reload memories from backend: %s", exc, exc_info=True)
            return 0

    def __del__(self):
        """Ensure write buffer is flushed before destruction."""
        if hasattr(self, "write_buffer"):
            self.write_buffer.flush()

    def consolidate(self, llm_fn: Optional[Callable] = None) -> Dict:
        """Deep maintenance: resolve conflicts and hierarchical reflection."""
        # Snapshot current memories under the read lock, then release before
        # calling self.add() / self.reflect() — both internally acquire the
        # write lock, so holding it here would deadlock.
        with ReadContext(self._lock):
            mems = list(self.kv.all())

        # 1. Resolve conflicts using LLM if available (pure computation, no lock)
        resolutions = reflect_on_conflicts(mems, summarizer=llm_fn)

        # 2. Persist resolutions — each add() acquires the write lock itself
        for res in resolutions:
            self.add(
                res.content,
                mem_type=res.type,
                importance=res.importance,
                source="consolidator",
            )

        # 3. Hierarchical reflection — reflect() also calls add() internally
        insights = self.reflect(summarizer=llm_fn, namespace=None)

        # 4. Rebuild vector index from current active vectors (acquires its own lock)
        with ReadContext(self._lock):
            active_vecs = [m.vector for m in self.kv.all() if m.vector is not None]
        if active_vecs:
            import numpy as np
            self.vector_index.rebuild(np.stack(active_vecs).astype(np.float32))

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
        return [m for mid in m_ids if (m := self.kv.get(mid)) is not None]

    def query_graph(self, entity_name: str, depth: int = 2) -> Dict:
        """Structured graph query with nodes, edges, and related memory IDs."""
        from ..brain.reasoning import query_graph_substrate

        return query_graph_substrate(self.knowledge_graph, entity_name, depth=depth)

    def link_entities(
        self,
        source: str,
        target: str,
        relation: str = "related_to",
        memory_id: str = "",
        confidence: float = 1.0,
    ) -> str:
        from ..graph.knowledge import EdgeType

        edge_type = EdgeType(relation) if relation in EdgeType._value2member_map_ else EdgeType.RELATED_TO
        return self.knowledge_graph.link_entities(
            source, target, edge_type, memory_id=memory_id, confidence=confidence
        )

    def assert_fact(
        self,
        subject: str,
        relation: str,
        obj: str,
        memory_id: str = "",
        confidence: float = 0.9,
    ) -> Dict:
        from ..graph.knowledge import EdgeType

        if not memory_id:
            memory_id = self.add(f"{subject} {relation} {obj}", source="assertion")
        edge_type = EdgeType(relation) if relation in EdgeType._value2member_map_ else EdgeType.ASSERTED
        return self.knowledge_graph.assert_fact(
            subject, edge_type, obj, memory_id, confidence=confidence
        )

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
        self,
        query: str,
        top_k: int = 5,
        namespace: Optional[str] = None,
        mode: str = "default",
        weight_overrides: Optional[Dict] = None,
    ) -> List:
        """Explain why certain memories were retrieved for a query."""
        mems = self.kv.all()
        if namespace:
            mems = [m for m in mems if m.namespace == namespace]

        query_vec = self.embedder.encode(query)
        scores, indices = self.vector_index.search(query_vec, top_k=min(len(mems), 100))

        id_snap = list(self._id_order)
        vector_scores = {}
        for idx, s in zip(indices, scores):
            if 0 <= int(idx) < len(id_snap):
                vector_scores[id_snap[int(idx)]] = float(s)

        return inspect_query(
            query,
            mems,
            vector_scores,
            top_k=top_k,
            mode=mode,
            knowledge_graph=self.knowledge_graph,
            weight_overrides=weight_overrides,
        )

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
        from ..brain.self_tune import normalize_weights, tune_weights_from_feedback

        with WriteContext(self._lock):
            for mid in memory_ids:
                mem = self.kv.get(mid)
                if mem:
                    adjustment = 0.1 * max(min(score, 1.0), -1.0)
                    mem.utility_score = max(
                        min(mem.utility_score + adjustment, 1.0), 0.0
                    )
                    self.kv.put(mid, mem)
                    self.write_buffer.enqueue(mem)

            self._fusion_weights = normalize_weights(
                tune_weights_from_feedback(self._fusion_weights, score)
            )
        logger.info(
            "Feedback applied to %d memories (score=%.2f)", len(memory_ids), score
        )

    def __repr__(self) -> str:
        s = self.stats()
        return f"BrainTrace(total={s['total']}, inactive={s['inactive']}, ns={len(s['namespaces'])})"
