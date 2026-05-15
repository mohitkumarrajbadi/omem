"""OMem MCP Server Integration.

Provides a Model Context Protocol (MCP) server that exposes OMem's cognitive engine
to Claude Code and other MCP-compatible agents.

Features:
- Natural language tools: remember, recall, reflect, maintain.
- Advanced retrieval: context_type and time_range filtering.
- Truth Maintenance: resolve_conflict tool.
- Auto-namespacing: Detects project context for zero-config isolation.
"""

import os
import time
import logging
from typing import Optional, List, Dict, Any

from ..api import OMem
from ..types import MemoryType

# Setup logger
logger = logging.getLogger(__name__)

try:
    from mcp.server.fastmcp import FastMCP
    _HAS_MCP = True
except ImportError:
    FastMCP = None  # type: ignore[assignment,misc]
    _HAS_MCP = False


def _require_mcp() -> None:
    if not _HAS_MCP:
        raise ImportError(
            "The 'mcp' package is required to run the OMem MCP server. "
            "Install it with: pip install omem-os[mcp]"
        )


class _NoOpMCP:
    """Stub used when the mcp package is not installed.

    Provides silent no-op versions of @tool, @resource, and @prompt so that
    this module can be imported and its functions called directly without the
    MCP runtime.  Only mcp.run() raises — that requires the real package.
    """

    def tool(self, *args, **kwargs):
        def decorator(f):
            return f
        return decorator

    def resource(self, *args, **kwargs):
        def decorator(f):
            return f
        return decorator

    def prompt(self, *args, **kwargs):
        def decorator(f):
            return f
        return decorator

    def run(self, *args, **kwargs):
        _require_mcp()


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


# Initialize OMem instance (always available)
omem = OMem()

# MCP instance — real server when mcp is installed, silent stub otherwise.
# The stub lets this module be imported and its functions called without mcp,
# which is required for tests and direct Python usage.
if _HAS_MCP:
    mcp = FastMCP("OMem Cognitive Engine")
else:
    mcp = _NoOpMCP()  # type: ignore[assignment]


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
def query_codebase(query: str, depth: int = 2, top_k: int = 5):
    """Search the Project Memory (codebase graph) for relevant code symbols.

    This is the PREFERRED way to navigate a codebase. Instead of grepping files
    or reading large directories, call this tool with a natural-language description
    of what you are looking for. It returns the exact file paths, line numbers,
    and architectural context — just like a senior engineer would recall.

    Args:
        query: Natural-language description of what you need.
               Examples:
               - "auth token refresh logic"
               - "class that parses AST nodes"
               - "where is the database connection pooling?"
        depth: Graph traversal depth for related context (default 2).
               Higher values include more dependency and caller context.
        top_k: Maximum number of primary results to return (default 5).

    Returns:
        A dict with a list of ``results``, each containing:
        - ``symbol_id``: Stable hierarchical identifier (e.g. ``auth.jwt.generate_token``).
        - ``file_path``: Absolute path to the source file.
        - ``start_line`` / ``end_line``: Exact line range in the file.
        - ``type``: Symbol type (module / class / function / method).
        - ``content``: Compressed signature + docstring.
        - ``related``: List of dependency / caller symbols with relationship type.
    """
    # Always use "project" namespace for code symbols for consistent cross-call identity.
    namespace = "project"
    try:
        raw = omem.query_code(
            query,
            namespace=namespace,
            context_depth=depth,
            top_k=top_k,
            include_dependencies=True,
            include_callers=True,
        )
        clean = []
        for r in raw:
            clean.append({
                "symbol_id": r.get("symbol_id"),
                "file_path": r.get("file_path"),
                "start_line": r.get("start_line"),
                "end_line": r.get("end_line"),
                "type": r.get("type"),
                "content": r.get("content"),
                "score": round(float(r.get("score", 0)), 4),
                "importance": round(float(r.get("importance", 0)), 4),
                "related": [
                    {
                        "symbol_id": rel.get("symbol_id"),
                        "type": rel.get("type"),
                        "file_path": rel.get("file_path"),
                    }
                    for rel in r.get("related", [])
                ],
            })
        return {
            "namespace": namespace,
            "query": query,
            "total": len(clean),
            "results": clean,
        }
    except Exception as e:
        return {"error": str(e), "query": query, "results": []}


@mcp.tool()
def sync_codebase(path: str = "."):
    """Incrementally sync the Project Memory after code changes.

    Run this after modifying, adding, or deleting Python files so that OMem
    stays up to date without a full re-ingest. Uses ``git diff`` under the
    hood, so only changed files are re-parsed — takes milliseconds.

    Args:
        path: Root directory of the project to sync (default: current directory).

    Returns:
        A status dict with the number of symbols updated.
    """
    try:
        count = omem.sync_project(path, namespace="project")
        return {
            "status": "ok",
            "namespace": "project",
            "path": path,
            "symbols_updated": count,
            "message": f"Synced {count} symbols via git diff.",
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@mcp.tool()
def ingest_codebase(path: str = "."):
    """Perform a full baseline ingest of a Python codebase into Project Memory.

    Use this the first time OMem encounters a new project, or after a major
    restructure. It walks the entire repository, parses AST symbols, and
    builds the code graph. For incremental updates use ``sync_codebase`` instead.

    Args:
        path: Root directory of the project to ingest (default: current directory).

    Returns:
        A status dict with the number of symbols indexed.
    """
    try:
        count = omem.ingest_project(path, namespace="project")
        return {
            "status": "ok",
            "namespace": "project",
            "path": path,
            "symbols_indexed": count,
            "message": (
                f"Indexed {count} symbols. "
                "Use query_codebase to navigate the repository."
            ),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}



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
        "You have access to OMem, a persistent cognitive memory engine with built-in "
        "codebase intelligence. Unlike static metadata, OMem manages short-term vs "
        "long-term importance, resolves contradictions, and understands code structure.\n\n"
        "═══ CODEBASE NAVIGATION (most important) ═══\n"
        "NEVER use grep, find, or recursive file search to navigate code.\n"
        "Instead, use `query_codebase` with a natural-language query:\n"
        "  • 'auth token refresh logic'     → returns auth/session.py:142-178\n"
        "  • 'class that parses AST nodes'  → returns the exact class + file\n"
        "  • 'database connection pooling'  → returns the module + dependencies\n\n"
        "WORKFLOW:\n"
        "1. **First run** (new project): call `ingest_codebase` once to index the repo.\n"
        "2. **Navigate**: use `query_codebase` to jump to exact files + lines.\n"
        "3. **After changes**: call `sync_codebase` to update the graph (uses git diff).\n\n"
        "═══ GENERAL MEMORY HABITS ═══\n"
        "1. **Recall first**: Use `recall` before solving complex tasks.\n"
        "2. **Remember decisions**: Use `remember` for architectural choices or bug fixes.\n"
        "3. **Reflect & Maintain**: Occasionally use `reflect` or `maintain`.\n"
        "4. **Summarize**: Use `summarize_state` for a birds-eye project overview.\n\n"
        "Do not over-use memory for trivial things; focus on 'knowledge debt' reduction."
    )


if __name__ == "__main__":
    _require_mcp()
    mcp.run(transport="stdio")
