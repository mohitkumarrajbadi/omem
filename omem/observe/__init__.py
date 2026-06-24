"""V2 observability layer — Phase 6 of the implementation plan.

Purpose: understand what agents are doing, why they succeed or fail,
and how much memory contributes to their quality and efficiency.

APIs (implemented in Phase 6):
    ObserveOS.metrics()    — recall rate, latency, token savings, restore rate
    ObserveOS.traces()     — all trace events for a session
    ObserveOS.replay()     — ordered iterator over a session's events
    ObserveOS.export_otel() — OpenTelemetry export (Phase 6b)

See: docs/roadmap/FULL_IMPLEMENTATION_PLAN.md — Phase 6
"""

from .events import ObserveOS, TraceEvent

__all__ = ["ObserveOS", "TraceEvent"]
