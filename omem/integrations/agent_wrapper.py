"""Agent-OMem Integration Wrapper.

Formalizes the 'Think-Act-Learn' loop for AI agents using OMem as a cognitive core.
"""

import logging
from typing import List, Optional, Callable

from ..api import OMem

logger = logging.getLogger(__name__)


class OMemAgent:
    """A wrapper for LLM agents that encapsulates OMem as their memory core."""

    def __init__(
        self,
        name: str = "Assistant",
        omem: Optional[OMem] = None,
        llm_fn: Optional[Callable[[str], str]] = None,
    ):
        self.name = name
        self.omem = omem or OMem()
        self.llm_fn = llm_fn
        self.last_retrieved_ids: List[str] = []

    def think(self, user_input: str) -> str:
        """Process user input with OMem context."""
        logger.info("Agent %s is thinking...", self.name)

        # 1. Retrieve relevant context from OMem
        # Uses the cognitive RAG mode with utility and importance awareness
        memories = self.omem.recall(user_input, limit=5)
        self.last_retrieved_ids = [m.id for m in memories]

        context_str = "\n".join([f"- {m.content}" for m in memories])

        # 2. Prepare the prompt for the LLM
        full_prompt = f"""You are {self.name}, an intelligent assistant.
Your memory context:
{context_str}

User: {user_input}
Answer:"""

        # 3. Call LLM
        if self.llm_fn:
            response = self.llm_fn(full_prompt)
        else:
            response = (
                "(Mock Response) Relying on internal context: " + context_str[:100]
            )

        return response

    def learn(self, info: str, importance: Optional[float] = None):
        """Save a new piece of information into OMem."""
        logger.info("Agent %s is learning: %s", self.name, info[:50])
        return self.omem.add(info, importance=importance)

    def feedback(self, success: bool, score_delta: float = 1.0):
        """Provide feedback to OMem based on the success of the last action."""
        if not self.last_retrieved_ids:
            return

        score = score_delta if success else -score_delta
        logger.info(
            "Agent %s applying feedback: %s to %d memories",
            self.name,
            "POSITIVE" if success else "NEGATIVE",
            len(self.last_retrieved_ids),
        )

        self.omem.feedback(self.last_retrieved_ids, score)

    def consolidate(self):
        """Trigger the 'dream' cycle for self-reflection and conflict resolution."""
        logger.info("Agent %s is starting deep consolidation...", self.name)
        return self.omem.consolidate(llm_fn=self.llm_fn)
