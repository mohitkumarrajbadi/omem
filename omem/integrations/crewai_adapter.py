"""CrewAI integration adapter for OMem.

Provides a small wrapper layer for CrewAI / AutoGen agents to use OMem as a
shared workspace memory substrate with agent-level namespaces, broadcasting,
and retrieval filtering.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..api import OMem
from ..types import Memory


class OMemCrewAIAdapter:
    """Adapter exposing OMem to CrewAI or AutoGen agents."""

    def __init__(
        self,
        omem: Optional[OMem] = None,
        workspace: str = "default",
        default_agent: str = "agent",
    ):
        self.omem = omem or OMem()
        self.workspace = workspace
        self.default_agent = default_agent

    def _namespace(self, agent: Optional[str] = None) -> str:
        if agent:
            return f"{self.workspace}/{agent}"
        return self.workspace

    def store(
        self,
        agent: Optional[str],
        content: str,
        importance: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        agent_name = agent or self.default_agent
        metadata = metadata or {}
        metadata["agent"] = agent_name
        metadata["workspace"] = self.workspace
        return self.omem.add(
            content,
            namespace=self._namespace(agent_name),
            source=f"agent:{agent_name}",
            importance=importance,
            metadata=metadata,
        )

    def recall(
        self,
        query: str,
        agent: Optional[str] = None,
        top_k: int = 5,
        include_workspace: bool = True,
    ) -> List[Memory]:
        if include_workspace:
            return self.omem.recall(query, top_k=top_k, namespace=self.workspace)

        agent_name = agent or self.default_agent
        return self.omem.recall(
            query,
            top_k=top_k,
            namespace=self._namespace(agent_name),
        )

    def broadcast(self, content: str, importance: float = 0.8) -> str:
        return self.omem.add(
            content,
            namespace=self.workspace,
            source="broadcast",
            importance=importance,
        )

    def get_agent_namespaces(self) -> List[str]:
        return [ns for ns in self.omem.namespaces() if ns.startswith(self.workspace)]


__all__ = ["OMemCrewAIAdapter"]
