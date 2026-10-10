"""First-run story: a wrong decision, and the memory that caused it.

The same three records are what ``omem init`` seeds, what ``omem demo`` prints,
and what the MCP ``lineage`` tool returns. The console first-run thread uses
the same ids and sentences.
"""

from __future__ import annotations

import os
import shutil
import sys
import time
from typing import Any, Dict, List, Optional

DEMO_NAMESPACE = "demo"
STALE_ID = "demo-stale-mongodb"
LATER_ID = "demo-later-postgres"
ACTION_ID = "demo-action-chose-mongodb"

STALE_TEXT = "Production database is MongoDB. Do not use Postgres."
LATER_TEXT = "Decision: PostgreSQL for production, not MongoDB."
ACTION_TEXT = "Agent decision: chose MongoDB for production."

STORY_QUERY = "which database should production use"

# Stale fact is older and more important, so importance can beat recency.
_STALE_AGE_S = 30 * 24 * 3600
_LATER_AGE_S = 24 * 3600
_STALE_IMPORTANCE = 0.95
_LATER_IMPORTANCE = 0.55
_ACTION_IMPORTANCE = 0.80


def story_ids() -> List[str]:
    return [STALE_ID, LATER_ID, ACTION_ID]


def story_present(omem: Any) -> bool:
    return all(omem.get(mid) is not None for mid in story_ids())


def seed_story(omem: Any, *, now: Optional[float] = None) -> bool:
    """Insert the three story memories if any are missing.

    Returns True when at least one record was written.
    """
    if story_present(omem):
        return False

    clock = time.time() if now is None else now
    specs = (
        (
            STALE_ID,
            STALE_TEXT,
            _STALE_IMPORTANCE,
            clock - _STALE_AGE_S,
            {
                "story": "five_minute",
                "role": "causing_memory",
            },
        ),
        (
            LATER_ID,
            LATER_TEXT,
            _LATER_IMPORTANCE,
            clock - _LATER_AGE_S,
            {
                "story": "five_minute",
                "role": "losing_memory",
            },
        ),
        (
            ACTION_ID,
            ACTION_TEXT,
            _ACTION_IMPORTANCE,
            clock,
            {
                "story": "five_minute",
                "role": "wrong_decision",
                "caused_by": STALE_ID,
                "lost": LATER_ID,
            },
        ),
    )
    wrote = False
    for mem_id, content, importance, ts, metadata in specs:
        if omem.get(mem_id) is not None:
            continue
        omem.add(
            content,
            importance=importance,
            namespace=DEMO_NAMESPACE,
            source="demo",
            force=True,
            memory_id=mem_id,
            metadata=metadata,
        )
        _stamp(omem, mem_id, ts)
        wrote = True
    return wrote


def lineage_report(omem: Any, query: str = STORY_QUERY) -> Dict[str, Any]:
    """Return the decision, the memory that caused it, and the one that lost."""
    seed_story(omem)
    explanations = omem.inspect(query, top_k=5, namespace=DEMO_NAMESPACE)
    by_id = {e.memory_id: e for e in explanations}
    rank = {e.memory_id: i + 1 for i, e in enumerate(explanations)}

    caused = _node(omem, STALE_ID, by_id.get(STALE_ID), rank.get(STALE_ID))
    lost = _node(omem, LATER_ID, by_id.get(LATER_ID), rank.get(LATER_ID))
    decision = _node(omem, ACTION_ID, by_id.get(ACTION_ID), rank.get(ACTION_ID))
    decision["caused_by"] = STALE_ID
    decision["lost"] = LATER_ID

    return {
        "story": "wrong_decision",
        "namespace": DEMO_NAMESPACE,
        "query": query,
        "decision": decision,
        "caused_by": caused,
        "lost": lost,
        "nodes": [decision, caused, lost],
    }


def mcp_config(
    db_path: str,
    *,
    namespace: Optional[str] = DEMO_NAMESPACE,
    mode: str = "auto",
) -> Dict[str, Any]:
    """One MCP server object. ``command`` is the resolved ``omem`` binary."""
    path = os.path.expanduser(db_path)
    args = ["serve", "--db-path", path, "--mode", mode or "auto"]
    if namespace not in (None, "", "auto"):
        args.extend(["--namespace", str(namespace)])
    return {
        "mcpServers": {
            "omem": {
                "command": resolve_omem_bin(),
                "args": args,
            }
        }
    }


def resolve_omem_bin() -> str:
    found = shutil.which("omem")
    if found:
        return found
    argv0 = sys.argv[0] if sys.argv else ""
    if argv0 and os.path.basename(argv0) in {"omem", "omem.exe"}:
        return os.path.abspath(argv0)
    return "omem"


def merge_cursor_mcp(block: Dict[str, Any], path: Optional[str] = None) -> str:
    """Merge the omem server into Cursor's mcp.json. Other servers stay."""
    import json

    target = path or os.path.expanduser("~/.cursor/mcp.json")
    parent = os.path.dirname(target)
    if parent:
        os.makedirs(parent, exist_ok=True)
    existing: Dict[str, Any] = {}
    if os.path.exists(target):
        with open(target, "r", encoding="utf-8") as fh:
            raw = fh.read().strip()
        if raw:
            existing = json.loads(raw)
    servers = existing.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
    servers["omem"] = block["mcpServers"]["omem"]
    existing["mcpServers"] = servers
    with open(target, "w", encoding="utf-8") as fh:
        json.dump(existing, fh, indent=2)
        fh.write("\n")
    return target


def _stamp(omem: Any, memory_id: str, timestamp: float) -> None:
    mem = omem.get(memory_id)
    if mem is None:
        return
    mem.timestamp = timestamp
    if hasattr(mem, "valid_from"):
        mem.valid_from = timestamp
    if hasattr(mem, "freshness"):
        mem.freshness = timestamp
    brain = omem.brain
    brain.kv.set(memory_id, mem)
    if hasattr(brain, "write_buffer"):
        brain.write_buffer.enqueue(mem)
        brain.write_buffer.flush()
    elif hasattr(brain, "backend") and hasattr(brain.backend, "save"):
        brain.backend.save(mem)


def _node(omem: Any, memory_id: str, explanation: Any, rank: Optional[int]) -> Dict[str, Any]:
    mem = omem.get(memory_id)
    content = mem.content if mem is not None else ""
    importance = float(mem.importance) if mem is not None else 0.0
    return {
        "id": memory_id,
        "content": content,
        "importance": round(importance, 3),
        "rank": rank,
        "why": _why(explanation, importance),
    }


def _why(explanation: Any, importance: float) -> str:
    if explanation is None:
        return (
            f"not in the top recall; stored importance {importance:.2f} "
            "(recency was not scored for this row)"
        )
    imp = float(explanation.importance_score)
    rec = float(explanation.recency_score)
    final = float(explanation.final_score)
    winner = "importance" if imp >= rec else "recency"
    return (
        f"{winner} decided the rank "
        f"(importance {imp:.2f}, recency {rec:.2f}, final {final:.2f})"
    )
