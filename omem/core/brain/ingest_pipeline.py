"""High-throughput ingest pipeline: classify → index metadata → graph → embed async.

Hot path avoids LLM. Embeddings can be deferred so classification + graph
hooks run at much higher rates than end-to-end ``add()``.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from ...types import Memory, MemoryType
from ..brain.classify import auto_classify_multi

logger = logging.getLogger(__name__)

try:
    import omem_rust

    _HAS_RUST = hasattr(omem_rust, "cognition_classify_batch")
except ImportError:
    omem_rust = None
    _HAS_RUST = False


@dataclass
class IngestItem:
    content: str
    namespace: str = "default"
    source: str = "ingest"
    importance: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    memory_id: Optional[str] = None


@dataclass
class IngestResult:
    accepted: int = 0
    classified: int = 0
    queued_embed: int = 0
    elapsed_ms: float = 0.0
    ids: List[str] = field(default_factory=list)
    ops_per_sec: float = 0.0


def classify_batch(contents: Sequence[str]) -> List[MemoryType]:
    """Classify many texts; prefer Rust batch when available."""
    if not contents:
        return []
    if _HAS_RUST:
        try:
            # Rust returns type indices matching MemoryType values when possible
            labels = omem_rust.cognition_classify_batch(list(contents))
            out = []
            for lab in labels:
                try:
                    out.append(MemoryType(int(lab)))
                except Exception:
                    out.append(MemoryType.SEMANTIC)
            if len(out) == len(contents):
                return out
        except Exception as exc:
            logger.debug("rust classify_batch fallback: %s", exc)
    return [auto_classify_multi(c)[0][0] for c in contents]


class IngestPipeline:
    """Async-friendly ingest orchestrator.

    Stages:
      1. classify (Rust pool / heuristics)
      2. create Memory shells with placeholder/hash vectors
      3. graph update hooks
      4. enqueue write buffer + optional embed worker
    """

    def __init__(
        self,
        engine,
        *,
        defer_embed: bool = True,
        embed_fn: Optional[Callable[[str], Any]] = None,
    ) -> None:
        self.engine = engine
        self.defer_embed = defer_embed
        self.embed_fn = embed_fn
        self._pending_embed: List[str] = []

    def ingest_batch(self, items: Sequence[IngestItem]) -> IngestResult:
        t0 = time.time()
        result = IngestResult()
        if not items:
            return result

        contents = [it.content for it in items]
        types = classify_batch(contents)
        result.classified = len(types)

        import numpy as np

        from ..brain.importance import estimate_importance
        from ..engine.add import _scoped_memory_id
        from ..engine.utils import _TOKENIZER, _token_hash

        for it, mtype in zip(items, types):
            mem_id = it.memory_id or _scoped_memory_id(it.namespace, it.content)
            if self.engine.kv.get(mem_id):
                continue
            imp = it.importance if it.importance is not None else estimate_importance(it.content)
            tokens = set(_TOKENIZER.findall(it.content.lower()))
            token_hashes = np.array([_token_hash(t) for t in tokens], dtype=np.uint64)

            if self.defer_embed:
                # Cheap deterministic placeholder until embed worker runs
                rng = np.random.default_rng(abs(hash(mem_id)) % (2**32))
                vector = rng.standard_normal(self.engine.embedder.dim).astype(np.float32)
                vector /= max(float(np.linalg.norm(vector)), 1e-9)
                self._pending_embed.append(mem_id)
                result.queued_embed += 1
            else:
                vector = self.engine.embedder.encode(it.content)

            scores = auto_classify_multi(it.content)
            t_mask = 0
            for t, _ in scores:
                t_mask |= 1 << t.value

            memory = Memory(
                id=mem_id,
                type=mtype,
                content=it.content,
                vector=vector,
                timestamp=time.time(),
                importance=imp,
                namespace=it.namespace,
                source=it.source,
                tokens=tokens,
                token_hashes=token_hashes,
                type_mask=t_mask,
                type_confidence=float(scores[0][1]) if scores else 1.0,
                metadata=dict(it.metadata or {}),
                level="working",
                base_score=float(imp),
            )
            self.engine.vector_index.add(vector)
            self.engine._id_order.append(mem_id)
            self.engine.kv.set(mem_id, memory)
            if hasattr(self.engine, "write_buffer") and self.engine.write_buffer:
                self.engine.write_buffer.enqueue(memory)

            kg = getattr(self.engine, "knowledge_graph", None)
            if kg is not None:
                try:
                    from .ingestion import ingest_experience

                    ingest_experience(kg, mem_id, it.content)
                except Exception:
                    pass

            result.ids.append(mem_id)
            result.accepted += 1

        elapsed = (time.time() - t0) * 1000.0
        result.elapsed_ms = elapsed
        result.ops_per_sec = (
            result.accepted / (elapsed / 1000.0) if elapsed > 0 else 0.0
        )
        return result

    def flush_embeddings(self, limit: Optional[int] = None) -> int:
        """Re-embed deferred memories with the real embedder."""
        ids = self._pending_embed[: limit or len(self._pending_embed)]
        done = 0
        for mid in ids:
            mem = self.engine.kv.get(mid)
            if mem is None:
                continue
            vec = self.engine.embedder.encode(mem.content)
            mem.vector = vec
            done += 1
        self._pending_embed = self._pending_embed[len(ids) :]
        return done
