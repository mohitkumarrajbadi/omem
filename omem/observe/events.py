"""ObserveOS — Phase 6: full observability layer.

Every state transition, context build, recall decision, and memory
write emits a ``TraceEvent``. These events power:
  - Real-time metrics: latency, token savings, hit rate
  - Step-by-step session replay for debugging
  - OpenTelemetry-compatible export (OTLP JSON)
  - CLI dashboard

Architecture:
  - ``_EventStore`` — thread-safe ring buffer (max 10,000 events/session)
  - ``ObserveOS``  — recording target + query/metrics engine

``ObserveOS.record(event)`` is called from ``AgentState`` after each
instrumented operation. The layer itself does not intercept calls; instead,
the facade pattern is used so that layers stay decoupled.

See: docs/roadmap/FULL_IMPLEMENTATION_PLAN.md — Phase 6
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Public data types
# ──────────────────────────────────────────────────────────────────────────────

_EVENT_TYPES = frozenset({
    "remember", "recall", "forget", "consolidate",
    "snapshot", "rollback", "fork", "clone", "merge",
    "checkpoint", "resume",
    "context_build",
    "learn",           # knowledge.link
    "sleep",           # memory consolidation cycle
    "register",        # runtime agent registration
    "share",           # org memory promotion
})


@dataclass
class TraceEvent:
    """A single observable event emitted during an agent session.

    Attributes:
        id:          Unique trace ID (``tr_<ts>_<hex>``).
        session_id:  The session this event belongs to.
        event_type:  One of the canonical event type strings.
        timestamp:   Unix epoch float (seconds).
        duration_ms: Wall-clock time for the operation in milliseconds.
        payload:     Operation-specific metadata (memory_id, token counts, etc.).
        namespace:   Namespace in effect at the time of the event.
    """

    id: str
    session_id: str
    event_type: str
    timestamp: float
    duration_ms: float
    payload: Dict[str, Any] = field(default_factory=dict)
    namespace: str = "default"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
            "payload": self.payload,
            "namespace": self.namespace,
        }


def new_trace_id() -> str:
    """Generate a time-sortable trace ID."""
    return f"tr_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"


# ──────────────────────────────────────────────────────────────────────────────
# Internal: thread-safe event store
# ──────────────────────────────────────────────────────────────────────────────


class _EventStore:
    """Thread-safe ring-buffer store: per-session deque of TraceEvents."""

    MAX_EVENTS_PER_SESSION: int = 10_000

    def __init__(self) -> None:
        self._store: Dict[str, deque] = defaultdict(
            lambda: deque(maxlen=self.MAX_EVENTS_PER_SESSION)
        )
        self._lock = threading.RLock()
        self._global: deque = deque(maxlen=100_000)

    def add(self, event: TraceEvent) -> None:
        with self._lock:
            self._store[event.session_id].append(event)
            self._global.append(event)

    def get(self, session_id: str) -> List[TraceEvent]:
        with self._lock:
            return list(self._store.get(session_id, []))

    def all_events(self, namespace: Optional[str] = None) -> List[TraceEvent]:
        with self._lock:
            events = list(self._global)
        if namespace:
            events = [e for e in events if e.namespace == namespace]
        return events

    def clear(self, session_id: Optional[str] = None) -> None:
        with self._lock:
            if session_id:
                self._store.pop(session_id, None)
            else:
                self._store.clear()
                self._global.clear()

    def session_ids(self) -> List[str]:
        with self._lock:
            return list(self._store.keys())


# ──────────────────────────────────────────────────────────────────────────────
# Statistics helpers
# ──────────────────────────────────────────────────────────────────────────────


def _percentile(data: List[float], pct: float) -> float:
    """Linear-interpolation percentile (no numpy required)."""
    if not data:
        return 0.0
    s = sorted(data)
    k = (pct / 100.0) * (len(s) - 1)
    lo, hi = int(k), int(k) + 1
    if hi >= len(s):
        return s[-1]
    return s[lo] + (k - lo) * (s[hi] - s[lo])


def _compute_metrics(events: List[TraceEvent]) -> Dict[str, Any]:
    """Compute aggregate metrics from a list of trace events."""
    by_type: Dict[str, List[TraceEvent]] = defaultdict(list)
    for e in events:
        by_type[e.event_type].append(e)

    recall_events = by_type.get("recall", [])
    recall_latencies = [e.duration_ms for e in recall_events]

    context_events = by_type.get("context_build", [])
    savings_pcts = [
        e.payload.get("savings_pct", 0.0) for e in context_events
        if isinstance(e.payload.get("savings_pct"), (int, float))
    ]
    tokens_used = [
        e.payload.get("token_count", 0) for e in context_events
        if isinstance(e.payload.get("token_count"), (int, float))
    ]

    rollback_events = by_type.get("rollback", [])
    restore_attempts = len(rollback_events) + len(by_type.get("resume", []))
    restore_successes = sum(
        1 for e in rollback_events + by_type.get("resume", [])
        if not e.payload.get("error")
    )

    return {
        "total_events": len(events),
        "remember_count": len(by_type.get("remember", [])),
        "recall_count": len(recall_events),
        "recall_latency_p50_ms": round(_percentile(recall_latencies, 50), 2),
        "recall_latency_p99_ms": round(_percentile(recall_latencies, 99), 2),
        "recall_avg_latency_ms": (
            round(sum(recall_latencies) / len(recall_latencies), 2) if recall_latencies else 0.0
        ),
        "snapshot_count": len(by_type.get("snapshot", [])),
        "rollback_count": len(rollback_events),
        "checkpoint_count": len(by_type.get("checkpoint", [])),
        "resume_count": len(by_type.get("resume", [])),
        "fork_count": len(by_type.get("fork", [])),
        "clone_count": len(by_type.get("clone", [])),
        "context_build_count": len(context_events),
        "context_tokens_saved_pct": round(
            sum(savings_pcts) / len(savings_pcts) if savings_pcts else 0.0, 1
        ),
        "context_avg_tokens": round(
            sum(tokens_used) / len(tokens_used) if tokens_used else 0.0, 0
        ),
        "restore_success_rate": (
            round(restore_successes / restore_attempts, 3)
            if restore_attempts > 0 else 1.0
        ),
        "knowledge_link_count": len(by_type.get("learn", [])),
        "consolidate_count": len(by_type.get("consolidate", [])),
        "share_count": len(by_type.get("share", [])),
    }


# ──────────────────────────────────────────────────────────────────────────────
# ObserveOS — public API
# ──────────────────────────────────────────────────────────────────────────────


class ObserveOS:
    """Phase 6 observability layer — fully implemented.

    Every operation in ``AgentState`` calls ``observe.record(event)``
    immediately after completion. ``ObserveOS`` stores all events in a
    thread-safe ring buffer and exposes three query modes:

    1. **Metrics** — aggregated statistics (latency, savings, hit rates)
    2. **Traces** — raw event list for a session
    3. **Replay** — iterator for step-by-step session reconstruction
    4. **OTel export** — OTLP-compatible JSON for Jaeger/Zipkin/Grafana Tempo

    Usage::

        agent = AgentState(session_id="demo")
        # … do things …
        m = agent.observe.metrics(session_id="demo")
        print(f"Recall p99: {m['recall_latency_p99_ms']}ms")
        print(f"Context savings: {m['context_tokens_saved_pct']}%")

    Thread safety: All methods are thread-safe.
    """

    def __init__(self) -> None:
        self._store = _EventStore()
        logger.debug("ObserveOS initialized")

    # ------------------------------------------------------------------
    # Recording (called by AgentState instrumentation)
    # ------------------------------------------------------------------

    def record(self, event: TraceEvent) -> None:
        """Record a trace event. Called by ``AgentState`` after each operation.

        This method never raises — any storage error is logged and silently
        swallowed so instrumentation never breaks the main call path.
        """
        try:
            self._store.add(event)
        except Exception as exc:
            logger.warning("observe.record failed: %s", exc)

    # ------------------------------------------------------------------
    # Query API
    # ------------------------------------------------------------------

    def metrics(
        self,
        namespace: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return aggregated operational metrics.

        Args:
            namespace:  Filter to a specific namespace.
            session_id: Filter to a specific session (overrides namespace).

        Returns:
            Dict with latency percentiles, token savings, event counts.
        """
        events = (
            self._store.get(session_id)
            if session_id
            else self._store.all_events(namespace=namespace)
        )
        base = _compute_metrics(events)
        base["session_id"] = session_id
        base["namespace"] = namespace
        base["event_window_start"] = events[0].timestamp if events else None
        base["event_window_end"] = events[-1].timestamp if events else None
        return base

    def traces(self, session_id: str) -> List[TraceEvent]:
        """Return all trace events for a session in chronological order.

        Args:
            session_id: The session to retrieve traces for.

        Returns:
            List of ``TraceEvent`` objects, oldest first.
        """
        return self._store.get(session_id)

    def replay(self, session_id: str) -> Iterator[TraceEvent]:
        """Yield trace events for a session in chronological order.

        Suitable for step-by-step replay of what an agent did.

        Args:
            session_id: The session to replay.

        Yields:
            ``TraceEvent`` objects one at a time.
        """
        for event in self._store.get(session_id):
            yield event

    def export_otel(
        self,
        session_id: Optional[str] = None,
        service_name: str = "omem",
        service_version: str = "0.5.0",
    ) -> Dict[str, Any]:
        """Export traces in OpenTelemetry-compatible OTLP JSON format.

        The output can be sent to any OTLP-compatible backend:
        Jaeger, Zipkin, Grafana Tempo, Honeycomb, etc.

        Args:
            session_id:      Filter to a specific session. If None, exports all.
            service_name:    OTel ``service.name`` resource attribute.
            service_version: OTel ``service.version`` resource attribute.

        Returns:
            OTLP JSON dict — serialize to JSON and POST to your collector.
        """
        events = (
            self._store.get(session_id)
            if session_id
            else self._store.all_events()
        )

        # Group events by session for trace hierarchy
        by_session: Dict[str, List[TraceEvent]] = defaultdict(list)
        for e in events:
            by_session[e.session_id].append(e)

        scope_spans = []
        for sess_id, sess_events in by_session.items():
            spans = []
            for event in sess_events:
                # Represent each event as a span
                span = {
                    "traceId": _hex_id(sess_id, 32),
                    "spanId": _hex_id(event.id, 16),
                    "operationName": event.event_type,
                    "startTimeUnixNano": str(int(event.timestamp * 1e9)),
                    "endTimeUnixNano": str(int((event.timestamp + event.duration_ms / 1000) * 1e9)),
                    "kind": 2,  # CLIENT span
                    "attributes": [
                        {"key": "session.id", "value": {"stringValue": sess_id}},
                        {"key": "namespace", "value": {"stringValue": event.namespace}},
                        *[
                            {"key": k, "value": {"stringValue": str(v)}}
                            for k, v in event.payload.items()
                        ],
                    ],
                    "status": {
                        "code": 2 if event.payload.get("error") else 1,
                    },
                }
                spans.append(span)

            scope_spans.append({
                "scope": {
                    "name": "omem.observe",
                    "version": service_version,
                },
                "spans": spans,
            })

        return {
            "resourceSpans": [{
                "resource": {
                    "attributes": [
                        {"key": "service.name", "value": {"stringValue": service_name}},
                        {"key": "service.version", "value": {"stringValue": service_version}},
                    ]
                },
                "scopeSpans": scope_spans,
            }]
        }

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def session_ids(self) -> List[str]:
        """Return all session IDs that have at least one recorded event."""
        return self._store.session_ids()

    def clear(self, session_id: Optional[str] = None) -> None:
        """Flush the event store (all sessions, or a specific session).

        Args:
            session_id: If provided, clear only this session's events.
                        If None, clear everything.
        """
        self._store.clear(session_id)

    def event_count(self, session_id: Optional[str] = None) -> int:
        """Return total number of stored events."""
        if session_id:
            return len(self._store.get(session_id))
        return sum(len(self._store.get(s)) for s in self._store.session_ids())


# ──────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────────────


def _hex_id(source: str, length: int) -> str:
    """Derive a stable hex ID from a source string (for OTel trace/span IDs)."""
    import hashlib
    h = hashlib.md5(source.encode(), usedforsecurity=False).hexdigest()
    return (h * (length // 32 + 1))[:length]
