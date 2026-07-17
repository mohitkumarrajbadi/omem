"""Unified multi-objective retrieval ranker.

Shared scoring path for RAG retrieval and explainability inspector.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Set

import numpy as np

from ...types import Memory, MemoryStatus, RetrievalExplanation
from ..brain.importance import (
    _RECENCY_HALF_LIFE,
    compute_frequency_score,
    compute_recency_score,
    reinforce_on_access,
)
from ..engine.utils import _TOKENIZER, _token_hash, fast_intersect
from ..graph.knowledge import KnowledgeGraph
from .fusion import DEFAULT_WEIGHTS, FusionWeights, fuse_score

# Mode-specific fusion profiles (weights sum ≈ 1.0 including success/goal)
MODE_WEIGHT_PROFILES: Dict[str, FusionWeights] = {
    "default": DEFAULT_WEIGHTS,
    "planning": FusionWeights(
        semantic=0.20,
        keyword=0.09,
        recency=0.09,
        importance=0.24,
        confidence=0.10,
        graph=0.09,
        personalization=0.06,
        success=0.05,
        goal=0.08,
    ),
    "coding": FusionWeights(
        semantic=0.32,
        keyword=0.16,
        recency=0.07,
        importance=0.14,
        confidence=0.07,
        graph=0.09,
        personalization=0.05,
        success=0.05,
        goal=0.05,
    ),
    "chat": FusionWeights(
        semantic=0.26,
        keyword=0.11,
        recency=0.16,
        importance=0.13,
        confidence=0.07,
        graph=0.09,
        personalization=0.08,
        success=0.05,
        goal=0.05,
    ),
    "recall": FusionWeights(
        semantic=0.23,
        keyword=0.09,
        recency=0.20,
        importance=0.16,
        confidence=0.09,
        graph=0.07,
        personalization=0.06,
        success=0.05,
        goal=0.05,
    ),
}


@dataclass
class CandidateSignals:
    """Decomposed scoring signals for one memory candidate."""

    semantic: float = 0.0
    keyword: float = 0.0
    recency: float = 0.0
    importance: float = 0.0
    confidence: float = 1.0
    graph: float = 0.0
    centrality: float = 0.0
    personalization: float = 0.0
    frequency: float = 0.0
    success: float = 0.0
    goal: float = 0.0
    status_multiplier: float = 1.0
    matched_keywords: List[str] = None  # type: ignore[assignment]
    type_confidence: float = 1.0

    def __post_init__(self) -> None:
        if self.matched_keywords is None:
            self.matched_keywords = []

    @property
    def graph_combined(self) -> float:
        """Blend proximity and centrality into one graph signal."""
        return 0.7 * self.graph + 0.3 * self.centrality


def weights_for_mode(
    mode: str,
    overrides: Optional[Dict[str, float]] = None,
    base: Optional[FusionWeights] = None,
) -> FusionWeights:
    """Resolve fusion weights from mode profile and optional overrides."""
    w = MODE_WEIGHT_PROFILES.get(mode, base or DEFAULT_WEIGHTS)
    if not overrides:
        return w
    data = w.as_dict()
    data.update({k: float(v) for k, v in overrides.items() if k in data})
    return FusionWeights(**data)


def compute_keyword_score(
    query_tokens: Set[str],
    memory: Memory,
    q_hashes: Optional[np.ndarray] = None,
) -> tuple[float, List[str]]:
    """Keyword overlap score and matched token list (legacy single-doc path)."""
    if q_hashes is not None and memory.token_hashes.size > 0:
        overlap = fast_intersect(q_hashes, memory.token_hashes)
        kw = min(overlap / max(len(query_tokens), 1), 1.0)
    else:
        matched = query_tokens & memory.tokens
        kw = min(len(matched) / max(len(query_tokens), 1), 1.0)
        return kw, sorted(matched)
    matched = sorted(query_tokens & memory.tokens)
    return kw, matched


def _goal_alignment(memory: Memory, query: str) -> float:
    """Heuristic goal alignment: metadata goal + token overlap with query."""
    explicit = float(getattr(memory, "goal_alignment", 0.0) or 0.0)
    meta_goal = ""
    if isinstance(memory.metadata, dict):
        meta_goal = str(memory.metadata.get("goal", "") or "")
    blob = f"{meta_goal} {memory.content}".lower()
    q_tokens = set(_TOKENIZER.findall(query.lower()))
    if not q_tokens:
        return min(max(explicit, 0.0), 1.0)
    overlap = len(q_tokens & set(_TOKENIZER.findall(blob))) / max(len(q_tokens), 1)
    return min(max(explicit, overlap), 1.0)


def compute_signals(
    memory: Memory,
    query: str,
    vector_score: float,
    now: float,
    knowledge_graph: Optional[KnowledgeGraph] = None,
    query_entities: Optional[List[str]] = None,
    keyword_override: Optional[float] = None,
) -> CandidateSignals:
    """Compute all scoring signals for a memory candidate."""
    query_tokens = set(_TOKENIZER.findall(query.lower()))
    q_hashes = np.sort(
        np.array([_token_hash(t) for t in query_tokens], dtype=np.uint64)
    ) if query_tokens else np.array([], dtype=np.uint64)

    kw_score, matched = compute_keyword_score(query_tokens, memory, q_hashes)
    if keyword_override is not None:
        kw_score = float(keyword_override)
    recency = compute_recency_score(memory.timestamp, now, _RECENCY_HALF_LIFE)
    frequency = compute_frequency_score(memory.access_count)
    personalization = min(getattr(memory, "utility_score", 0.0), 1.0)
    confidence = getattr(memory, "confidence_score", 1.0)
    # Soft-hint: blend stored confidence with type_confidence (never hard-gate)
    type_conf = float(getattr(memory, "type_confidence", 1.0) or 1.0)
    confidence = 0.85 * confidence + 0.15 * type_conf
    success = min(float(getattr(memory, "success_score", 0.0) or 0.0), 1.0)
    if isinstance(memory.metadata, dict) and "success" in memory.metadata:
        try:
            success = max(success, float(memory.metadata["success"]))
        except (TypeError, ValueError):
            pass
    goal = _goal_alignment(memory, query)

    graph_score = 0.0
    centrality = 0.0
    if knowledge_graph and query_entities:
        graph_score = knowledge_graph.graph_score_for_memory(
            memory.id, query_entities, depth=2
        )
        centrality = knowledge_graph.centrality_for_memory(
            memory.id, query_entities
        )

    status_mult = 1.0
    if memory.status == MemoryStatus.CONFLICTED:
        status_mult = 0.3
    elif memory.status == MemoryStatus.DEPRECATED:
        status_mult = 0.0

    return CandidateSignals(
        semantic=float(vector_score),
        keyword=kw_score,
        recency=recency,
        importance=memory.base_score or memory.importance,
        confidence=confidence,
        graph=graph_score,
        centrality=centrality,
        personalization=personalization,
        frequency=frequency,
        success=success,
        goal=goal,
        status_multiplier=status_mult,
        matched_keywords=matched,
        type_confidence=type_conf,
    )


def score_candidate(
    signals: CandidateSignals,
    weights: Optional[FusionWeights] = None,
    frequency_weight: float = 0.10,
) -> float:
    """Fuse signals into a final retrieval score."""
    if signals.status_multiplier == 0.0:
        return 0.0
    fused = fuse_score(
        semantic=signals.semantic,
        keyword=signals.keyword,
        recency=signals.recency,
        importance=signals.importance,
        confidence=signals.confidence,
        graph=signals.graph_combined,
        personalization=signals.personalization,
        success=signals.success,
        goal=signals.goal,
        weights=weights,
    )
    return float((fused + signals.frequency * frequency_weight) * signals.status_multiplier)


def explain_candidate(
    memory: Memory,
    query: str,
    vector_score: float,
    now: float,
    mode: str = "default",
    knowledge_graph: Optional[KnowledgeGraph] = None,
    query_entities: Optional[List[str]] = None,
    weights: Optional[FusionWeights] = None,
    keyword_override: Optional[float] = None,
) -> RetrievalExplanation:
    """Build a full fusion-based retrieval explanation."""
    w = weights or weights_for_mode(mode)
    entities = query_entities or (
        [e.name for e in knowledge_graph.find_entities_in_query(query)]
        if knowledge_graph
        else []
    )
    signals = compute_signals(
        memory,
        query,
        vector_score,
        now,
        knowledge_graph,
        entities,
        keyword_override=keyword_override,
    )
    final = score_candidate(signals, w)

    factors: List[str] = []
    parts = [
        ("semantic", signals.semantic),
        ("keyword", signals.keyword),
        ("recency", signals.recency),
        ("importance", signals.importance),
        ("graph", signals.graph_combined),
        ("success", signals.success),
        ("goal", signals.goal),
    ]
    for name, val in sorted(parts, key=lambda x: -x[1]):
        if val >= 0.15:
            factors.append(f"{name}={val:.2f}")

    return RetrievalExplanation(
        memory_id=memory.id,
        final_score=final,
        vector_score=signals.semantic,
        keyword_score=signals.keyword,
        recency_score=signals.recency,
        importance_score=signals.importance,
        frequency_bonus=signals.frequency,
        query=query,
        mode=mode,
        matched_keywords=signals.matched_keywords,
        confidence_score=signals.confidence,
        graph_score=signals.graph_combined,
        personalization_score=signals.personalization,
        success_score=signals.success,
        goal_alignment_score=signals.goal,
        retrieval_reason=f"hybrid BM25 fusion (mode={mode})",
        contributing_factors=factors,
        lookup_kind="hybrid",
    )


def rank_memories(
    memories: List[Memory],
    query: str,
    vector_scores: Dict[str, float],
    now: float,
    top_k: int = 5,
    mode: str = "default",
    knowledge_graph: Optional[KnowledgeGraph] = None,
    weights: Optional[FusionWeights] = None,
) -> tuple[List[Memory], List[RetrievalExplanation]]:
    """Score, rank, and explain a candidate memory set (BM25 keyword on batch)."""
    from .bm25 import keyword_bm25_blend

    w = weights or weights_for_mode(mode)
    query_entities = (
        [e.name for e in knowledge_graph.find_entities_in_query(query)]
        if knowledge_graph
        else []
    )

    # Precompute BM25+overlap keyword signal across the candidate set
    query_tokens = set(_TOKENIZER.findall(query.lower()))
    overlaps = []
    for mem in memories:
        ov, _ = compute_keyword_score(query_tokens, mem)
        overlaps.append(ov)
    kw_scores = keyword_bm25_blend(
        [m.content for m in memories],
        query,
        overlaps,
    )

    scored: List[tuple[Memory, float, RetrievalExplanation]] = []
    for i, mem in enumerate(memories):
        vs = vector_scores.get(mem.id, 0.0)
        exp = explain_candidate(
            mem,
            query,
            vs,
            now,
            mode=mode,
            knowledge_graph=knowledge_graph,
            query_entities=query_entities,
            weights=w,
            keyword_override=kw_scores[i] if i < len(kw_scores) else None,
        )
        mem.score = exp.final_score
        scored.append((mem, exp.final_score, exp))

    scored.sort(key=lambda x: x[1], reverse=True)
    top = scored[:top_k]
    results = [m for m, _, _ in top]
    explanations = [e for _, _, e in top]
    return results, explanations


def apply_reinforcement(memories: List[Memory], now: float) -> None:
    """Boost importance/confidence for retrieved memories (online learning)."""
    from ..brain.lifecycle_fsm import mark_reinforced

    for mem in memories:
        reinforce_on_access(mem, now)
        mark_reinforced(mem)
