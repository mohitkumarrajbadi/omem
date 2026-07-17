"""Type-aware and multi-kind lookup routers on top of hybrid fusion.

Lookup kinds (charter):
  exact | semantic | temporal | entity | causal | state | hybrid

State lookups are handled by StateOS — this module returns an empty
list with a reason so callers can route explicitly.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Sequence

from ...types import Memory, MemoryType, RetrievalExplanation, resolve_hierarchy_level
from .fusion import FusionWeights
from .ranker import weights_for_mode


class LookupKind(str, Enum):
    EXACT = "exact"
    SEMANTIC = "semantic"
    TEMPORAL = "temporal"
    ENTITY = "entity"
    CAUSAL = "causal"
    STATE = "state"
    HYBRID = "hybrid"


# Soft per-type retrieval bias: which lookup + mode to prefer
TYPE_LOOKUP_HINTS: Dict[MemoryType, LookupKind] = {
    MemoryType.WORKING: LookupKind.TEMPORAL,
    MemoryType.EPISODIC: LookupKind.TEMPORAL,
    MemoryType.SEMANTIC: LookupKind.SEMANTIC,
    MemoryType.DECISION: LookupKind.SEMANTIC,
    MemoryType.TOOL: LookupKind.EXACT,
    MemoryType.SKILL: LookupKind.SEMANTIC,
    MemoryType.PROCEDURAL: LookupKind.SEMANTIC,
    MemoryType.CAUSAL: LookupKind.CAUSAL,
    MemoryType.ACTIVE: LookupKind.HYBRID,
    MemoryType.INSIGHT: LookupKind.SEMANTIC,
    MemoryType.REFLECTION: LookupKind.SEMANTIC,
    MemoryType.SENSORY: LookupKind.TEMPORAL,
}


def lookup_overrides(kind: LookupKind) -> Dict[str, float]:
    """Weight overrides that soft-bias hybrid fusion toward a lookup kind."""
    if kind == LookupKind.EXACT:
        return {"keyword": 0.40, "semantic": 0.15, "recency": 0.10}
    if kind == LookupKind.SEMANTIC:
        return {"semantic": 0.45, "keyword": 0.08, "graph": 0.12}
    if kind == LookupKind.TEMPORAL:
        return {"recency": 0.40, "semantic": 0.20, "keyword": 0.10}
    if kind == LookupKind.ENTITY:
        return {"graph": 0.35, "semantic": 0.25, "keyword": 0.12}
    if kind == LookupKind.CAUSAL:
        return {"semantic": 0.30, "keyword": 0.18, "graph": 0.18, "importance": 0.15}
    return {}


def resolve_lookup(
    *,
    lookup: Optional[str] = None,
    memory_type: Optional[MemoryType] = None,
) -> LookupKind:
    if lookup:
        try:
            return LookupKind(lookup.lower().strip())
        except ValueError:
            return LookupKind.HYBRID
    if memory_type is not None:
        return TYPE_LOOKUP_HINTS.get(memory_type, LookupKind.HYBRID)
    return LookupKind.HYBRID


def fusion_for_lookup(
    kind: LookupKind,
    mode: str = "default",
    extra: Optional[Dict[str, float]] = None,
) -> FusionWeights:
    base_overrides = lookup_overrides(kind)
    if extra:
        base_overrides = {**base_overrides, **extra}
    return weights_for_mode(mode, base_overrides or None)


def filter_by_type_hint(
    memories: Sequence[Memory],
    preferred: Optional[MemoryType],
    *,
    soft: bool = True,
) -> List[Memory]:
    """Optionally prefer a type without hard-gating (soft=True keeps all, sorts prefer)."""
    if preferred is None or not soft:
        if preferred is None:
            return list(memories)
        return [m for m in memories if m.type == preferred]
    preferred_list = [m for m in memories if m.type == preferred]
    others = [m for m in memories if m.type != preferred]
    return preferred_list + others


def annotate_explanations(
    explanations: List[RetrievalExplanation],
    kind: LookupKind,
) -> List[RetrievalExplanation]:
    for exp in explanations:
        exp.lookup_kind = kind.value
        if not exp.retrieval_reason:
            exp.retrieval_reason = f"{kind.value} lookup via hybrid fusion"
    return explanations


def recall_routed(
    engine: Any,
    query: str,
    *,
    k: int = 5,
    namespace: Optional[str] = None,
    mode: str = "default",
    lookup: Optional[str] = None,
    memory_type: Optional[MemoryType] = None,
    level: Optional[str] = None,
    **kwargs: Any,
) -> List[Memory]:
    """Recall with soft type/lookup routing.

    ``lookup=state`` returns [] — callers should use StateOS.
    """
    from .type_strategies import (
        apply_type_preference,
        filter_by_preferred_levels,
        fusion_for_type,
        strategy_for,
    )

    kind = resolve_lookup(lookup=lookup, memory_type=memory_type)
    if kind == LookupKind.STATE:
        return []

    strat = strategy_for(memory_type, lookup)
    weights = fusion_for_type(memory_type, mode=mode, lookup=lookup)
    extra = kwargs.pop("weight_overrides", None)
    if extra:
        data = weights.as_dict()
        data.update({kk: float(vv) for kk, vv in extra.items() if kk in data})
        from .fusion import FusionWeights

        weights = FusionWeights(**data)

    level_resolved = resolve_hierarchy_level(level) if level else level
    if level_resolved is None and strat.preferred_levels:
        # Soft: do not hard-filter by level unless caller asked
        level_resolved = None

    context_type = kwargs.pop("context_type", None)
    if memory_type is not None and context_type is None:
        context_type = memory_type.name.lower()

    results = engine.recall(
        query,
        k=max(k * 3, k) if memory_type else k,
        namespace=namespace,
        mode=mode,
        level=level_resolved,
        context_type=context_type,
        weight_overrides=weights.as_dict(),
        **kwargs,
    )
    results = filter_by_preferred_levels(results, memory_type, soft=True)
    results = apply_type_preference(results, memory_type)[:k]

    exps = getattr(engine, "_last_explanations", None) or []
    annotate_explanations(list(exps), strat.lookup)
    return results

