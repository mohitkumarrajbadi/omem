"""Per-type retrieval strategies for Memory OS cognitive objects.

Each MemoryType has independent candidate filtering + fusion weight profile
while still using the shared hybrid scorer (soft type engines, not hard silos).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

from ...types import Memory, MemoryType
from .fusion import FusionWeights
from .lookup import LookupKind, fusion_for_lookup, resolve_lookup


@dataclass
class TypeStrategy:
    """Independent retrieval logic knobs for one cognitive memory type."""

    lookup: LookupKind
    preferred_levels: tuple
    weight_overrides: Dict[str, float]
    prefer_types: tuple  # soft prefer these MemoryType values first


# Charter: each type has independent retrieval logic
TYPE_STRATEGIES: Dict[MemoryType, TypeStrategy] = {
    MemoryType.WORKING: TypeStrategy(
        lookup=LookupKind.TEMPORAL,
        preferred_levels=("working", "short_term"),
        weight_overrides={"recency": 0.40, "semantic": 0.20, "importance": 0.15},
        prefer_types=(MemoryType.WORKING, MemoryType.ACTIVE),
    ),
    MemoryType.EPISODIC: TypeStrategy(
        lookup=LookupKind.TEMPORAL,
        preferred_levels=("short_term", "long_term", "working"),
        weight_overrides={"recency": 0.32, "semantic": 0.25, "keyword": 0.15},
        prefer_types=(MemoryType.EPISODIC, MemoryType.CAUSAL),
    ),
    MemoryType.SEMANTIC: TypeStrategy(
        lookup=LookupKind.SEMANTIC,
        preferred_levels=("long_term", "short_term"),
        weight_overrides={"semantic": 0.42, "graph": 0.15, "importance": 0.18},
        prefer_types=(MemoryType.SEMANTIC, MemoryType.INSIGHT, MemoryType.DECISION),
    ),
    MemoryType.DECISION: TypeStrategy(
        lookup=LookupKind.SEMANTIC,
        preferred_levels=("long_term",),
        weight_overrides={"importance": 0.28, "semantic": 0.30, "keyword": 0.15},
        prefer_types=(MemoryType.DECISION, MemoryType.SEMANTIC),
    ),
    MemoryType.TOOL: TypeStrategy(
        lookup=LookupKind.EXACT,
        preferred_levels=("working", "short_term", "long_term"),
        weight_overrides={"keyword": 0.45, "semantic": 0.20, "recency": 0.15},
        prefer_types=(MemoryType.TOOL,),
    ),
    MemoryType.SKILL: TypeStrategy(
        lookup=LookupKind.SEMANTIC,
        preferred_levels=("long_term",),
        weight_overrides={"semantic": 0.35, "keyword": 0.20, "importance": 0.20},
        prefer_types=(MemoryType.SKILL, MemoryType.PROCEDURAL),
    ),
    MemoryType.PROCEDURAL: TypeStrategy(
        lookup=LookupKind.SEMANTIC,
        preferred_levels=("long_term", "short_term"),
        weight_overrides={"keyword": 0.28, "semantic": 0.30, "importance": 0.18},
        prefer_types=(MemoryType.PROCEDURAL, MemoryType.SKILL),
    ),
    MemoryType.CAUSAL: TypeStrategy(
        lookup=LookupKind.CAUSAL,
        preferred_levels=("long_term", "short_term"),
        weight_overrides={"semantic": 0.30, "graph": 0.22, "keyword": 0.16},
        prefer_types=(MemoryType.CAUSAL, MemoryType.EPISODIC),
    ),
}


def strategy_for(
    memory_type: Optional[MemoryType] = None,
    lookup: Optional[str] = None,
) -> TypeStrategy:
    if memory_type and memory_type in TYPE_STRATEGIES:
        return TYPE_STRATEGIES[memory_type]
    kind = resolve_lookup(lookup=lookup, memory_type=memory_type)
    # Default hybrid strategy
    return TypeStrategy(
        lookup=kind,
        preferred_levels=("working", "short_term", "long_term"),
        weight_overrides={},
        prefer_types=(),
    )


def fusion_for_type(
    memory_type: Optional[MemoryType] = None,
    *,
    mode: str = "default",
    lookup: Optional[str] = None,
) -> FusionWeights:
    strat = strategy_for(memory_type, lookup)
    return fusion_for_lookup(strat.lookup, mode=mode, extra=strat.weight_overrides)


def apply_type_preference(
    memories: Sequence[Memory],
    memory_type: Optional[MemoryType],
) -> List[Memory]:
    """Reorder candidates: preferred types first (soft), keep all."""
    if memory_type is None or memory_type not in TYPE_STRATEGIES:
        return list(memories)
    prefer = set(TYPE_STRATEGIES[memory_type].prefer_types)
    head = [m for m in memories if m.type in prefer]
    tail = [m for m in memories if m.type not in prefer]
    return head + tail


def filter_by_preferred_levels(
    memories: Sequence[Memory],
    memory_type: Optional[MemoryType],
    *,
    soft: bool = True,
) -> List[Memory]:
    if memory_type is None or memory_type not in TYPE_STRATEGIES:
        return list(memories)
    levels = set(TYPE_STRATEGIES[memory_type].preferred_levels)
    matched = [m for m in memories if getattr(m, "level", "") in levels]
    if soft:
        others = [m for m in memories if getattr(m, "level", "") not in levels]
        return matched + others
    return matched
