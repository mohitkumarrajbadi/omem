"""Phase 6 — Observability layer.

Every state transition, context build, and recall emits a TraceEvent.
"""

# Layer 5 extension — local dashboard (``omem dashboard``)
from .dashboard import serve as dashboard_serve
from .events import ObserveOS, TraceEvent, new_trace_id

__all__ = ["ObserveOS", "TraceEvent", "new_trace_id", "dashboard_serve"]
