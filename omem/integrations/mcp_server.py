"""OMem MCP Server — Coding Agent Edition.

Optimized memory layer for Cursor, Claude Code, and any MCP-compatible coding agent.
Provides persistent context across sessions: architectural decisions, PR history,
codebase structure, and bug fixes — the exact knowledge that makes an agent behave
like a senior engineer who has been on the project for months.

Core tools (coding-agent wedge):
  remember_decision      — Store ADRs, tech choices, tradeoffs
  recall_decisions       — Retrieve past architectural decisions
  remember_pr_context    — Persist PR metadata, review notes, merge rationale
  recall_pr_context      — Recall PR history for a file or feature
  remember_bug_fix       — Log root cause + fix for recurring issues
  recall_bugs            — Surface past fixes before repeating mistakes
  query_codebase         — Semantic AST search (preferred over grep)
  ingest_codebase        — One-time full index of a repository
  sync_codebase          — Incremental post-commit sync via git diff

General tools:
  remember, recall, reflect, maintain, resolve_conflict
  remember_action, recall_action

Auto-namespace: detects .git root → zero-config project isolation.
"""

import logging
import os
import time
from typing import Any, Dict, List, Optional

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
        content_snippet = m.content[:120].strip()
        if len(m.content) > 120:
            content_snippet += "..."
        line = f"- [{m.type.name}] ({m.importance:.2f}) {content_snippet}"
        lines.append(line)

    return "\n".join(lines)


def _coding_namespace() -> str:
    """Return the coding-agent namespace (project root basename)."""
    return get_project_namespace()


def _memory_to_dict(m: Any) -> Dict[str, Any]:
    """Serialize a Memory object to a lean JSON-serializable dict."""
    return {
        "id": m.id,
        "content": m.content,
        "type": m.type.name,
        "importance": round(m.importance, 3),
        "score": round(getattr(m, "score", m.importance), 4),
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(m.timestamp)),
        "metadata": m.metadata,
    }


# --- TOOLS ---


