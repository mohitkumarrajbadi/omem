"""Engine Mixin: Addition Pipeline."""

import logging
import time
from typing import Dict, List, Optional

import numpy as np

from ..brain.classify import auto_classify_multi
from ...types import PRIORITY_MULTIPLIER, Memory, MemoryPriority, MemoryTier, MemoryType
from ..brain.importance import estimate_importance, estimate_priority
from ..brain.ingestion import apply_ingest_to_memory, ingest_experience
from ..brain.noise_gate import check_noise
from ..utils.concurrency import WriteContext
from ..utils.metrics import metrics
from .utils import _DEDUP_THRESHOLD, _TOKENIZER, _fast_hash, _token_hash

logger = logging.getLogger(__name__)


def _scoped_memory_id(namespace: str, content: str) -> str:
    """Content-hash scoped by org + namespace so identical text never collides.

    See omem-cloud ``docs/MIGRATION_MEMORY_IDS.md`` for upgrade notes.
    """
    try:
        from omem.backends.pg_session import resolve_pg_session

        org = resolve_pg_session(fallback_namespace=namespace or "default").org_id or ""
    except Exception:
        org = ""
    ns = namespace or "default"
    return _fast_hash(f"{org}\0{ns}\0{content}")


class AddMixin:
    """Methods for adding and indexing memories."""

    def add(
        self,
        content: str,
        mem_type: Optional[MemoryType] = None,
        metadata: Optional[Dict] = None,
        importance: Optional[float] = None,
        namespace: str = "default",
        source: str = "user",
        force: bool = False,
        memory_id: Optional[str] = None,
        confidence: Optional[float] = None,
    ) -> str:
        with metrics.timer("add"):
            imp = importance if importance is not None else estimate_importance(content)
            if self._noise_gate_enabled and not force:
                gate = check_noise(content, imp)
                if not gate.passed:
                    metrics.increment("noise_rejected")
                    return ""

            mem_id = memory_id if memory_id else _scoped_memory_id(namespace, content)
            type_scores = auto_classify_multi(content)
            primary_type = mem_type or type_scores[0][0]
            vector = self.embedder.encode(content)
            priority = estimate_priority(content)
            now = time.time()
            conf = confidence if confidence is not None else 1.0

            if self._dedup_enabled and not force:
                dedup_id = self._check_dedup(vector, content)
                if dedup_id:
                    return dedup_id

            current_size = self.kv.size
            if current_size >= self.quota.max_total:
                self.compress()
            elif current_size >= self.quota.max_active:
                self.forget()

            with WriteContext(self._lock):
                if mem_id in self.kv:
                    return mem_id
                tokens = set(_TOKENIZER.findall(content.lower()))
                token_hashes = np.array(
                    [_token_hash(t) for t in tokens], dtype=np.uint64
                )
                tier = (
                    MemoryTier.CORE
                    if priority == MemoryPriority.CORE
                    else MemoryTier.ACTIVE
                )

                base_score = float(imp * PRIORITY_MULTIPLIER.get(priority, 1.0))
                t_mask = 0
                for t, _ in type_scores:
                    t_mask |= 1 << t.value

                memory = Memory(
                    id=mem_id,
                    type=primary_type,
                    content=content,
                    vector=vector,
                    timestamp=now,
                    metadata=metadata or {},
                    importance=imp,
                    namespace=namespace,
                    source=source,
                    tokens=tokens,
                    token_hashes=token_hashes,
                    priority=priority,
                    tier=tier,
                    base_score=base_score,
                    type_mask=t_mask,
                    confidence_score=conf,
                    provenance=source,
                    freshness=now,
                    level="working",
                )

                self.vector_index.add(vector)
                self._id_order.append(mem_id)
                self.kv.set(mem_id, memory)

                if hasattr(self, "tms"):
                    self.tms.check_and_mark_conflicts(memory)

                self.working_memory.clear()

            ingest = ingest_experience(
                self.knowledge_graph,
                memory_id=mem_id,
                content=content,
                source=source,
                confidence=conf,
                namespace=namespace,
            )
            apply_ingest_to_memory(memory, ingest)
            self.kv.set(mem_id, memory)

            self.prefetcher.observe(content)
            self.write_buffer.enqueue(memory)
            metrics.increment("memories_added")
            return mem_id

    def add_experience(
        self,
        content: str,
        namespace: str = "default",
        source: str = "experience",
        confidence: float = 1.0,
        importance: Optional[float] = None,
        metadata: Optional[Dict] = None,
        force: bool = False,
    ) -> str:
        """Graph-first ingestion entrypoint for unstructured experience text."""
        return self.add(
            content,
            namespace=namespace,
            source=source,
            confidence=confidence,
            importance=importance,
            metadata=metadata,
            force=force,
        )

    def _check_dedup(self, vector: np.ndarray, content: str) -> Optional[str]:
        if self.vector_index.size == 0:
            return None
        scores, indices = self.vector_index.search(vector, 1)
        if len(scores) > 0:
            top_score, top_idx = float(scores[0]), int(indices[0])
            if top_score > _DEDUP_THRESHOLD and 0 <= top_idx < len(self._id_order):
                existing_id = self._id_order[top_idx]
                existing = self.kv.get(existing_id)
                if existing and existing.active:
                    existing.access_count += 1
                    existing.last_accessed = time.time()
                    existing.evidence_count += 1
                    existing.freshness = time.time()
                    return existing_id
        return None

    def add_batch(
        self,
        contents: List[str],
        mem_types: Optional[List[MemoryType]] = None,
        namespaces: Optional[List[str]] = None,
        sources: Optional[List[str]] = None,
    ) -> List[str]:
        """High-throughput batch add. Encodes markers in parallel."""
        if not contents:
            return []

        m_ids = []
        for i, content in enumerate(contents):
            m_type = mem_types[i] if mem_types and i < len(mem_types) else None
            ns = namespaces[i] if namespaces and i < len(namespaces) else "default"
            src = sources[i] if sources and i < len(sources) else "user"
            m_ids.append(self.add(content, mem_type=m_type, namespace=ns, source=src))
        return m_ids
