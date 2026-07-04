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
    ) -> List[Memory]:
        """Retrieve memories using the multi-objective retrieval engine."""
        if isinstance(query, MemoryQuery):
            q = query
            return self._omem.recall(
                q.text,
                k=q.k if k is None else k,
                namespace=q.namespace if namespace is None else namespace,
                context_type=q.context_type if context_type is None else context_type,
                mode=q.mode if mode is None else mode,
                level=q.level if level is None else level,
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
            )

        return self._omem.recall(
            query,
            k=5 if k is None else k,
            namespace=namespace,
            context_type=context_type,
            mode=mode,
            level=level,
            tiers=tiers,
            include_archive=False if include_archive is None else include_archive,
            weight_overrides=weight_overrides,
            project_only=project_only,
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

    def list(
        self,
        *,
        namespace: Optional[str] = None,
        include_inactive: bool = False,
    ) -> List[Memory]:
        """List memories in the current store."""
        return self._omem.all(namespace=namespace, include_inactive=include_inactive)

    def stats(self) -> Dict[str, Any]:
        """Return memory layer statistics."""
        return self._omem.stats()

    def clear(self, namespace: Optional[str] = None) -> None:
        """Clear all memory or one namespace."""
        self._omem.clear(namespace=namespace)
