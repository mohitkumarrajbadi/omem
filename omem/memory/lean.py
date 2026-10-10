"""Compact recall packs — less token bulk for CLI and MCP agents."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from ..types import Memory

DEFAULT_K = 3
DEFAULT_SNIPPET_CHARS = 100
DEFAULT_CONTEXT_CHARS = 480  # ~120 tokens of context blob


def snippet(text: str, max_chars: int = DEFAULT_SNIPPET_CHARS) -> str:
    text = (text or "").strip().replace("\n", " ")
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def approx_tokens(text: str) -> int:
    """Rough token estimate (chars/4) — good enough for CLI budgets."""
    return max(0, (len(text or "") + 3) // 4)


def build_lean_context(
    memories: Sequence[Memory],
    *,
    max_chars: int = DEFAULT_CONTEXT_CHARS,
    snippet_chars: int = DEFAULT_SNIPPET_CHARS,
) -> str:
    """Build a short, labeled context block for LLM injection."""
    if not memories:
        return "No relevant memories found."

    lines: List[str] = []
    used = 0
    for mem in memories:
        ns = getattr(mem, "namespace", "") or ""
        typ = getattr(getattr(mem, "type", None), "name", "?")
        line = f"- [{typ}] ns={ns} | {snippet(mem.content, snippet_chars)}"
        if used + len(line) + 1 > max_chars and lines:
            break
        lines.append(line)
        used += len(line) + 1
    return "\n".join(lines)


def lean_memory_dicts(
    memories: Sequence[Memory],
    *,
    query: str = "",
    snippet_chars: int = DEFAULT_SNIPPET_CHARS,
    full: bool = False,
) -> List[Dict[str, Any]]:
    """Serialize memories for MCP/CLI JSON — snippets by default."""
    import time as _time

    out: List[Dict[str, Any]] = []
    for mem in memories:
        content = mem.content if full else snippet(mem.content, snippet_chars)
        out.append(
            {
                "content": content,
                "type": mem.type.name,
                "namespace": mem.namespace,
                "importance": round(float(mem.importance or 0), 3),
                "score": round(float(getattr(mem, "score", mem.importance) or 0), 4),
                "reason": (
                    f"ns={mem.namespace} match for '{query[:48]}'"
                    if query
                    else f"ns={mem.namespace}"
                ),
                "timestamp": _time.strftime(
                    "%Y-%m-%d %H:%M:%S", _time.gmtime(mem.timestamp)
                ),
                "id": mem.id or "",
            }
        )
    return out


def lean_pack_stats(
    memories: Sequence[Memory],
    context: str,
    *,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    stats: Dict[str, Any] = {
        "total_found": len(memories),
        "context_chars": len(context),
        "approx_tokens": approx_tokens(context),
        "lean": True,
    }
    if extra:
        stats.update(extra)
    return stats


__all__ = [
    "DEFAULT_CONTEXT_CHARS",
    "DEFAULT_K",
    "DEFAULT_SNIPPET_CHARS",
    "approx_tokens",
    "build_lean_context",
    "lean_memory_dicts",
    "lean_pack_stats",
    "snippet",
]
