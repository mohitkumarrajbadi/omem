"""V2 runtime layer — Phase 9 of the implementation plan.

Purpose: coordinate multiple agents that share memory and state safely.

APIs (implemented in Phase 9):
    RuntimeOS.register()    — register an agent with its session
    RuntimeOS.sync()        — sync state for a session
    RuntimeOS.recover()     — find latest checkpoint for a crashed agent
    RuntimeOS.list_agents() — list active agents in a namespace

See: docs/roadmap/FULL_IMPLEMENTATION_PLAN.md — Phase 9
"""

from .layer import AgentRegistration, RuntimeOS

__all__ = ["RuntimeOS", "AgentRegistration"]
