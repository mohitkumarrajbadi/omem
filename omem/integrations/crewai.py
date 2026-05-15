"""CrewAI / AutoGen integration — shared memory for multi-agent systems.

Usage::

    from omem.integrations.crewai import OMemSharedMemory

    shared = OMemSharedMemory(workspace="project-alpha")
    shared.store("research_agent", "Found that market grew 15% in Q3")
    shared.store("planner_agent", "Set quarterly target to 20%")
    results = shared.recall("market growth target", agent="planner_agent")

Works standalone — no CrewAI or AutoGen required.
"""

from typing import Any, Dict, List, Optional

from ..api import OMem
from ..types import Memory


class OMemSharedMemory:
    """Shared memory layer for multi-agent AI systems.

    Each agent writes to its own namespace within a shared workspace.
    All agents can read from any namespace or the entire workspace.
    """

    def __init__(
        self,
        workspace: str = "default",
        omem: Optional[OMem] = None,
    ):
        self.workspace = workspace
        self.omem = omem or OMem()

    def _ns(self, agent: Optional[str] = None) -> str:
        if agent:
            return f"{self.workspace}/{agent}"
        return self.workspace

    def store(
        self,
        agent: str,
        content: str,
        importance: Optional[float] = None,
        metadata: Optional[Dict] = None,
    ) -> str:
        """Agent stores a memory in its namespace within the workspace."""
        meta = metadata or {}
        meta["agent"] = agent
        meta["workspace"] = self.workspace
        return self.omem.add(
            content,
            namespace=self._ns(agent),
            source=f"agent:{agent}",
            importance=importance,
            metadata=meta,
        )

    def recall(
        self,
        query: str,
        agent: Optional[str] = None,
        top_k: int = 5,
    ) -> List[Memory]:
        """Recall memories.

        If agent is given, recall from that agent's namespace only.
        If None, recall from the entire workspace (all agents).
        """
        if agent:
            return self.omem.recall(query, top_k=top_k, namespace=self._ns(agent))
        else:
            # Search across all agent namespaces in this workspace
            all_results = []
            for ns in self.omem.namespaces():
                if ns.startswith(self.workspace):
                    results = self.omem.recall(query, top_k=top_k, namespace=ns)
                    all_results.extend(results)
            all_results.sort(key=lambda m: m.score, reverse=True)
            return all_results[:top_k]

    def broadcast(self, content: str, importance: float = 0.8) -> str:
        """Store a memory visible to all agents in the workspace."""
        return self.omem.add(
            content,
            namespace=self._ns(),
            source="broadcast",
            importance=importance,
        )

    def reflect_workspace(self) -> List[Memory]:
        """Generate reflections across the entire workspace."""
        return self.omem.reflect(namespace=None)

    def compress_workspace(self) -> Dict:
        """Compress memories across the entire workspace."""
        return self.omem.compress(namespace=None)

    def stats(self) -> Dict[str, Any]:
        """Get workspace-level stats."""
        all_stats = self.omem.stats()
        workspace_ns = [
            ns for ns in all_stats["namespaces"] if ns.startswith(self.workspace)
        ]
        return {
            "workspace": self.workspace,
            "agents": [ns.split("/")[-1] for ns in workspace_ns if "/" in ns],
            "namespaces": workspace_ns,
            "total_memories": all_stats["total"],
        }
