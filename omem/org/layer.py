"""OrgMemoryOS — Phase 10: shared organizational memory.

Knowledge compounds across agents and teams. The namespace hierarchy
allows memories to be private, team-shared, or org-wide:

    personal/{user_id}/*              → private
    team/{team_id}/*                  → team-shared
    org/{org_id}/*                    → org-wide
    global                            → system-wide (read-only)

Key capabilities:
  1. ``remember(content, scope=...)``      — write to the right namespace
  2. ``recall_scoped(query, scope=...)``   — search up the hierarchy
  3. ``share(memory_id, target_namespace)``— promote memory to a higher tier
  4. ``namespaces()``                      — list all available namespaces
  5. ``promote(memory_id, to=...)``        — alias for share()

Exit criteria (from the implementation plan):
  "Agent A writes org memory. Agent B recalls it via scope='team'."

See: docs/roadmap/FULL_IMPLEMENTATION_PLAN.md — Phase 10
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from .namespace import NamespaceResolver

if TYPE_CHECKING:
    from omem.memory.layer import MemoryOS

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Data types
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class NamespaceInfo:
    """Metadata about a namespace in the hierarchy.

    Attributes:
        namespace:     The full namespace string.
        kind:          ``"personal"`` | ``"team"`` | ``"org"`` | ``"global"``.
        memory_count:  Number of active memories in this namespace.
        is_writable:   Whether the current user can write to this namespace.
    """

    namespace: str
    kind: str
    memory_count: int = 0
    is_writable: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "namespace": self.namespace,
            "kind": self.kind,
            "memory_count": self.memory_count,
            "is_writable": self.is_writable,
        }


@dataclass
class ShareResult:
    """Result of a ``share()`` or ``promote()`` operation.

    Attributes:
        original_id:      Memory ID of the source memory.
        new_id:           Memory ID of the memory in the target namespace.
        source_namespace: Where the memory was copied from.
        target_namespace: Where the memory was copied to.
    """

    original_id: str
    new_id: str
    source_namespace: str
    target_namespace: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_id": self.original_id,
            "new_id": self.new_id,
            "source_namespace": self.source_namespace,
            "target_namespace": self.target_namespace,
        }


# ──────────────────────────────────────────────────────────────────────────────
# OrgMemoryOS
# ──────────────────────────────────────────────────────────────────────────────


class OrgMemoryOS:
    """Phase 10 organizational memory layer — fully implemented.

    Provides namespace-aware memory operations for multi-agent, multi-team
    environments. Wraps ``MemoryOS`` with:

    - **Hierarchical recall**: ``recall_scoped()`` searches up the hierarchy
      (personal → team → org → global) and returns deduplicated, re-ranked results.
    - **Write routing**: ``remember()`` resolves the correct namespace from a
      ``scope`` alias (``"personal"``, ``"team"``, ``"org"``, ``"global"``).
    - **Memory promotion**: ``share()`` copies a memory to a higher namespace.

    **Identity context** (user_id, team_id, org_id) is set at construction time
    and used to resolve namespace strings automatically.

    Usage::

        org = agent.org
        # Agent A writes an org-level memory
        mid = org.remember("API rate limit is 100/min", scope="org")

        # Agent B in the same org recalls it
        results = org.recall_scoped("rate limits", scope="team")
        print(results[0].content)  # "API rate limit is 100/min"

        # Promote a personal memory to the team
        res = org.share(mid, target_namespace="team/eng")
        print(res.new_id)

    Thread safety: Delegates to ``MemoryOS`` which is thread-safe.
    """

    def __init__(
        self,
        memory: "MemoryOS",
        user_id: str = "",
        team_id: str = "",
        org_id: str = "",
    ) -> None:
        """Initialise OrgMemoryOS.

        Args:
            memory:  The ``MemoryOS`` instance to delegate operations to.
            user_id: The current user's ID. Used to resolve ``"personal"`` scope.
            team_id: The current team's ID. Used to resolve ``"team"`` scope.
            org_id:  The current org's ID. Used to resolve ``"org"`` scope.
        """
        self._memory = memory
        self._user_id = user_id
        self._team_id = team_id
        self._org_id = org_id
        self._resolver = NamespaceResolver
        logger.debug(
            "OrgMemoryOS initialized (user=%r, team=%r, org=%r)",
            user_id, team_id, org_id,
        )

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    @property
    def user_id(self) -> str:
        return self._user_id

    @property
    def team_id(self) -> str:
        return self._team_id

    @property
    def org_id(self) -> str:
        return self._org_id

    def with_identity(
        self,
        user_id: Optional[str] = None,
        team_id: Optional[str] = None,
        org_id: Optional[str] = None,
    ) -> "OrgMemoryOS":
        """Return a new ``OrgMemoryOS`` with updated identity context.

        Does not mutate the original instance.

        Args:
            user_id: Override the user ID.
            team_id: Override the team ID.
            org_id:  Override the org ID.

        Returns:
            New ``OrgMemoryOS`` instance with the updated identity.
        """
        return OrgMemoryOS(
            memory=self._memory,
            user_id=user_id if user_id is not None else self._user_id,
            team_id=team_id if team_id is not None else self._team_id,
            org_id=org_id if org_id is not None else self._org_id,
        )

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def remember(
        self,
        content: str,
        scope: str = "personal",
        *,
        importance: Optional[float] = None,
        source: str = "user",
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> str:
        """Store a memory in the namespace resolved from ``scope``.

        Args:
            content:    The memory content.
            scope:      Write scope. One of ``"personal"``, ``"team"``,
                        ``"org"``, ``"global"``, or a literal namespace string.
            importance: Optional importance override [0, 1].
            source:     The source of the memory (for audit / provenance).
            metadata:   Optional key-value metadata.

        Returns:
            The memory ID of the stored memory.
        """
        ns = self._resolve_write_ns(scope)
        return self._memory.remember(
            content,
            namespace=ns,
            importance=importance,
            source=source,
            metadata=metadata or {},
            **kwargs,
        )

    def _resolve_write_ns(self, scope: str) -> str:
        """Resolve a write scope alias to a concrete namespace string."""
        if scope == "personal":
            if self._user_id:
                return f"personal/{self._user_id}"
            return "default"
        if scope == "team":
            if self._team_id:
                return f"team/{self._team_id}"
            if self._org_id:
                return f"org/{self._org_id}"
            return "default"
        if scope == "org":
            if self._org_id:
                return f"org/{self._org_id}"
            return "default"
        if scope == "global":
            return "global"
        return scope  # treat as literal namespace

    # ------------------------------------------------------------------
    # Hierarchical recall
    # ------------------------------------------------------------------

    def recall_scoped(
        self,
        query: str,
        scope: str = "team",
        k: int = 5,
        user_id: Optional[str] = None,
        team_id: Optional[str] = None,
        org_id: Optional[str] = None,
        **kwargs: Any,
    ) -> List[Any]:
        """Recall memories from all namespaces within the given scope.

        Searches up the namespace hierarchy and returns deduplicated,
        re-ranked results.

        Args:
            query:   The recall query.
            scope:   One of ``"personal"``, ``"team"``, ``"org"``,
                     ``"global"``, ``"all"``, or a literal namespace.
            k:       Maximum number of results to return.
            user_id: Override the user_id for this call only.
            team_id: Override the team_id for this call only.
            org_id:  Override the org_id for this call only.

        Returns:
            Deduplicated list of ``Memory`` objects, most relevant first.
        """
        uid = user_id or self._user_id
        tid = team_id or self._team_id
        oid = org_id or self._org_id

        namespaces = self._resolver.scoped(
            scope=scope,
            user_id=uid,
            team_id=tid,
            org_id=oid,
        )

        if not namespaces:
            # Fall back to unscoped recall
            return self._memory.recall(query, k=k, **kwargs)

        all_results: List[Any] = []
        seen_ids: set = set()

        for ns in namespaces:
            try:
                results = self._memory.recall(query, namespace=ns, k=k, **kwargs)
                for mem in results:
                    mid = getattr(mem, "id", None)
                    if mid and mid not in seen_ids:
                        seen_ids.add(mid)
                        all_results.append(mem)
            except Exception as exc:
                logger.debug("recall_scoped: namespace %r failed: %s", ns, exc)

        # Re-sort by importance (proxy for relevance when no explicit score)
        all_results.sort(
            key=lambda m: (
                getattr(m, "score", None)
                or getattr(m, "importance", 0.0)
            ),
            reverse=True,
        )
        return all_results[:k]

    # ------------------------------------------------------------------
    # Memory promotion / sharing
    # ------------------------------------------------------------------

    def share(
        self,
        memory_id: str,
        target_namespace: str,
        source_namespace: Optional[str] = None,
    ) -> ShareResult:
        """Copy a memory to a target namespace (promotion).

        The original memory is NOT deleted. A new memory with the same
        content and importance is created in the target namespace.

        Args:
            memory_id:        The ID of the memory to share.
            target_namespace: The destination namespace.
            source_namespace: If provided, the source namespace to search.
                              If ``None``, searches all namespaces.

        Returns:
            ``ShareResult`` with original_id, new_id, and namespace info.

        Raises:
            ValueError: If the memory is not found.
        """
        # Find the source memory
        try:
            all_mems = self._memory.list(namespace=source_namespace)
        except Exception:
            all_mems = self._memory.list()

        source_mem = next(
            (m for m in all_mems if getattr(m, "id", None) == memory_id),
            None,
        )
        if source_mem is None:
            # Try without namespace filter
            all_mems = self._memory.list()
            source_mem = next(
                (m for m in all_mems if getattr(m, "id", None) == memory_id),
                None,
            )
        if source_mem is None:
            raise ValueError(f"Memory {memory_id!r} not found")

        src_ns = getattr(source_mem, "namespace", None) or source_namespace or "default"

        # Store in target namespace
        new_id = self._memory.remember(
            getattr(source_mem, "content", str(source_mem)),
            namespace=target_namespace,
            importance=getattr(source_mem, "importance", None),
            source="share",
            metadata={
                "shared_from": src_ns,
                "original_memory_id": memory_id,
            },
        )

        logger.info(
            "OrgMemoryOS.share: %r → %r (new_id=%r)",
            memory_id, target_namespace, new_id,
        )
        return ShareResult(
            original_id=memory_id,
            new_id=new_id,
            source_namespace=src_ns,
            target_namespace=target_namespace,
        )

    def promote(
        self,
        memory_id: str,
        to: str,
    ) -> ShareResult:
        """Alias for ``share()`` with a more natural call signature.

        Args:
            memory_id: The memory to promote.
            to:        Target namespace (or scope alias: ``"team"``, ``"org"``).

        Returns:
            ``ShareResult``.
        """
        resolved_ns = self._resolve_write_ns(to)
        return self.share(memory_id, target_namespace=resolved_ns)

    # ------------------------------------------------------------------
    # Namespace inspection
    # ------------------------------------------------------------------

    def namespaces(self) -> List[NamespaceInfo]:
        """Return all namespaces available to the current identity.

        Lists namespaces in order from most specific to least specific.
        Memory counts are included (requires listing all memories).

        Returns:
            List of ``NamespaceInfo`` objects.
        """
        # Build the known namespace list for this identity
        ns_list = self._resolver.scoped(
            scope="all",
            user_id=self._user_id,
            team_id=self._team_id,
            org_id=self._org_id,
        )
        if not ns_list:
            ns_list = ["default"]

        # Also discover any existing namespaces in the memory store
        try:
            all_mems = self._memory.list()
            for mem in all_mems:
                ns = getattr(mem, "namespace", None) or "default"
                if ns not in ns_list:
                    ns_list.append(ns)
        except Exception:
            pass

        # Count memories per namespace
        counts: Dict[str, int] = {}
        try:
            for ns_str in ns_list:
                try:
                    mems = self._memory.list(namespace=ns_str)
                    counts[ns_str] = len(mems)
                except Exception:
                    counts[ns_str] = 0
        except Exception:
            pass

        result: List[NamespaceInfo] = []
        for ns_str in ns_list:
            node = self._resolver.parse(ns_str)
            result.append(NamespaceInfo(
                namespace=ns_str,
                kind=node.kind,
                memory_count=counts.get(ns_str, 0),
                is_writable=(ns_str != "global"),
            ))
        return result

    def namespace_summary(self) -> Dict[str, Any]:
        """Return a summary of all available namespaces.

        Returns:
            Dict with total_namespaces, total_memories, and per-namespace breakdown.
        """
        infos = self.namespaces()
        return {
            "user_id": self._user_id,
            "team_id": self._team_id,
            "org_id": self._org_id,
            "total_namespaces": len(infos),
            "total_memories": sum(i.memory_count for i in infos),
            "namespaces": [i.to_dict() for i in infos],
        }
