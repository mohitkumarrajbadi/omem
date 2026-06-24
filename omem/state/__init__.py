"""V2 state layer — Phase 2 of the implementation plan.

Purpose: preserve agent execution state across sessions, crashes, and plan branches.

APIs (implemented in Phase 2):
    StateOS.save()         — persist session state
    StateOS.load()         — restore session state
    StateOS.snapshot()     — immutable point-in-time copy
    StateOS.rollback()     — revert to a prior snapshot
    StateOS.fork()         — branch from a snapshot into a new session
    StateOS.checkpoint()   — lightweight crash-recovery marker
    StateOS.resume()       — restore from latest checkpoint

See: docs/roadmap/FULL_IMPLEMENTATION_PLAN.md — Phase 2
"""

from .layer import StateOS

__all__ = ["StateOS"]
