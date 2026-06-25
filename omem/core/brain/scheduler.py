"""Memory tier scheduler — working → short-term → long-term transitions."""

import time
from typing import Dict, List, Optional

from ...types import Memory, MemoryTier

_STM_PROMOTE_ACCESSES = 3
_STM_MAX_AGE_SECONDS = 3600.0
_LTM_MIN_ACCESSES = 5
_GRAPH_PROMOTE_THRESHOLD = 0.4


def schedule_tier_transitions(
    memories: List[Memory],
    now: Optional[float] = None,
    graph_centralities: Optional[Dict[str, float]] = None,
) -> Dict[str, List[str]]:
    """Promote frequently accessed or graph-central memories through the hierarchy."""
    now = now or time.time()
    promoted: List[str] = []
    archived_candidates: List[str] = []
    centralities = graph_centralities or {}

    for mem in memories:
        if not mem.active:
            continue
        if mem.tier in (MemoryTier.CORE, MemoryTier.INSIGHT, MemoryTier.FORGOTTEN):
            continue

        age = max(now - mem.timestamp, 0.0)
        graph_boost = max(
            (centralities.get(e.lower(), 0.0) for e in getattr(mem, "entities", [])),
            default=0.0,
        )
        effective_accesses = mem.access_count + (1 if graph_boost >= _GRAPH_PROMOTE_THRESHOLD else 0)

        if mem.level == "working":
            if effective_accesses >= _STM_PROMOTE_ACCESSES or age >= _STM_MAX_AGE_SECONDS:
                mem.level = "short_term"
                promoted.append(mem.id)
        elif mem.level == "short_term":
            if effective_accesses >= _LTM_MIN_ACCESSES or graph_boost >= _GRAPH_PROMOTE_THRESHOLD:
                mem.level = "long_term"
                promoted.append(mem.id)
        elif mem.tier == MemoryTier.SENSORY and mem.access_count >= 1:
            mem.tier = MemoryTier.ACTIVE
            mem.level = "short_term"
            promoted.append(mem.id)

        if (
            mem.level == "long_term"
            and mem.access_count == 0
            and age > 30 * 24 * 3600
            and mem.tier == MemoryTier.ACTIVE
            and graph_boost < 0.2
        ):
            archived_candidates.append(mem.id)

    return {"promoted": promoted, "archive_candidates": archived_candidates}


def build_centrality_map(knowledge_graph) -> Dict[str, float]:
    """Precompute entity centralities for graph-aware scheduling."""
    if knowledge_graph is None:
        return {}
    return {
        e.name.lower(): knowledge_graph.entity_centrality(e.name)
        for e in knowledge_graph.all_entities()
    }
