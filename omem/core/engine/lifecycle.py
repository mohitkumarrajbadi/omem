"""Engine Mixin: Lifecycle Management (Forgetting, Compression, Snapshot)."""

import logging
import re
import time
from typing import Dict, List, Optional

from ...types import Memory, MemoryTier
from ..brain.dream import dream_consolidate
from ..brain.forgetting import forget_sweep
from ..utils.concurrency import WriteContext
from ..utils.metrics import metrics
from ..utils.snapshot import restore, snapshot

logger = logging.getLogger(__name__)

_TOKENIZER = re.compile(r"\w+")

from ..brain.importance import run_decay_sweep  # noqa: E402
from ..brain.updater import create_updated_memory  # noqa: E402


class LifecycleMixin:
    """Methods for memory maintenance and version control."""

    def get(self, memory_id: str) -> Optional[Memory]:
        """Fetch a single memory by ID."""
        return self.kv.get(memory_id)

    def update(
        self, memory_id: str, new_content: str, merge: bool = False
    ) -> Optional[str]:
        """Update or merge memory content with lineage tracking."""
        old = self.get(memory_id)
        if not old:
            return None

        # v0.6.0: Lineage tracking + updater logic
        new_vec = self.embedder.encode(new_content)
        new_mem = create_updated_memory(old, new_content, new_vec, merge=merge)

        with WriteContext(self._lock):
            self.kv.set(new_mem.id, new_mem)
            self._id_order.append(new_mem.id)
            self.vector_index.add(new_mem.vector)
            old.active = False
            old.superseded_by = new_mem.id

        return new_mem.id

    def delete(self, memory_id: str) -> bool:
        """Soft-delete memory."""
        with WriteContext(self._lock):
            mem = self.kv.get(memory_id)
            if mem:
                mem.active = False
                return True
        return False

    def all_memories(
        self, namespace: Optional[str] = None, include_inactive: bool = False
    ) -> List[Memory]:
        """Return all memories, filtered by namespace."""
        mems = self.kv.all()
        if namespace:
            mems = [m for m in mems if m.namespace == namespace]
        if not include_inactive:
            mems = [m for m in mems if m.active]
        return mems

    def clear(self, namespace: Optional[str] = None):
        """Wipe memory namespace or full engine."""
        with WriteContext(self._lock):
            self.kv.clear(namespace)
            self.working_memory.clear()

    def run_decay(self) -> List[str]:
        """Run expiry sweep."""
        with WriteContext(self._lock):
            mems = self.kv.all()
            deactivated = run_decay_sweep(mems)
            return deactivated

    def forget(self, namespace: Optional[str] = None):
        """Trigger importance-based forgetting sweep."""
        with WriteContext(self._lock):
            mems = self.kv.all()
            if namespace:
                mems = [m for m in mems if m.namespace == namespace]
            result = forget_sweep(mems)
            metrics.increment("memories_forgotten", len(result.deleted))
            return result

    def dream(
        self,
        llm_fn: Optional[callable] = None,
        threshold: float = 0.60,
        min_cluster_size: int = 3,
    ):
        """Trigger background consolidation (Sleep/Dream cycle)."""
        mems = self.kv.all()
        # Ensure we pass the embedder if available
        embedder = getattr(self, "embedder", None)
        wisdom_memories, source_ids, result = dream_consolidate(
            mems,
            embedder=embedder,
            llm_fn=llm_fn,
            threshold=threshold,
            min_cluster_size=min_cluster_size,
        )

        themes_by_insight: Dict[str, List[str]] = {}
        for wisdom in wisdom_memories:
            themes = []
            for word in _TOKENIZER.findall(wisdom.content.lower()):
                if len(word) > 4:
                    themes.append(word)
            themes_by_insight[wisdom.id] = sorted(set(themes))[:5]

        # Add new wisdom memories and archive sources
        for wisdom in wisdom_memories:
            self.kv.set(wisdom.id, wisdom)
            self.vector_index.add(wisdom.vector)
            self._id_order.append(wisdom.id)

            if hasattr(self, "knowledge_graph"):
                themes = themes_by_insight.get(wisdom.id, [])
                node = self.knowledge_graph.create_insight_node(
                    label=wisdom.content[:120],
                    memory_ids=[wisdom.id] + wisdom.insight_sources,
                    themes=themes,
                    confidence=wisdom.confidence_score,
                )
                wisdom.node_ids = [node.id]
                self.kv.set(wisdom.id, wisdom)

        for s_id in source_ids:
            mem = self.kv.get(s_id)
            if mem:
                mem.active = False
                mem.tier = MemoryTier.ARCHIVE

        return result

    def vacuum(self) -> int:
        """Physically remove memories marked as FORGOTTEN from RAM and storage.

        This is the only operation that permanently deletes data.
        Returns the number of memories purged.
        """
        with WriteContext(self._lock):
            mems = self.kv.all()
            to_purge = [m for m in mems if m.tier == MemoryTier.FORGOTTEN]

            for m in to_purge:
                self.kv.delete(m.id)
                if self.backend and hasattr(self.backend, "delete"):
                    try:
                        self.backend.delete(m.id, namespace=m.namespace)
                    except TypeError:
                        self.backend.delete(m.id)

            logger.info("Maintenance vacuumed %d forgotten memories", len(to_purge))
            return len(to_purge)

    def compact_index(self):
        """Rebuild vector index to remove 'holes' and search-space bloat from deleted memories.

        Significantly reduces RAM usage and improves retrieval speed.
        """
        import numpy as np

        with WriteContext(self._lock):
            # 1. Get all active or archived memories (ignore forgotten/deleted)
            # We must maintain a stable order for the index mapping
            all_mems = [
                m for m in self.kv.all() if m.active or m.tier == MemoryTier.ARCHIVE
            ]
            all_mems.sort(key=lambda m: m.timestamp)  # Stable sort

            if not all_mems:
                self.vector_index.reset()
                self._id_order = []
                return

            # 2. Rebuild index
            vectors = np.array([m.vector for m in all_mems], dtype=np.float32)
            self.vector_index.rebuild(vectors)

            # 3. Update ID mapping
            self._id_order = [m.id for m in all_mems]

            logger.info("Maintenance compacted index: %d active vectors", len(all_mems))

    def sleep(
        self,
        speed: str = "normal",
        llm_fn: Optional[callable] = None,
        include_dream: bool = True,
    ) -> dict:
        """Full maintenance cycle: Decay -> Forget -> (Dream) -> Vacuum -> Compact.

        Args:
            speed: 'fast', 'normal', or 'thorough'.
            llm_fn: Optional LLM for consolidation.
            include_dream: Whether to run consolidation (requires CPU/LLM).
        """
        t0 = time.time()

        # 1. Aging and TTL
        deactivated = self.run_decay()

        # 2. Tier scheduling (working → short-term → long-term)
        from ..brain.scheduler import build_centrality_map, schedule_tier_transitions

        centralities = build_centrality_map(getattr(self, "knowledge_graph", None))
        schedule_tier_transitions(self.kv.all(), graph_centralities=centralities)

        # 3. Importance-based forgetting
        f_result = self.forget()

        # 4. Consolidation (Dreaming)
        d_result = None
        if include_dream:
            d_result = self.dream(llm_fn=llm_fn)

        # 5. Physical Purge
        purged = self.vacuum()

        # 6. Index Optimization
        self.compact_index()

        elapsed = (time.time() - t0) * 1000
        logger.info("Sleep cycle complete in %.0fms. Purged: %d.", elapsed, purged)

        return {
            "elapsed_ms": elapsed,
            "deactivated": len(deactivated),
            "archived": len(f_result.archived),
            "deleted": len(f_result.deleted),
            "purged": purged,
            "dream": d_result,
        }

    def snapshot(self, path: str):
        """Save full engine state to a compressed snapshot."""
        return snapshot(self, path)

    def restore(self, path: str):
        """Restore engine state from a snapshot."""
        return restore(self, path)

    def stats(self):
        """Return engine health and performance metrics."""
        mems = self.kv.all()
        namespaces = list(set(m.namespace for m in mems))

        # Calculate type distribution
        type_dist = {}
        for m in mems:
            t_name = m.type.name
            type_dist[t_name] = type_dist.get(t_name, 0) + 1

        avg_imp = sum(m.importance for m in mems) / len(mems) if mems else 0.0

        return {
            "total": len(mems),
            "inactive": len([m for m in mems if not m.active]),
            "kv_size": self.kv.size,
            "vector_index_size": self.vector_index.size,
            "buffer_pending": self.write_buffer.stats.get("pending", 0),
            "namespaces": namespaces,
            "types": type_dist,
            "avg_importance": avg_imp,
            "graph_edges": getattr(self.graph, "num_edges", 0),
            "knowledge_entities": getattr(self.knowledge_graph, "num_entities", 0),
            "knowledge_nodes": len(getattr(self.knowledge_graph, "_nodes", {})),
            "knowledge_edges": getattr(self.knowledge_graph, "num_edges", 0),
            "uptime": time.time() - getattr(self, "_start_time", time.time()),
        }
