"""Memory layer facade for the v2 API surface."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Union

from ..api import OMem
from ..types import Memory, MemoryTier, MemoryType, RetrievalExplanation


@dataclass
class MemoryQuery:
    """Typed query contract for the v2 memory layer."""

    text: str
    k: int = 5
    namespace: Optional[str] = None
    context_type: Optional[str] = None
    mode: str = "default"
    level: Optional[str] = None
    tiers: Optional[List[MemoryTier]] = None
    include_archive: bool = False
    weight_overrides: Optional[Dict[str, float]] = None
    as_of: Optional[float] = None
    rerank: Optional[bool] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class MemoryOS:
    """V2 memory layer.

    ``MemoryOS`` intentionally delegates to the mature ``OMem`` implementation.
    It gives v2 a clean package boundary and memory-native method names without
    forcing a disruptive migration for existing users.
    """

    def __init__(self, omem: Optional[OMem] = None, **kwargs: Any) -> None:
        self._omem = omem or OMem(**kwargs)

    @property
    def omem(self) -> OMem:
        """Return the underlying stable OMem instance."""
        return self._omem

    def remember(
        self,
        content: str,
        *,
        namespace: str = "default",
        memory_type: Optional[MemoryType] = None,
        importance: Optional[float] = None,
        confidence: float = 1.0,
        source: str = "memory",
        metadata: Optional[Dict[str, Any]] = None,
        force: bool = False,
    ) -> str:
        """Store graph-backed experience in memory."""
        if confidence != 1.0 or (source != "memory" and source != "user"):
            return self._omem.add_experience(
                content,
                namespace=namespace,
                source=source,
                confidence=confidence,
                importance=importance,
                metadata=metadata,
                force=force,
            )
        return self._omem.add(
            content,
            mem_type=memory_type,
            namespace=namespace,
            importance=importance,
            metadata=metadata,
            source=source,
            force=force,
        )

    def recall(
        self,
        query: Union[str, MemoryQuery],
        *,
        k: Optional[int] = None,
        namespace: Optional[str] = None,
        context_type: Optional[str] = None,
        mode: Optional[str] = None,
        level: Optional[str] = None,
        tiers: Optional[List[MemoryTier]] = None,
        include_archive: Optional[bool] = None,
        weight_overrides: Optional[Dict[str, float]] = None,
        project_only: bool = False,
        lookup: Optional[str] = None,
        memory_type: Optional[MemoryType] = None,
        as_of: Optional[float] = None,
        rerank: Optional[bool] = None,
    ) -> List[Memory]:
        """Retrieve memories using the multi-objective retrieval engine."""
        from ..core.retrieval.lookup import recall_routed
        from ..types import resolve_hierarchy_level

        if lookup or memory_type is not None:
            text = query.text if isinstance(query, MemoryQuery) else query
            return recall_routed(
                self._omem,
                text,
                k=5 if k is None else k,
                namespace=namespace
                if namespace is not None
                else (query.namespace if isinstance(query, MemoryQuery) else None),
                mode=(
                    mode
                    or (query.mode if isinstance(query, MemoryQuery) else None)
                    or "default"
                ),
                lookup=lookup,
                memory_type=memory_type,
                level=level
                if level is not None
                else (query.level if isinstance(query, MemoryQuery) else None),
                context_type=context_type,
                weight_overrides=weight_overrides,
                project_only=project_only,
            )

        if isinstance(query, MemoryQuery):
            q = query
            level_val = q.level if level is None else level
            return self._omem.recall(
                q.text,
                k=q.k if k is None else k,
                namespace=q.namespace if namespace is None else namespace,
                context_type=q.context_type if context_type is None else context_type,
                mode=q.mode if mode is None else mode,
                level=resolve_hierarchy_level(level_val) if level_val else level_val,
                tiers=q.tiers if tiers is None else tiers,
                include_archive=(
                    q.include_archive if include_archive is None else include_archive
                ),
                weight_overrides=(
                    q.weight_overrides
                    if weight_overrides is None
                    else weight_overrides
                ),
                project_only=q.metadata.get("project_only", False) if q.metadata else False,
                as_of=q.as_of if as_of is None else as_of,
                rerank=q.rerank if rerank is None else rerank,
            )

        return self._omem.recall(
            query,
            k=5 if k is None else k,
            namespace=namespace,
            context_type=context_type,
            mode=mode,
            level=resolve_hierarchy_level(level) if level else level,
            tiers=tiers,
            include_archive=False if include_archive is None else include_archive,
            weight_overrides=weight_overrides,
            project_only=project_only,
            as_of=as_of,
            rerank=rerank,
        )

    def explain(
        self,
        query: str,
        *,
        k: int = 5,
        namespace: Optional[str] = None,
        mode: str = "default",
        weight_overrides: Optional[Dict[str, float]] = None,
    ) -> List[RetrievalExplanation]:
        """Explain why memories would be recalled."""
        return self._omem.inspect(
            query,
            top_k=k,
            namespace=namespace,
            mode=mode,
            weight_overrides=weight_overrides,
        )

    def consolidate(self, speed: str = "normal") -> Dict[str, Any]:
        """Run the memory sleep cycle."""
        return self._omem.sleep(speed=speed)

    def forget(self) -> Any:
        """Run the forgetting engine."""
        return self._omem.forget()

    def archive(self, memory_id: str) -> bool:
        """Force L4 archive transition for a single memory.

        Moves the memory to ``MemoryTier.ARCHIVE``, sets level to archive,
        and marks lifecycle_stage as archived. Optionally spills content to
        cold object storage when ``OMEM_COLD_ENABLED=1``.
        """
        from ..backends.cold_archive import ColdArchive
        from ..types import LifecycleStage, MemoryStatus, MemoryTier

        mem = self._omem.get(memory_id)
        if mem is None:
            return False
        try:
            cold = ColdArchive()
            if cold.config.enabled:
                cold.archive_memory(mem)
        except Exception:
            pass
        mem.tier = MemoryTier.ARCHIVE
        mem.level = "archive"
        mem.status = MemoryStatus.ARCHIVED
        mem.lifecycle_stage = LifecycleStage.ARCHIVED.value
        mem.archived_at = mem.archived_at or __import__("time").time()
        if hasattr(self._omem, "brain") and hasattr(self._omem.brain, "kv"):
            self._omem.brain.kv.set(mem.id, mem)
        return True

    def list(
        self,
        *,
        namespace: Optional[str] = None,
        include_inactive: bool = False,
    ) -> List[Memory]:
        """List memories in the current store."""
        return self._omem.all(namespace=namespace, include_inactive=include_inactive)

    def profile(
        self,
        *,
        namespace: str = "default",
        user_id: str = "",
        session_id: Optional[str] = None,
        state: Optional[Any] = None,
        max_facts: int = 20,
        max_recent: int = 8,
    ):
        """Compile a no-LLM briefing from current facts, recent episodes, and goal."""
        from .profile import profile_from_layers

        return profile_from_layers(
            self,
            state,
            namespace=namespace,
            user_id=user_id,
            session_id=session_id,
            max_facts=max_facts,
            max_recent=max_recent,
        )

    def remember_document(
        self,
        source: Any,
        *,
        namespace: str = "default",
        filename: Optional[str] = None,
        max_chars: int = 1200,
        overlap: int = 150,
        importance: float = 0.55,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ):
        """Chunk a markdown/PDF/HTML document into memories. No LLM extract."""
        from ..ingest.documents import remember_document as _remember_document

        return _remember_document(
            self,
            source,
            namespace=namespace,
            filename=filename,
            max_chars=max_chars,
            overlap=overlap,
            importance=importance,
            extra_metadata=extra_metadata,
        )

    def ingest_folder(self, path: str, **kwargs: Any):
        """Ingest markdown/HTML/PDF files from a folder. No LLM."""
        from ..ingest.connectors import ingest_folder as _ingest_folder

        return _ingest_folder(self, path, **kwargs)

    def ingest_url(self, url: str, **kwargs: Any):
        """Fetch a URL and ingest stripped text. No LLM."""
        from ..ingest.connectors import ingest_url as _ingest_url

        return _ingest_url(self, url, **kwargs)

    def ingest_notion(self, **kwargs: Any):
        """Pull Notion pages via REST and ingest block text. No LLM."""
        from ..ingest.connectors import ingest_notion as _ingest_notion

        return _ingest_notion(self, **kwargs)

    def ingest_drive(self, **kwargs: Any):
        """Pull Google Drive files via REST and ingest exported text. No LLM."""
        from ..ingest.connectors import ingest_drive as _ingest_drive

        return _ingest_drive(self, **kwargs)

    def stats(self) -> Dict[str, Any]:
        """Return memory layer statistics."""
        return self._omem.stats()

    def ingest_batch(
        self,
        contents: List[str],
        *,
        namespace: str = "default",
        defer_embed: bool = True,
    ) -> Dict[str, Any]:
        """High-throughput ingest: classify → index → graph (embed optional defer)."""
        from ..core.brain.ingest_pipeline import IngestItem, IngestPipeline

        pipe = IngestPipeline(self._omem.brain, defer_embed=defer_embed)
        items = [IngestItem(content=c, namespace=namespace) for c in contents]
        result = pipe.ingest_batch(items)
        return {
            "accepted": result.accepted,
            "classified": result.classified,
            "queued_embed": result.queued_embed,
            "ops_per_sec": result.ops_per_sec,
            "elapsed_ms": result.elapsed_ms,
            "ids": result.ids,
        }

    def clear(self, namespace: Optional[str] = None) -> None:
        """Clear all memory or one namespace."""
        self._omem.clear(namespace=namespace)
