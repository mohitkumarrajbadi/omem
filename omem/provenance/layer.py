"""ProvenanceOS — Phase 7: full provenance layer.

Traces WHERE every memory and state change came from. Every create,
update, merge, fork, and consolidation is recorded as a ``ProvenanceEvent``
so full lineage is queryable for any entity.

The provenance store is:
  - In-memory: ``_ProvenanceStore`` — thread-safe dict of entity_id → events
  - Queryable: ``trace(entity_id)`` and ``history(namespace)``
  - Linkable: multiple entities can be cross-referenced via ``related_ids``

``ProvenanceOS.record()`` is called from ``AgentState`` after each
instrumented write operation. No layer modifications are required.

See: docs/roadmap/FULL_IMPLEMENTATION_PLAN.md — Phase 7
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Public data types
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class ProvenanceEvent:
    """A single provenance record in the lineage history.

    Attributes:
        id:           Unique event ID (``prov_<ts>_<hex>``).
        entity_id:    The entity this event is about (memory_id, snapshot_id, etc.).
        entity_type:  ``"memory"`` | ``"snapshot"`` | ``"edge"`` | ``"state"`` |
                      ``"checkpoint"`` | ``"session"``.
        operation:    ``"create"`` | ``"update"`` | ``"merge"`` | ``"forget"`` |
                      ``"fork"`` | ``"rollback"`` | ``"consolidate"`` | ``"share"``.
        source:       Who triggered it: ``"user"`` | ``"agent"`` | ``"consolidation"``
                      | ``"ingestion"`` | ``"governance"``.
        timestamp:    Unix epoch float.
        session_id:   The session in effect at the time of the event.
        namespace:    The namespace in effect.
        confidence:   Source confidence [0, 1].
        related_ids:  Cross-references to other entities involved.
        metadata:     Operation-specific key-value pairs.
    """

    id: str
    entity_id: str
    entity_type: str
    operation: str
    source: str
    timestamp: float
    session_id: str = ""
    namespace: str = "default"
    confidence: float = 1.0
    related_ids: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "entity_id": self.entity_id,
            "entity_type": self.entity_type,
            "operation": self.operation,
            "source": self.source,
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "namespace": self.namespace,
            "confidence": self.confidence,
            "related_ids": self.related_ids,
            "metadata": self.metadata,
        }


@dataclass
class ProvenanceChain:
    """Full lineage history for a single entity.

    Attributes:
        root_id: The entity ID this chain describes.
        events:  Chronological list of all provenance events for this entity.
    """

    root_id: str
    events: List[ProvenanceEvent] = field(default_factory=list)

    @property
    def created_at(self) -> Optional[float]:
        """Timestamp of the oldest event (when the entity was first seen)."""
        return self.events[0].timestamp if self.events else None

    @property
    def last_modified_at(self) -> Optional[float]:
        """Timestamp of the most recent event."""
        return self.events[-1].timestamp if self.events else None

    @property
    def source_chain(self) -> List[str]:
        """List of sources that touched this entity, oldest first."""
        return [e.source for e in self.events]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "root_id": self.root_id,
            "event_count": len(self.events),
            "created_at": self.created_at,
            "last_modified_at": self.last_modified_at,
            "sources": self.source_chain,
            "events": [e.to_dict() for e in self.events],
        }


# ──────────────────────────────────────────────────────────────────────────────
# Internal store
# ──────────────────────────────────────────────────────────────────────────────


class _ProvenanceStore:
    """Thread-safe in-memory store: entity_id → list of ProvenanceEvents."""

    def __init__(self) -> None:
        self._by_entity: Dict[str, List[ProvenanceEvent]] = defaultdict(list)
        self._global: List[ProvenanceEvent] = []   # chronological global log
        self._lock = threading.RLock()
        self._MAX_GLOBAL = 100_000

    def add(self, event: ProvenanceEvent) -> None:
        with self._lock:
            self._by_entity[event.entity_id].append(event)
            self._global.append(event)
            if len(self._global) > self._MAX_GLOBAL:
                self._global = self._global[-self._MAX_GLOBAL:]

    def get_chain(self, entity_id: str) -> List[ProvenanceEvent]:
        with self._lock:
            return list(self._by_entity.get(entity_id, []))

    def history(
        self,
        namespace: Optional[str],
        limit: int,
        since: Optional[float],
    ) -> List[ProvenanceEvent]:
        with self._lock:
            events = list(self._global)
        if namespace:
            events = [e for e in events if e.namespace == namespace]
        if since is not None:
            events = [e for e in events if e.timestamp >= since]
        events.sort(key=lambda e: e.timestamp, reverse=True)
        return events[:limit]

    def all_entity_ids(self) -> List[str]:
        with self._lock:
            return list(self._by_entity.keys())

    def clear(self, entity_id: Optional[str] = None) -> None:
        with self._lock:
            if entity_id:
                self._by_entity.pop(entity_id, None)
            else:
                self._by_entity.clear()
                self._global.clear()


# ──────────────────────────────────────────────────────────────────────────────
# ProvenanceOS — public API
# ──────────────────────────────────────────────────────────────────────────────


class ProvenanceOS:
    """Phase 7 provenance layer — fully implemented.

    Tracks WHERE every memory, state snapshot, and knowledge edge came
    from. Answers "how did this memory get here?" and "who changed this
    session state?".

    Usage::

        agent = AgentState(session_id="demo")
        mid = agent.remember("FastAPI uses Pydantic")

        chain = agent.provenance.trace(mid)
        print(chain.source_chain)   # ["user"]

        history = agent.provenance.history("default", limit=20)
        for e in history:
            print(e.operation, e.entity_type, e.entity_id)

    Thread safety: All methods are thread-safe.
    """

    def __init__(self) -> None:
        self._store = _ProvenanceStore()
        logger.debug("ProvenanceOS initialized")

    # ------------------------------------------------------------------
    # Recording (called by AgentState instrumentation)
    # ------------------------------------------------------------------

    def record(
        self,
        entity_id: str,
        entity_type: str,
        operation: str,
        source: str = "agent",
        session_id: str = "",
        namespace: str = "default",
        confidence: float = 1.0,
        related_ids: Optional[List[str]] = None,
        **metadata: Any,
    ) -> ProvenanceEvent:
        """Record a single provenance event. Called from ``AgentState``.

        This method never raises — errors are logged and swallowed.

        Returns:
            The ``ProvenanceEvent`` that was recorded.
        """
        event = ProvenanceEvent(
            id=f"prov_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}",
            entity_id=entity_id,
            entity_type=entity_type,
            operation=operation,
            source=source,
            timestamp=time.time(),
            session_id=session_id,
            namespace=namespace,
            confidence=confidence,
            related_ids=related_ids or [],
            metadata=dict(metadata),
        )
        try:
            self._store.add(event)
        except Exception as exc:
            logger.warning("provenance.record failed: %s", exc)
        return event

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------

    def trace(self, entity_id: str) -> ProvenanceChain:
        """Return the full lineage chain for any entity.

        Args:
            entity_id: A memory ID, snapshot ID, edge ID, or session ID.

        Returns:
            ``ProvenanceChain`` with all events for the entity, oldest first.
            Returns an empty chain if the entity has no recorded provenance.
        """
        events = self._store.get_chain(entity_id)
        return ProvenanceChain(root_id=entity_id, events=sorted(events, key=lambda e: e.timestamp))

    def history(
        self,
        namespace: str,
        limit: int = 100,
        since: Optional[float] = None,
    ) -> List[ProvenanceEvent]:
        """Return recent provenance events across all entities in a namespace.

        Args:
            namespace: Filter to this namespace (``"default"`` for unscoped).
            limit:     Maximum number of events to return.
            since:     Only return events after this Unix timestamp.

        Returns:
            List of ``ProvenanceEvent``, newest first.
        """
        return self._store.history(namespace=namespace, limit=limit, since=since)

    def history_for_session(self, session_id: str, limit: int = 100) -> List[ProvenanceEvent]:
        """Return all provenance events for a specific session.

        Args:
            session_id: The session to query.
            limit:      Maximum number of events to return.

        Returns:
            List of ``ProvenanceEvent``, newest first.
        """
        events = self._store.history(namespace=None, limit=limit * 10, since=None)
        filtered = [e for e in events if e.session_id == session_id]
        return filtered[:limit]

    def known_entities(self) -> List[str]:
        """Return all entity IDs that have provenance records."""
        return self._store.all_entity_ids()

    def summary(self, namespace: Optional[str] = None) -> Dict[str, Any]:
        """Return aggregate provenance statistics.

        Returns:
            Dict with: total_events, entity_count, operations_breakdown,
            sources_breakdown, most_recent_event.
        """
        events = self._store.history(namespace=namespace, limit=100_000, since=None)
        ops: Dict[str, int] = defaultdict(int)
        srcs: Dict[str, int] = defaultdict(int)
        for e in events:
            ops[e.operation] += 1
            srcs[e.source] += 1
        return {
            "total_events": len(events),
            "entity_count": len(self._store.all_entity_ids()),
            "operations_breakdown": dict(ops),
            "sources_breakdown": dict(srcs),
            "most_recent_event": events[0].to_dict() if events else None,
        }

    def clear(self, entity_id: Optional[str] = None) -> None:
        """Clear provenance records.

        Args:
            entity_id: If provided, clear only this entity's history.
                       If None, clear all provenance records.
        """
        self._store.clear(entity_id)
