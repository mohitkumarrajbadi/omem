"""Minimal custom Python agent loop recipe — OMem v1.

Not a framework. Shows how an existing loop dual-writes durable run history
+ checkpoints without rewriting the application around OMem.

Example::

    from omem import AgentState
    from omem.integrations.custom_loop import DurableLoop

    agent = AgentState(session_id="ops", backend="memory")
    loop = DurableLoop(agent, goal="Investigate outage")
    loop.step("read_logs", lambda: {"ok": True})
    # ... crash ...
    loop = DurableLoop.resume(agent, run_id=...)
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from ..agent_state import AgentState
from ..state.runs import ActiveRun


class DurableLoop:
    """Thin helper: start/resume a run and checkpoint after each step."""

    def __init__(self, agent: AgentState, run: ActiveRun) -> None:
        self.agent = agent
        self.run = run

    @classmethod
    def start(
        cls,
        agent: AgentState,
        goal: str,
        *,
        worker_id: Optional[str] = None,
    ) -> "DurableLoop":
        if goal:
            try:
                agent.set_goal(goal)
            except Exception:
                pass
        run = agent.start_run(goal=goal, worker_id=worker_id)
        return cls(agent, run)

    @classmethod
    def resume(
        cls,
        agent: AgentState,
        run_id: str,
        *,
        worker_id: Optional[str] = None,
    ) -> "DurableLoop":
        run = agent.resume_run(run_id, worker_id=worker_id)
        return cls(agent, run)

    def step(
        self,
        name: str,
        fn: Callable[[], Any],
        *,
        idempotency_key: Optional[str] = None,
    ) -> Any:
        """Record tool_call → execute → tool_result → checkpoint.

        L1 idempotency dedupes records; ``fn`` may still run unless the caller
        skips execution when a prior result exists (not automatic — L2 is the
        tool's responsibility).
        """
        key = idempotency_key or f"step:{name}"
        call = self.run.record(
            "tool_call",
            {"tool": name},
            idempotency_key=f"{key}:call",
        )
        result = fn()
        self.run.record(
            "tool_result",
            {"result": result},
            causation_id=call.event_id,
            idempotency_key=f"{key}:result",
        )
        self.agent.advance()
        self.run.checkpoint()
        return result

    def complete(self, payload: Optional[Dict[str, Any]] = None) -> None:
        self.run.complete(payload)
