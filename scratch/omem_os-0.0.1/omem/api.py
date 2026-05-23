"""OMem: A persistent context engine for AI.

Unified interface for managing memory: add, update, rag, compress, and forget.
"""

import logging
from typing import Callable, Dict, List, Optional

from .backends.postgres import PostgresBackend
from .backends.sqlite import SQLiteBackend
from .core.engine import BrainTrace, DreamResult, ForgetResult
from .types import Memory, MemoryType, RetrievalExplanation

logger = logging.getLogger(__name__)


class OMem:
    """Main interface for OMem persistent memory.

    Example:
        from omem import OMem

        m = OMem()
        m.add("User prefers Python", importance=0.9)
        results = m.recall("favorite language")
    """

    def __init__(
        self,
        backend: str = "sqlite",
        db_path: Optional[str] = None,
        model: Optional[str] = None,
        embedding_provider: str = "local",
    ):
        if backend in ("sqlite", "memory", "postgres"):
            import os

            if backend == "postgres":
                self._backend = PostgresBackend(
                    db_path or "postgresql://localhost:5432/omem"
                )
            else:
                if backend == "sqlite" and db_path is None:
                    # Default to centralized storage
                    db_path = os.path.expanduser("~/.omem/brain.db")
                    db_dir = os.path.dirname(db_path)
                    if not os.path.exists(db_dir):
                        os.makedirs(db_dir, exist_ok=True)
                self._backend = SQLiteBackend(db_path or ":memory:")
        else:
            raise ValueError(
                f"Unknown backend '{backend}'. Supported: sqlite, memory, postgres"
            )

        model_name = model or "all-MiniLM-L6-v2"
        self.brain = BrainTrace(
            backend=self._backend,
            model_name=model_name,
            embedding_provider=embedding_provider,
        )
        logger.info(
            "OMem initialized (backend=%s, provider=%s)", backend, embedding_provider
        )

    # Core methods

    def add(
        self,
        content: str,
        mem_type: Optional[MemoryType] = None,
        metadata: Optional[Dict] = None,
        importance: Optional[float] = None,
        namespace: str = "default",
        source: str = "user",
        force: bool = False,
    ) -> str:
        """Store a memory. Auto-classifies type and importance if not supplied."""
        return self.brain.add(
            content,
            mem_type=mem_type,
            metadata=metadata,
            importance=importance,
            namespace=namespace,
            source=source,
            force=force,
        )

    def add_batch(
        self,
        contents: List[str],
        mem_types: Optional[List[MemoryType]] = None,
        namespaces: Optional[List[str]] = None,
        sources: Optional[List[str]] = None,
    ) -> List[str]:
        """High-throughput batch store. Auto-classifies and embeds in bulk."""
        return self.brain.add_batch(
            contents, mem_types=mem_types, namespaces=namespaces, sources=sources
        )

    def update(
        self, memory_id: str, new_content: str, merge: bool = False
    ) -> Optional[str]:
        """Update a memory's content. Returns new memory ID.

        Args:
            memory_id: ID of the memory to update.
            new_content: New content to replace or merge with.
            merge: If True, combines old+new. If False, replaces entirely.
        """
        return self.brain.update(memory_id, new_content, merge=merge)

    def delete(self, memory_id: str) -> bool:
        """Soft-delete a memory (mark as inactive, excluded from RAG)."""
        return self.brain.delete(memory_id)

    # Retrieval

    def recall(
        self,
        query: str,
        k: Optional[int] = None,
        top_k: int = 5,
        context_type: Optional[str] = None,
        mode: Optional[str] = None,
        time_range: Optional[str] = None,
        namespace: Optional[str] = None,
        project_only: bool = False,
    ) -> List[Memory]:
        """Advanced retrieval with context-type boosting and temporal filtering.

        Args:
            query: The search query.
            k: Number of results.
            context_type: One of 'architecture', 'bugs', 'decisions', etc.
            time_range: One of 'today', 'recent', 'last_week'.
            namespace: Specific namespace.
            project_only: If True, only searches the provided namespace (doesn't mix global).
        """
        import time

        now = time.time()

        top_k = k if k is not None else top_k
        context_type = context_type or mode

        # 1. Handle Time Range Filtering
        # Note: Time filtering is done post-retrieval below

        # 2. Handle Context Type Boosting
        # Maps natural-language context_type strings → real MemoryType enum names.
        # Boost=2.5 means this type's memories score 2.5× higher in results.
        type_boosts = {}
        if context_type:
            _CONTEXT_TYPE_MAP = {
                # Decisions & choices
                "decisions": "DECISION",
                "decision": "DECISION",
                # Causal reasoning / root-cause / bugs
                "bugs": "CAUSAL",
                "bug": "CAUSAL",
                "errors": "CAUSAL",
                "root_cause": "CAUSAL",
                "causal": "CAUSAL",
                # Architecture / system knowledge
                "architecture": "SEMANTIC",
                "arch": "SEMANTIC",
                "system": "SEMANTIC",
                "semantic": "SEMANTIC",
                # User preferences / settings
                "preferences": "DECISION",
                "preference": "DECISION",
                "settings": "DECISION",
                # Step-by-step procedures / automations
                "procedures": "PROCEDURAL",
                "procedural": "PROCEDURAL",
                "howto": "PROCEDURAL",
                "actions": "PROCEDURAL",
                # Events / past experiences
                "episodic": "EPISODIC",
                "events": "EPISODIC",
                "history": "EPISODIC",
                # Current tasks / context
                "working": "WORKING",
                "active": "ACTIVE",
                "current": "WORKING",
                # AI-generated insights
                "insights": "INSIGHT",
                "insight": "INSIGHT",
                "reflections": "REFLECTION",
                "reflection": "REFLECTION",
            }
            target = _CONTEXT_TYPE_MAP.get(context_type.lower())
            if target:
                type_boosts[target] = 2.5  # Significant boost for the matched type
            else:
                # Last resort: try direct enum name match (e.g. context_type="SEMANTIC")
                target_upper = context_type.upper()
                from .types import MemoryType

                if target_upper in MemoryType.__members__:
                    type_boosts[target_upper] = 2.5

        # 3. Namespace logic
        search_namespace = namespace
        if not project_only and namespace and namespace != "global":
            # OMem rag currently only takes one namespace.
            # We'll need to call it twice or modify rag to take a list.
            # For now, let's call it once and let the MCP server handle the mix if needed,
            # or just use None to search all if project_only is False.
            if not project_only:
                search_namespace = (
                    None  # Search all, then filter in python? Or just trust rag.
                )

        results = self.brain.rag(
            query, top_k=top_k, namespace=search_namespace, type_boosts=type_boosts
        )

        # Post-filter for namespace if we searched wide
        if not project_only and namespace:
            results = [m for m in results if m.namespace in (namespace, "global")]

        # Post-filter for time_range
        if time_range:
            one_day = 86400
            if time_range == "today":
                results = [m for m in results if now - m.timestamp < one_day]
            elif time_range == "recent":
                results = [m for m in results if now - m.timestamp < one_day * 3]
            elif time_range == "last_week":
                results = [m for m in results if now - m.timestamp < one_day * 7]

        return results[:top_k]

    def get(self, memory_id: str) -> Optional[Memory]:
        """Fetch a single memory by ID."""
        return self.brain.get(memory_id)

    # Maintenance
    # ══════════════════════════════════════════════════════════════

    def compress(
        self,
        threshold: float = 0.75,
        namespace: Optional[str] = None,
        summarizer: Optional[Callable] = None,
    ) -> Dict:
        """Compress similar memories into merged summaries.

        Pass a summarizer function ``f(texts) -> summary`` for LLM-quality compression.
        Without it, uses sentence-level deduplication.
        """
        return self.brain.compress(
            threshold=threshold, namespace=namespace, summarizer=summarizer
        )

    def reflect(
        self,
        threshold: float = 0.65,
        namespace: Optional[str] = None,
        summarizer: Optional[Callable] = None,
    ) -> List[Memory]:
        """Generate reflection insights from accumulated memories.

        Returns a list of new REFLECTION-type memories.
        """
        return self.brain.reflect(
            threshold=threshold, namespace=namespace, summarizer=summarizer
        )

    def reflect_conversation(
        self,
        messages: List[str],
        summarizer: Optional[Callable] = None,
    ) -> Optional[Memory]:
        """Reflect on a conversation to produce a single insight memory."""
        return self.brain.reflect_conversation(messages, summarizer)

    def decay(self) -> List[str]:
        """Run decay sweep — deactivate memories that have expired. Returns deactivated IDs."""
        return self.brain.run_decay()

    def forget(self) -> ForgetResult:
        """Run the forgetting engine to archive or delete low-value memories.

        Returns:
            ForgetResult with a summary of affected items.
        """
        return self.brain.forget()

    def archived(self, namespace: Optional[str] = None) -> List[Memory]:
        """Return archived memories (excluded from RAG, but recoverable)."""
        return self.brain.archived(namespace)

    def restore(self, memory_id: str) -> bool:
        """Restore an archived memory back to ACTIVE tier.

        Returns True if restored, False if not archived.
        """
        return self.brain.restore(memory_id)

    def inspect(
        self,
        query: str,
        top_k: int = 5,
        namespace: Optional[str] = None,
    ) -> List[RetrievalExplanation]:
        """Explain the scoring for a given query."""
        return self.brain.inspect(query, top_k, namespace)

    def namespace_stats(self, namespace: str) -> Dict:
        """Get stats for a specific namespace."""
        mems = self.brain.kv.all()
        mems = [m for m in mems if m.namespace == namespace and m.active]
        return {
            "total": len(mems),
            "types": {
                t.name: sum(1 for m in mems if m.type == t)
                for t in set(m.type for m in mems)
            },
            "avg_importance": sum(m.importance for m in mems) / len(mems)
            if mems
            else 0.0,
        }

    def namespaces(self) -> List[str]:
        """List all active namespaces."""
        return self.brain.stats()["namespaces"]

    def link(
        self, src_id: str, dst_id: str, weight: float = 1.0, label: str = ""
    ) -> None:
        """Link two memories in the knowledge graph."""
        self.brain.link(src_id, dst_id, weight, label)

    # Maintenance and Graph

    def dream(
        self,
        llm_fn: Optional[Callable] = None,
        threshold: float = 0.60,
        min_cluster_size: int = 3,
    ) -> "DreamResult":
        """Consolidate clusters of memories into summarized insights.

        Args:
            llm_fn: Optional LLM function for summarization.
            threshold: Clustering similarity threshold.
            min_cluster_size: Minimum memories to form a cluster.
        """
        return self.brain.dream(
            llm_fn=llm_fn, threshold=threshold, min_cluster_size=min_cluster_size
        )

    def sleep(self, speed: str = "normal", llm_fn: Optional[Callable] = None) -> Dict:
        """Run a full maintenance cycle (Sleep cycle).

        Cleans up dirty data, consolidates memories, and optimizes the index.
        Best run during idle periods or low traffic.
        """
        return self.brain.sleep(speed=speed, llm_fn=llm_fn)

    def auto_maintenance(self, enabled: bool = True, interval: float = 3600.0):
        """Enable or disable background auto-maintenance."""
        if enabled:
            self.brain.start_maintenance(interval=interval)
        else:
            self.brain.stop_maintenance()

    def prefetch(self) -> Dict:
        """Prefetch likely-needed memories based on recent context."""
        return self.brain.prefetch()

    def graph_query(self, entity_name: str, depth: int = 2) -> List[Memory]:
        """Search the knowledge graph by entity traversal."""
        return self.brain.graph_query(entity_name, depth)

    def entities(self) -> List[Dict]:
        """Return all entities in the knowledge graph."""
        return self.brain.entities()

    # Utilities

    def resolve_conflict(self, query: str) -> Dict:
        """Find and resolve logical contradictions for a given topic/query."""
        # 1. Find memories related to the query
        mems = self.recall(query, k=10)
        conflicted = [m for m in mems if m.status.name == "CONFLICTED"]

        if not conflicted:
            return {
                "status": "no_conflicts",
                "message": f"No active conflicts found for '{query}'",
            }

        # Simple resolution: Pick the most recent one as truth, deprecate others
        # In a real TMS, this would be more complex.
        conflicted.sort(key=lambda m: m.timestamp, reverse=True)
        truth = conflicted[0]
        deprecated = conflicted[1:]

        for m in deprecated:
            from .types import MemoryStatus

            m.status = MemoryStatus.DEPRECATED
            m.active = False
            # If backend supports per-memory save, use it. Usually handled by engine.

        return {
            "status": "resolved",
            "resolved_id": truth.id,
            "deprecated_ids": [m.id for m in deprecated],
            "message": f"Resolved conflict in favor of: {truth.content}",
        }

    def summarize_state(self, namespace: Optional[str] = None) -> str:
        """Provide a high-level summary of the system state (architecture, decisions, current goals)."""
        # Retrieval categories
        categories = ["architecture", "decision", "goal", "constraint"]
        summary_mems = []
        for cat in categories:
            summary_mems.extend(self.recall(cat, k=3, namespace=namespace))

        if not summary_mems:
            return "No significant state memories found."

        # Deduplicate and sort
        seen = set()
        unique_mems = []
        for m in summary_mems:
            if m.id not in seen:
                unique_mems.append(m)
                seen.add(m.id)

        unique_mems.sort(key=lambda m: m.importance, reverse=True)

        text = "### Current System Understanding\n\n"
        for m in unique_mems:
            text += (
                f"- **[{m.type.name}]** {m.content} (Importance: {m.importance:.2f})\n"
            )

        return text

    def stats(self) -> Dict:
        """Return system statistics."""
        return self.brain.stats()

    def all(
        self, namespace: Optional[str] = None, include_inactive: bool = False
    ) -> List[Memory]:
        """List all memories, optionally filtered by namespace."""
        return self.brain.all_memories(namespace, include_inactive)

    def clear(self, namespace: Optional[str] = None) -> None:
        """Clear memories in a namespace or all namespaces."""
        self.brain.clear(namespace)
        if namespace is None:
            self._backend.clear()

    def __repr__(self) -> str:
        s = self.brain.stats()
        ns = len(s["namespaces"])
        kg = s.get("knowledge_entities", 0)
        return f"OMem(memories={s['total']}, inactive={s['inactive']}, entities={kg}, namespaces={ns})"
