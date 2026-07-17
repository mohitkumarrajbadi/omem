"""Memory hierarchy conveyor: L0 → L1 → L2/L3 → L4 with optional cold spill.

Called during ``sleep()`` after decay so memories migrate automatically.
"""

from __future__ import annotations

import os
import time
from typing import Dict, List, Optional

from ...types import Memory, MemoryTier, MemoryType
from .lifecycle_fsm import mark_archived
from .scheduler import (
    _GRAPH_PROMOTE_THRESHOLD,
    _LTM_MIN_ACCESSES,
    _STM_MAX_AGE_SECONDS,
    _STM_PROMOTE_ACCESSES,
)

# Skill / decision types prefer L3 (long_term + skill metadata)
_L3_TYPES = {
    MemoryType.SKILL,
    MemoryType.PROCEDURAL,
    MemoryType.DECISION,
    MemoryType.SEMANTIC,
    MemoryType.INSIGHT,
}

_L4_AGE_SECONDS = float(os.getenv("OMEM_L4_AGE_SECONDS", str(7 * 24 * 3600)))
_L4_MIN_IMPORTANCE = float(os.getenv("OMEM_L4_MIN_IMPORTANCE", "0.25"))


def run_hierarchy_conveyor(
    memories: List[Memory],
    *,
    now: Optional[float] = None,
    graph_centralities: Optional[Dict[str, float]] = None,
    cold_archive=None,
    auto_cold: Optional[bool] = None,
) -> Dict[str, List[str]]:
    """Promote / archive memories along L0–L4.

    Returns dict with promoted, archived, cold_spilled ids.
    """
    now = now or time.time()
    centralities = graph_centralities or {}
    if auto_cold is None:
        auto_cold = os.getenv("OMEM_COLD_ENABLED", "").strip().lower() in (
            "1",
            "true",
            "yes",
        ) or cold_archive is not None

    promoted: List[str] = []
    archived: List[str] = []
    cold_spilled: List[str] = []

    for mem in memories:
        if not mem.active:
            continue
        if mem.tier in (MemoryTier.CORE, MemoryTier.FORGOTTEN):
            continue

        age = max(now - mem.timestamp, 0.0)
        graph_boost = max(
            (centralities.get(e.lower(), 0.0) for e in getattr(mem, "entities", [])),
            default=0.0,
        )
        effective_accesses = mem.access_count + (
            1 if graph_boost >= _GRAPH_PROMOTE_THRESHOLD else 0
        )

        # L0 → L1
        if mem.level == "working":
            if effective_accesses >= _STM_PROMOTE_ACCESSES or age >= _STM_MAX_AGE_SECONDS:
                mem.level = "short_term"
                promoted.append(mem.id)
        # L1 → L2/L3
        elif mem.level == "short_term":
            if effective_accesses >= _LTM_MIN_ACCESSES or graph_boost >= _GRAPH_PROMOTE_THRESHOLD:
                mem.level = "long_term"
                if mem.type in _L3_TYPES:
                    mem.metadata = dict(mem.metadata or {})
                    mem.metadata["hierarchy"] = "L3_skill" if mem.type in (
                        MemoryType.SKILL,
                        MemoryType.PROCEDURAL,
                    ) else "L2_semantic"
                else:
                    mem.metadata = dict(mem.metadata or {})
                    mem.metadata.setdefault("hierarchy", "L2_semantic")
                promoted.append(mem.id)
        elif mem.tier == MemoryTier.SENSORY and mem.access_count >= 1:
            mem.tier = MemoryTier.ACTIVE
            mem.level = "short_term"
            promoted.append(mem.id)

        # L2/L3 → L4 archive candidates
        should_archive = False
        if mem.level == "long_term" and mem.tier == MemoryTier.ACTIVE:
            if (
                mem.access_count == 0
                and age > _L4_AGE_SECONDS
                and mem.importance < _L4_MIN_IMPORTANCE
                and graph_boost < 0.2
            ):
                should_archive = True
            # Also archive if already listed in metadata by legacy scheduler
            if mem.metadata.get("force_archive"):
                should_archive = True

        if should_archive or mem.tier == MemoryTier.ARCHIVE:
            if mem.tier != MemoryTier.ARCHIVE:
                mark_archived(mem)
                archived.append(mem.id)
            if auto_cold and cold_archive is not None and not getattr(
                mem, "cold_storage_key", None
            ):
                try:
                    cold_archive.archive_memory(mem)
                    cold_spilled.append(mem.id)
                except Exception:
                    pass

    return {
        "promoted": promoted,
        "archived": archived,
        "cold_spilled": cold_spilled,
        "archive_candidates": archived,
    }
