"""Observability layer — Phase 6 of the v2 implementation plan.

Every state transition, context build, and recall decision emits a
``TraceEvent``. These events power the dashboard, debugging, and the
context-savings metric shown in the leadership demo.

Implementation target: docs/roadmap/FULL_IMPLEMENTATION_PLAN.md Phase 6.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional


@dataclass
class TraceEvent:
    """A single observable event in an agent session."""

    id: str
    session_id: str
    event_type: str  # recall | snapshot | rollback | fork | context_build | tool_record | sleep
    timestamp: float
    duration_ms: float
    payload: Dict[str, Any] = field(default_factory=dict)
    namespace: str = "default"


class ObserveOS:
    """V2 observability layer.

    ``ObserveOS`` exposes metrics, traces, and replay for agent sessions.
    It answers: "Why did the agent fail?", "What memory was used?",
    "How many tokens did context compression save?"

    This class is a typed stub. All methods raise ``NotImplementedError``
    until Phase 6 is implemented.

    Key metrics tracked (after Phase 6):
        - Recall hit rate + latency p50/p99
        - Context tokens saved vs naive
        - Snapshot count + restore success rate
        - Fork depth + merge outcomes
        - Sleep cycle stats

    Example (after Phase 6)::

        observe = ObserveOS(omem=agent.memory.omem, state=agent.state)
        metrics = observe.metrics()
        print(metrics["context_tokens_saved_pct"])  # e.g. 68.4
    """

    def metrics(
        self,
        namespace: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return aggregated metrics for a namespace or session."""
        raise NotImplementedError("Phase 6 — see docs/roadmap/FULL_IMPLEMENTATION_PLAN.md")

    def traces(self, session_id: str) -> List[TraceEvent]:
        """Return all trace events for a session in chronological order."""
        raise NotImplementedError("Phase 6 — see docs/roadmap/FULL_IMPLEMENTATION_PLAN.md")

    def replay(self, session_id: str) -> Iterator[TraceEvent]:
        """Yield trace events for a session in order — for step-by-step replay."""
        raise NotImplementedError("Phase 6 — see docs/roadmap/FULL_IMPLEMENTATION_PLAN.md")

    def export_otel(self, session_id: Optional[str] = None) -> None:
        """Export traces in OpenTelemetry format (Phase 6b)."""
        raise NotImplementedError("Phase 6b — see docs/roadmap/FULL_IMPLEMENTATION_PLAN.md")
