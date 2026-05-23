"""OMem MCP Server Integration.

Provides a Model Context Protocol (MCP) server that exposes OMem's cognitive engine
to Claude Code and other MCP-compatible agents.

Features:
- Natural language tools: remember, recall, reflect, maintain.
- Advanced retrieval: context_type and time_range filtering.
- Truth Maintenance: resolve_conflict tool.
- Auto-namespacing: Detects project context for zero-config isolation.
"""

import logging
import os
import time
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP

from ..api import OMem
from ..types import MemoryType

# Setup logger
logger = logging.getLogger(__name__)


# ── ToolSnippet schema (v1.0) ──
# Structured metadata stored inside PROCEDURAL memories.
# Enables the AI to recall and re-execute multi-step computer actions.
class ToolSnippet:
    """Typed container for an actionable procedural memory."""

    def __init__(
        self,
        tool: str,
        steps: List[str],
        target_url: str = "",
        args: Optional[Dict[str, str]] = None,
        description: str = "",
    ):
        self.tool = tool  # "browser_use" | "bash" | "python"
        self.steps = steps  # Ordered list of action strings
        self.target_url = target_url  # Entry URL (for browser automation)
        self.args = args or {}  # Named parameters the caller must fill in
        self.description = description

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool": self.tool,
            "steps": self.steps,
            "target_url": self.target_url,
            "args": self.args,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "ToolSnippet":
        return cls(
            tool=d.get("tool", "bash"),
            steps=d.get("steps", []),
            target_url=d.get("target_url", ""),
            args=d.get("args", {}),
            description=d.get("description", ""),
        )


# Initialize OMem + MCP
# By default, use centralized storage at ~/.omem/brain.db
omem = OMem()
mcp = FastMCP("OMem Cognitive Engine")


def get_project_namespace() -> str:
    """Detect the current project namespace based on directory structure."""
    curr = os.getcwd()
    # 1. Search for .git root
    temp = curr
    while temp != os.path.dirname(temp):
        if os.path.exists(os.path.join(temp, ".git")):
            return os.path.basename(temp)
        temp = os.path.dirname(temp)
    # 2. Fallback to current directory basename
    return os.path.basename(curr)


def format_memory_summary(memories: List[Any]) -> str:
    """Format a list of memories into a compressed string for context injection."""
    if not memories:
        return "No relevant memories found."

    lines = []
    for m in memories:
        # Use content summary if available, or first 120 chars
        content_snippet = m.content[:120].strip()
        if len(m.content) > 120:
            content_snippet += "..."

        line = f"- [{m.type.name}] ({m.importance:.2f}) {content_snippet}"
        lines.append(line)

    return "\n".join(lines)


# --- TOOLS ---


@mcp.tool()
def remember(
    content: str,
    importance: float | None = None,
    is_global: bool = False,
    metadata: dict | None = None,
):
    """Store knowledge in OMem.

    Args:
        content: The fact, decision, or insight to remember.
        importance: How critical this knowledge is (0.0 to 1.0). If null, auto-calculated.
        is_global: If True, this memory is available across ALL projects.
        metadata: Optional structured data to attach.
    """
    namespace = "global" if is_global else get_project_namespace()
    mem_id = omem.add(
        content, importance=importance, namespace=namespace, metadata=metadata
    )
    return f"Memory stored in {namespace} (ID: {mem_id})"


@mcp.tool()
def recall(
    query: str,
    k: int = 5,
    context_type: str | None = None,
    time_range: str | None = None,
    project_only: bool = False,
):
    """Search for relevant memories using semantic RAG.

    Args:
        query: The topic or question to recall info for.
        k: Maximum number of results to return.
        context_type: Optional filter (e.g., 'architecture', 'decisions', 'bugs').
        time_range: Optional filter (e.g., 'today', 'recent', 'last_week').
        project_only: If True, do NOT include global cross-project knowledge.
    """
    namespace = get_project_namespace()
    results = omem.recall(
        query,
        k=k,
        context_type=context_type,
        time_range=time_range,
        namespace=namespace,
        project_only=project_only,
    )

    # Build the structured infra-grade response
    mem_data = []
    for m in results:
        mem_data.append(
            {
                "content": m.content,
                "type": m.type.name,
                "importance": m.importance,
                "reason": f"Matches query '{query}' with importance {m.importance:.2f}",
                "timestamp": time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.gmtime(m.timestamp)
                ),
            }
        )

    return {
        "context": format_memory_summary(results),
        "memories": mem_data,
        "stats": {"total_found": len(results), "project_namespace": namespace},
    }


@mcp.tool()
def reflect(project_only: bool = False):
    """Trigger the OMem reflection engine to generate high-level insights from current knowledge."""
    namespace = get_project_namespace()
    insights = omem.reflect(namespace=namespace if project_only else None)
    if not insights:
        return "Not enough data for new reflections yet."
    return f"Generated {len(insights)} new reflection(s). Use 'recall' to see them."


@mcp.tool()
def maintain():
    """Run the 'Dream' cycle to consolidate, compress, and forget low-value memories.
    Helps keep the context window focused on what matters.
    """
    result = omem.sleep()  # Sleep cycle runs decay -> forget -> consolidation -> vacuum
    return {
        "message": "Memory maintenance complete.",
        "purged": result.get("purged", 0),
        "consolidated": result.get("dream", {}).get("wisdom_count", 0),
        "latency_ms": result.get("elapsed_ms", 0),
    }


@mcp.tool()
def resolve_conflict(query: str):
    """Detect and resolve contradictory memories related to a topic."""
    return omem.resolve_conflict(query)


