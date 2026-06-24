"""V2 context layer — Phase 3 of the implementation plan.

Purpose: select the optimal set of memories, state, and knowledge to send
to the LLM within a token budget. This is where token savings come from.

APIs (implemented in Phase 3):
    ContextEngine.build()            — assemble ContextBundle from budget
    ContextEngine.estimate_savings() — preview tokens saved vs naive recall

See: docs/roadmap/FULL_IMPLEMENTATION_PLAN.md — Phase 3
"""

from .engine import ContextBundle, ContextEngine, ContextRequest

__all__ = ["ContextEngine", "ContextRequest", "ContextBundle"]
