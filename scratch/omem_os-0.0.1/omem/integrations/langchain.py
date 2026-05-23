"""LangChain integration — drop-in OMem memory for LangChain agents.

Usage::

    from omem.integrations.langchain import OMemChatMemory

    memory = OMemChatMemory(namespace="agent-1")
    agent = ConversationChain(memory=memory, llm=llm)

Works standalone (no LangChain required) — the class follows the
LangChain BaseMemory interface pattern.
"""

from typing import Any, Dict, List, Optional

from ..api import OMem


class OMemChatMemory:
    """LangChain-compatible chat memory backed by OMem.

    Implements the LangChain BaseMemory interface:
    - memory_variables → list of keys
    - load_memory_variables(inputs) → context dict
    - save_context(inputs, outputs) → store turn
    - clear() → reset
    """

    memory_key: str = "history"
    input_key: str = "input"
    output_key: str = "output"

    def __init__(
        self,
        omem: Optional[OMem] = None,
        namespace: str = "langchain",
        return_messages: bool = False,
        top_k: int = 5,
    ):
        self.omem = omem or OMem()
        self.namespace = namespace
        self.return_messages = return_messages
        self.top_k = top_k
        self._conversation: List[str] = []

    @property
    def memory_variables(self) -> List[str]:
        return [self.memory_key]

    def load_memory_variables(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Retrieve relevant memories for the current input."""
        query = inputs.get(self.input_key, "")
        if not query:
            return {self.memory_key: "" if not self.return_messages else []}

        results = self.omem.recall(query, top_k=self.top_k, namespace=self.namespace)

        if self.return_messages:
            return {
                self.memory_key: [
                    {"content": m.content, "score": m.score} for m in results
                ]
            }
        else:
            context = "\n".join(f"- {m.content}" for m in results)
            return {self.memory_key: context}

    def save_context(self, inputs: Dict[str, Any], outputs: Dict[str, str]) -> None:
        """Store the current turn as a memory."""
        user_input = inputs.get(self.input_key, "")
        ai_output = outputs.get(self.output_key, "")

        if user_input:
            self.omem.add(
                f"User: {user_input}", namespace=self.namespace, source="user"
            )
            self._conversation.append(f"User: {user_input}")

        if ai_output:
            self.omem.add(f"AI: {ai_output}", namespace=self.namespace, source="agent")
            self._conversation.append(f"AI: {ai_output}")

    def clear(self) -> None:
        """Clear all memories in this namespace."""
        # Reflect on conversation before clearing
        if len(self._conversation) >= 3:
            self.omem.reflect_conversation(self._conversation)
        self.omem.clear(namespace=self.namespace)
        self._conversation.clear()


class OMemRetriever:
    """LangChain-compatible retriever backed by OMem.

    Can be used with RetrievalQA, create_retrieval_chain, etc.
    """

    def __init__(
        self,
        omem: Optional[OMem] = None,
        namespace: str = "default",
        top_k: int = 5,
    ):
        self.omem = omem or OMem()
        self.namespace = namespace
        self.top_k = top_k

    def get_relevant_documents(self, query: str) -> List[Dict[str, Any]]:
        """Retrieve relevant documents from OMem."""
        results = self.omem.recall(query, top_k=self.top_k, namespace=self.namespace)
        return [
            {
                "page_content": m.content,
                "metadata": {
                    "id": m.id,
                    "type": m.type.name,
                    "score": m.score,
                    "importance": m.importance,
                    "namespace": m.namespace,
                },
            }
            for m in results
        ]

    async def aget_relevant_documents(self, query: str) -> List[Dict[str, Any]]:
        return self.get_relevant_documents(query)
