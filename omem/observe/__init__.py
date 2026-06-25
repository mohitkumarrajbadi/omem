"""Phase 6 — Observability layer.

Every state transition, context build, and recall emits a TraceEvent.
"""

from .events import ObserveOS, TraceEvent, new_trace_id

# Layer 5 extension — local dashboard (``omem dashboard``)
from .dashboard import serve as dashboard_serve

__all__ = ["ObserveOS", "TraceEvent", "new_trace_id", "dashboard_serve"]
