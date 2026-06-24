"""Context engine — Phase 3 of the v2 implementation plan.

The ``ContextEngine`` selects what actually gets sent to the LLM.
It fuses memory recall, current state, and knowledge graph neighbours,
then packs them into the caller's token budget.

Pipeline (after Phase 3):
    1. Load current StatePayload for the session (goal, plan, recent tool outputs)
    2. recall() top-k memories for the task (existing RAG pipeline)
    3. Graph neighbours for recalled entities (existing knowledge graph)
    4. Rank all sections by relevance + recency + importance
    5. Pack into token budget (greedy v1; knapsack v2)
    6. Format as structured prompt block

Reuses: omem/core/retrieval/ranker.py mode profiles, rag.py, StateOS.load().

Implementation target: docs/roadmap/FULL_IMPLEMENTATION_PLAN.md Phase 3.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ContextRequest:
    """Parameters for a context assembly request."""

    task: str
    budget_tokens: int
    session_id: Optional[str] = None
    namespace: Optional[str] = None
    mode: str = "planning"  # reuses existing ranker profiles
    include: List[str] = field(default_factory=lambda: ["memory", "state", "knowledge"])
    exclude_types: List[str] = field(default_factory=list)


@dataclass
class ContextBundle:
    """Assembled context ready to inject into an LLM prompt."""

    text: str
    sections: Dict[str, str] = field(default_factory=dict)
    token_count: int = 0
    memories_used: List[str] = field(default_factory=list)
    state_snapshot_id: Optional[str] = None
    savings_vs_naive: float = 0.0  # fraction of tokens saved vs dump-all


class ContextEngine:
    """V2 context engine.

    ``ContextEngine`` is the key token-savings layer. Given a task description
    and a token budget, it returns a ``ContextBundle`` containing the most
    relevant slice of memory + state + knowledge — nothing more.

    This class is a typed stub. All methods raise ``NotImplementedError``
    until Phase 3 is implemented.

    Example (after Phase 3)::

        engine = ContextEngine(omem=agent.memory.omem, state=agent.state)
        ctx = engine.build(ContextRequest(
            task="continue the auth refactor",
            budget_tokens=6000,
            session_id="agent-1",
        ))
        print(ctx.savings_vs_naive)  # e.g. 0.68 = 68% fewer tokens
        llm.complete(ctx.text + user_prompt)
    """

    def build(self, request: ContextRequest) -> ContextBundle:
        """Assemble an optimal context bundle within the token budget."""
        raise NotImplementedError("Phase 3 — see docs/roadmap/FULL_IMPLEMENTATION_PLAN.md")

    def estimate_savings(self, request: ContextRequest) -> Dict[str, Any]:
        """Return token counts for naive vs optimised context assembly.

        Returns a dict with keys: naive_tokens, optimised_tokens, savings_pct.
        """
        raise NotImplementedError("Phase 3 — see docs/roadmap/FULL_IMPLEMENTATION_PLAN.md")