@mcp.tool()
def remember_action(
    goal: str,
    tool: str,
    steps: list[str],
    target_url: str = "",
    args: dict[str, str] | None = None,
    importance: float = 0.85,
    is_global: bool = False,
):
    """Store an actionable procedure (computer-use automation) in OMem.

    Use this when the AI has learned HOW to perform a multi-step task
    (e.g., pay a bill, fill a form, run a script) so it can be recalled
    and re-executed exactly next time without re-discovery.

    Args:
        goal: A plain-language description of what this action achieves.
              Example: 'Pay electricity bill on bescom.com'
        tool: The execution context. One of:
              'browser_use'  — browser automation steps
              'bash'         — shell commands
              'python'       — Python code snippet
        steps: Ordered list of action strings.
               Browser example: ['goto https://...', 'click #login', 'type {password} into #pwd', 'click #pay']
               Bash example: ['ssh user@host', 'cd /var/app', './deploy.sh']
        target_url: Starting URL (for browser_use only).
        args: Named parameters the caller must supply at runtime.
              Example: {'password': '', 'amount': ''}
        importance: How critical this procedure is (default 0.85 — high).
        is_global: If True, available across ALL projects.
    """
    snippet = ToolSnippet(
        tool=tool,
        steps=steps,
        target_url=target_url,
        args=args or {},
        description=goal,
    )
    namespace = "global" if is_global else get_project_namespace()
    mem_id = omem.add(
        content=goal,
        mem_type=MemoryType.PROCEDURAL,
        importance=importance,
        namespace=namespace,
        source="agent",
        metadata={"snippet": snippet.to_dict()},
        force=True,  # Procedural memories bypass noise gate
    )
    return f"Action procedure stored (ID: {mem_id}): '{goal}'"


@mcp.tool()
def recall_action(goal: str, k: int = 3):
    """Retrieve stored action procedures for a given goal.

    Returns the best matching PROCEDURAL memory with its executable
    ToolSnippet payload — ready for direct execution by computer-use agents.

    Args:
        goal: What you want to accomplish (e.g., 'pay electricity bill').
        k: Max number of candidate procedures to return.
    """
    namespace = get_project_namespace()
    results = omem.recall(
        goal,
        k=k,
        context_type="actions",  # Boosts PROCEDURAL type 2.5×
        namespace=namespace,
    )
    # Also search global namespace
    global_results = omem.recall(
        goal,
        k=k,
        context_type="actions",
        namespace="global",
    )
    all_results = results + [
        m for m in global_results if m.id not in {r.id for r in results}
    ]
    all_results.sort(key=lambda m: m.score, reverse=True)

    actions = []
    for m in all_results[:k]:
        snippet_data = m.metadata.get("snippet")
        actions.append(
            {
                "memory_id": m.id,
                "goal": m.content,
                "importance": m.importance,
                "score": round(m.score, 4),
                "snippet": snippet_data,  # Full ToolSnippet dict or None
                "has_executable": snippet_data is not None,
                "timestamp": time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.gmtime(m.timestamp)
                ),
            }
        )

    if not actions:
        return {
            "found": False,
            "message": f"No action procedures found for '{goal}'. Use remember_action() to store one.",
        }

    return {
        "found": True,
        "best_match": actions[0],
        "alternatives": actions[1:],
        "total": len(actions),
    }


@mcp.tool()
def summarize_state():
    """Provides a high-level summary of the system architecture, key decisions, and constraints."""
    namespace = get_project_namespace()
    return omem.summarize_state(namespace=namespace)


# --- RESOURCES ---


@mcp.resource("omem://recent")
def get_recent_memories():
    """Returns a list of the 20 most recent memories across the current project and global."""
    namespace = get_project_namespace()
    mems = omem.all(namespace=namespace)  # Already filtered by active
    mems.extend(omem.all(namespace="global"))
    mems.sort(key=lambda m: m.timestamp, reverse=True)
    return format_memory_summary(mems[:20])


@mcp.resource("omem://top_insights")
def get_top_insights():
    """Returns high-importance REFLECTION memories generated by OMem."""
    mems = [m for m in omem.all() if m.type.name == "REFLECTION" and m.importance > 0.7]
    mems.sort(key=lambda m: m.importance, reverse=True)
    return format_memory_summary(mems[:10])


@mcp.resource("omem://status")
def get_system_status():
    """Returns real-time health and memory distribution stats."""
    return omem.stats()


@mcp.resource("omem://graph")
def get_knowledge_graph() -> List[Dict[str, Any]]:
    """Returns a summary of the knowledge graph entities."""
    return omem.entities()


# --- PROMPTS ---


@mcp.prompt("omem/onboarding")
def onboarding_prompt():
    """Instruction for Claude on how to effectively use OMem cognitive memory."""
    return (
        "You have access to OMem, a persistent cognitive memory engine. Unlike static metadata, "
        "OMem manages short-term vs long-term importance and resolves contradictions.\n\n"
        "BEST HABITS:\n"
        "1. **Recall first**: Use `recall` before solving complex tasks to remember past decisions or bugs.\n"
        "2. **Remember decisions**: Use `remember` whenever you make an architectural choice or resolve a bug.\n"
        "3. **Reflect & Maintain**: Occasionally use `reflect` or `maintain` to help OMem organize itself.\n"
        "4. **Summarize**: Use `summarize_state` to get a 'birds-eye view' of the project architecture.\n\n"
        "Do not over-use memory for trivial things; focus on 'knowledge debt' reduction."
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
