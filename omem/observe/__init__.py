"""Phase 6 — Observability layer.

Every state transition, context build, and recall emits a TraceEvent.
"""

from .events import ObserveOS, TraceEvent, new_trace_id

__all__ = ["ObserveOS", "TraceEvent", "new_trace_id"]
