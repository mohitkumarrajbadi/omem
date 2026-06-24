"""V2 context layer — Phase 3 (fully implemented).

``ContextEngine`` selects the optimal subset of memory + state + knowledge
to send to the LLM within a given token budget.

Quickstart::

    from omem.context import ContextEngine, ContextRequest

    engine = ContextEngine(memory=agent.memory, state=agent.state)
    ctx = engine.build(ContextRequest(
        task="continue the auth refactor",
        budget_tokens=6000,
        session_id="agent-1",
    ))
    print(f"Tokens saved: {ctx.savings_vs_naive:.0%}")
    llm.chat(ctx.text + user_message)

See: docs/roadmap/FULL_IMPLEMENTATION_PLAN.md — Phase 3
"""

from .engine import ContextBundle, ContextEngine, ContextRequest
from .tokenizer import TokenCounter

__all__ = [
    "ContextEngine",
    "ContextRequest",
    "ContextBundle",
    "TokenCounter",
]