@mcp.tool()
def remember(
    content: str,
    importance: Optional[float] = None,
    is_global: bool = False,
    metadata: Optional[Dict[str, Any]] = None,
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
    context_type: Optional[str] = None,
    time_range: Optional[str] = None,
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
    steps: List[str],
    target_url: str = "",
    args: Optional[Dict[str, str]] = None,
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


# ─────────────────────────────────────────────────────────────────────────────
# CODING AGENT TOOLS — architectural decisions, PR context, bug knowledge
# ─────────────────────────────────────────────────────────────────────────────


@mcp.tool()
def remember_decision(
    title: str,
    decision: str,
    rationale: str,
    alternatives: Optional[List[str]] = None,
    files_affected: Optional[List[str]] = None,
    pr_url: Optional[str] = None,
    importance: float = 0.9,
):
    """Store an architectural decision record (ADR) in persistent memory.

    Use this whenever you make a significant technical choice so that future
    sessions can recall the rationale without re-deriving it.

    Args:
        title: Short name for the decision (e.g. 'Use PostgreSQL over SQLite for prod').
        decision: The chosen option in one sentence.
        rationale: Why this was chosen — the key factors and tradeoffs.
        alternatives: Other options that were considered and rejected.
        files_affected: Source file paths most impacted by this decision.
        pr_url: Link to the PR or issue where this was discussed.
        importance: Criticality weight (0.0–1.0). Defaults to 0.9 (high).
    """
    namespace = _coding_namespace()
    content = f"[ADR] {title}\nDecision: {decision}\nRationale: {rationale}"
    meta: Dict[str, Any] = {
        "kind": "architectural_decision",
        "title": title,
        "decision": decision,
        "rationale": rationale,
        "alternatives": alternatives or [],
        "files_affected": files_affected or [],
        "pr_url": pr_url or "",
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    mem_id = omem.add(
        content,
        mem_type=MemoryType.SEMANTIC,
        importance=importance,
        namespace=namespace,
        source="coding_agent",
        metadata=meta,
        force=True,
    )
    return {
        "status": "stored",
        "memory_id": mem_id,
        "title": title,
        "namespace": namespace,
        "tip": "Use recall_decisions to surface this in future sessions.",
    }


@mcp.tool()
def recall_decisions(query: str, k: int = 5):
    """Retrieve past architectural decisions relevant to a topic.

    Always call this before making a significant technical choice — you may
    have already evaluated the options in a previous session.

    Args:
        query: Describe the decision context (e.g. 'database choice', 'auth strategy').
        k: Max results to return.
    """
    namespace = _coding_namespace()
    results = omem.recall(
        query,
        k=k,
        context_type="architecture",
        namespace=namespace,
        mode="coding",
    )
    decisions = [
        m for m in results
        if m.metadata.get("kind") == "architectural_decision"
    ]
    if not decisions:
        decisions = results

    return {
        "query": query,
        "decisions": [_memory_to_dict(m) for m in decisions],
        "total": len(decisions),
        "namespace": namespace,
        "hint": (
            "No past decisions found." if not decisions
            else f"Found {len(decisions)} relevant ADR(s). Review before proceeding."
        ),
    }


@mcp.tool()
def remember_pr_context(
    pr_number: int,
    title: str,
    description: str,
    files_changed: Optional[List[str]] = None,
    review_notes: Optional[str] = None,
    merge_decision: Optional[str] = None,
    author: Optional[str] = None,
    importance: float = 0.8,
):
    """Store the context of a pull request for future recall.

    Enables agents to answer 'why was this changed?' or 'what did PR #42 do?'
    without reading the entire git log.

    Args:
        pr_number: GitHub / GitLab PR number.
        title: PR title.
        description: What this PR does and why.
        files_changed: Key files modified in the PR.
        review_notes: Important review comments or requested changes.
        merge_decision: Outcome — 'merged', 'closed', 'reverted', etc.
        author: Author username.
        importance: Memory weight (0.0–1.0).
    """
    namespace = _coding_namespace()
    content = f"[PR #{pr_number}] {title}\n{description}"
    meta: Dict[str, Any] = {
        "kind": "pr_context",
        "pr_number": pr_number,
        "title": title,
        "description": description,
        "files_changed": files_changed or [],
        "review_notes": review_notes or "",
        "merge_decision": merge_decision or "unknown",
        "author": author or "",
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    mem_id = omem.add(
        content,
        mem_type=MemoryType.SEMANTIC,
        importance=importance,
        namespace=namespace,
        source="coding_agent",
        metadata=meta,
        force=True,
    )
    return {
        "status": "stored",
        "memory_id": mem_id,
        "pr_number": pr_number,
        "namespace": namespace,
    }


@mcp.tool()
def recall_pr_context(query: str, k: int = 5, pr_number: Optional[int] = None):
    """Retrieve stored PR context for a feature, file, or topic.

    Args:
        query: What you want to know ('changes to auth module', 'performance PRs').
        k: Max results.
        pr_number: If set, filters to this specific PR number.
    """
    namespace = _coding_namespace()
    results = omem.recall(
        query,
        k=k * 2,
        context_type="decisions",
        namespace=namespace,
        mode="coding",
    )
    prs = [m for m in results if m.metadata.get("kind") == "pr_context"]
    if pr_number is not None:
        prs = [m for m in prs if m.metadata.get("pr_number") == pr_number]
    prs = prs[:k]

    if not prs:
        prs = results[:k]

    return {
        "query": query,
        "pr_number_filter": pr_number,
        "results": [_memory_to_dict(m) for m in prs],
        "total": len(prs),
        "namespace": namespace,
    }


@mcp.tool()
def remember_bug_fix(
    description: str,
    root_cause: str,
    fix: str,
    files: Optional[List[str]] = None,
    commit_hash: Optional[str] = None,
    error_signature: Optional[str] = None,
    importance: float = 0.88,
):
    """Persist a bug fix with root cause analysis for future recall.

    Prevents agents from re-investigating the same issue. If you've seen this
    error or pattern before, OMem will surface the prior fix immediately.

    Args:
        description: Human-readable description of the bug.
        root_cause: What caused the issue at a technical level.
        fix: How it was resolved — the actual change made.
        files: Files that were modified to fix the issue.
        commit_hash: Git commit that introduced or fixed the bug.
        error_signature: Key error string / stack frame for pattern matching.
        importance: Memory weight (0.0–1.0).
    """
    namespace = _coding_namespace()
    content = (
        f"[BUG FIX] {description}\n"
        f"Root cause: {root_cause}\n"
        f"Fix: {fix}"
    )
    if error_signature:
        content += f"\nError signature: {error_signature}"

    meta: Dict[str, Any] = {
        "kind": "bug_fix",
        "description": description,
        "root_cause": root_cause,
        "fix": fix,
        "files": files or [],
        "commit_hash": commit_hash or "",
        "error_signature": error_signature or "",
        "recorded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    mem_id = omem.add(
        content,
        mem_type=MemoryType.EPISODIC,
        importance=importance,
        namespace=namespace,
        source="coding_agent",
        metadata=meta,
        force=True,
    )
    return {
        "status": "stored",
        "memory_id": mem_id,
        "description": description,
        "namespace": namespace,
        "tip": "Use recall_bugs before investigating a new error.",
    }


@mcp.tool()
def recall_bugs(query: str, k: int = 5, error_signature: Optional[str] = None):
    """Search for past bug fixes matching a symptom, error message, or module.

    ALWAYS call this before starting a debugging session. You may have already
    fixed this exact issue in a prior session.

    Args:
        query: Describe the symptom (e.g. 'KeyError in auth module', 'payment retry').
        k: Max results.
        error_signature: Exact error string fragment for precise matching.
    """
    namespace = _coding_namespace()
    search_query = query
    if error_signature:
        search_query = f"{query} {error_signature}"

    results = omem.recall(
        search_query,
        k=k * 2,
        context_type="bugs",
        namespace=namespace,
        mode="coding",
    )
    bugs = [m for m in results if m.metadata.get("kind") == "bug_fix"]
    if not bugs:
        bugs = results
    bugs = bugs[:k]

    return {
        "query": query,
        "fixes_found": len(bugs),
        "results": [_memory_to_dict(m) for m in bugs],
        "namespace": namespace,
        "alert": (
            f"Found {len(bugs)} prior fix(es) — review before investigating."
            if bugs else
            "No prior fixes found. This may be a new issue."
        ),
    }


@mcp.tool()
def get_codebase_summary(include_decisions: bool = True, include_recent_prs: bool = True):
    """Get a high-level summary of the project's architectural state.

    Returns the most important architectural decisions, recent PR context,
    and a codebase stats overview. Call at the start of a new session to
    re-orient quickly without re-reading the codebase.

    Args:
        include_decisions: Include recent ADRs (default True).
        include_recent_prs: Include recent PR context (default True).
    """
    namespace = _coding_namespace()
    summary: Dict[str, Any] = {"namespace": namespace, "project": namespace}

    if include_decisions:
        decisions = omem.recall(
            "architectural decisions design patterns",
            k=5,
            context_type="architecture",
            namespace=namespace,
            mode="coding",
        )
        summary["recent_decisions"] = [
            _memory_to_dict(m) for m in decisions
            if m.metadata.get("kind") == "architectural_decision"
        ]

    if include_recent_prs:
        prs = omem.recall(
            "pull request changes feature",
            k=5,
            context_type="decisions",
            namespace=namespace,
            mode="coding",
        )
        summary["recent_prs"] = [
            _memory_to_dict(m) for m in prs
            if m.metadata.get("kind") == "pr_context"
        ]

    try:
        stats = omem.stats()
        summary["memory_stats"] = {
            "total_memories": stats.get("total", 0),
            "active": stats.get("active", 0),
            "by_type": stats.get("by_type", {}),
        }
    except Exception:
        summary["memory_stats"] = {}

    summary["tip"] = (
        "Start with query_codebase to navigate code. "
        "Use recall_decisions before making tech choices. "
        "Use recall_bugs before debugging."
    )
    return summary


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


@mcp.resource("omem://decisions")
def get_architectural_decisions():
    """Returns all stored architectural decision records (ADRs) for this project."""
    namespace = get_project_namespace()
    mems = omem.all(namespace=namespace)
    decisions = [
        m for m in mems
        if m.metadata.get("kind") == "architectural_decision" and m.active
    ]
    decisions.sort(key=lambda m: m.importance, reverse=True)
    return {
        "project": namespace,
        "count": len(decisions),
        "decisions": [
            {
                "title": m.metadata.get("title", m.content[:60]),
                "decision": m.metadata.get("decision", ""),
                "rationale": m.metadata.get("rationale", ""),
                "alternatives": m.metadata.get("alternatives", []),
                "files_affected": m.metadata.get("files_affected", []),
                "pr_url": m.metadata.get("pr_url", ""),
                "recorded_at": m.metadata.get("recorded_at", ""),
                "importance": round(m.importance, 3),
            }
            for m in decisions[:20]
        ],
    }


@mcp.resource("omem://pr_history")
def get_pr_history():
    """Returns stored PR context records for this project, newest first."""
    namespace = get_project_namespace()
    mems = omem.all(namespace=namespace)
    prs = [m for m in mems if m.metadata.get("kind") == "pr_context" and m.active]
    prs.sort(key=lambda m: m.timestamp, reverse=True)
    return {
        "project": namespace,
        "count": len(prs),
        "pull_requests": [
            {
                "pr_number": m.metadata.get("pr_number"),
                "title": m.metadata.get("title", ""),
                "description": m.metadata.get("description", "")[:200],
                "files_changed": m.metadata.get("files_changed", []),
                "merge_decision": m.metadata.get("merge_decision", ""),
                "author": m.metadata.get("author", ""),
                "recorded_at": m.metadata.get("recorded_at", ""),
            }
            for m in prs[:20]
        ],
    }


@mcp.resource("omem://bug_fixes")
def get_bug_fixes():
    """Returns stored bug fix records for this project."""
    namespace = get_project_namespace()
    mems = omem.all(namespace=namespace)
    bugs = [m for m in mems if m.metadata.get("kind") == "bug_fix" and m.active]
    bugs.sort(key=lambda m: m.importance, reverse=True)
    return {
        "project": namespace,
        "count": len(bugs),
        "fixes": [
            {
                "description": m.metadata.get("description", ""),
                "root_cause": m.metadata.get("root_cause", ""),
                "fix": m.metadata.get("fix", ""),
                "files": m.metadata.get("files", []),
                "error_signature": m.metadata.get("error_signature", ""),
                "recorded_at": m.metadata.get("recorded_at", ""),
            }
            for m in bugs[:20]
        ],
    }


# --- PROMPTS ---


@mcp.prompt("omem/onboarding")
def onboarding_prompt():
    """Instruction for Claude / Cursor on how to effectively use OMem for coding."""
    return (
        "You have access to OMem — a persistent cognitive memory engine purpose-built for "
        "coding agents. It gives you the institutional knowledge of a senior engineer who "
        "has been on this project for months, across every session.\n\n"

        "═══ SESSION START CHECKLIST ═══\n"
        "1. Call `get_codebase_summary` to re-orient (ADRs, recent PRs, stats).\n"
        "2. If first time on this project: call `ingest_codebase` once to index the AST.\n"
        "3. Before debugging: call `recall_bugs` — the fix may already be known.\n"
        "4. Before a tech choice: call `recall_decisions` — you may have decided this before.\n\n"

        "═══ CODEBASE NAVIGATION ═══\n"
        "NEVER use grep or find to navigate code. Use `query_codebase` instead:\n"
        "  • 'auth token refresh logic'  → returns auth/session.py:142-178 + callers\n"
        "  • 'database connection pool'  → returns the module + dependency graph\n"
        "  • 'class that handles retries'→ returns exact class + file + line range\n"
        "After code changes: call `sync_codebase` to update the index incrementally.\n\n"

        "═══ WHAT TO PERSIST ═══\n"
        "• Architectural decisions   → `remember_decision`  (why PostgreSQL, why GraphQL, etc.)\n"
        "• PR context               → `remember_pr_context` (what changed, why, review notes)\n"
        "• Bug fixes                → `remember_bug_fix`    (root cause + fix, prevent recurrence)\n"
        "• General facts            → `remember`            (any important project knowledge)\n\n"

        "═══ RULES ═══\n"
        "1. Always recall before solving — check what you already know.\n"
        "2. Store decisions immediately after making them — don't rely on chat history.\n"
        "3. Tag bug fixes with the error signature for precise future matching.\n"
        "4. Call `maintain` when idle to consolidate and prune stale memories.\n"
        "5. Do NOT store trivial facts — focus on knowledge that would take >5 min to re-derive."
    )


@mcp.prompt("omem/coding_agent")
def coding_agent_prompt():
    """Advanced system prompt for coding agents with full OMem integration."""
    project = get_project_namespace()
    return (
        f"Project: {project}\n\n"
        "You are a coding agent with persistent memory across sessions via OMem.\n\n"
        "MEMORY TOOLS AVAILABLE:\n"
        "  query_codebase(query)           — navigate code semantically\n"
        "  recall_decisions(query)         — past architectural choices\n"
        "  recall_bugs(query)              — prior bug fixes\n"
        "  recall_pr_context(query)        — PR history\n"
        "  recall(query, mode='coding')    — general project knowledge\n\n"
        "STORAGE TOOLS:\n"
        "  remember_decision(...)          — store ADR\n"
        "  remember_pr_context(...)        — store PR metadata\n"
        "  remember_bug_fix(...)           — store root cause + fix\n"
        "  remember(content)               — store general knowledge\n\n"
        "RESOURCES (read-only snapshots):\n"
        "  omem://decisions                — all ADRs\n"
        "  omem://pr_history               — PR context\n"
        "  omem://bug_fixes                — known bug fixes\n"
        "  omem://recent                   — recent memories\n\n"
        "Start every task by checking what OMem already knows. "
        "End every task by persisting new knowledge."
    )


if __name__ == "__main__":
    _require_mcp()
    mcp.run(transport="stdio")
