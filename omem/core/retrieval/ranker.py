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

# Mode-specific fusion profiles
MODE_WEIGHT_PROFILES: Dict[str, FusionWeights] = {
    "default": DEFAULT_WEIGHTS,
    "planning": FusionWeights(
        semantic=0.22,
        keyword=0.10,
        recency=0.10,
        importance=0.28,
        confidence=0.12,
        graph=0.10,
        personalization=0.08,
    ),
    "coding": FusionWeights(
        semantic=0.35,
        keyword=0.18,
        recency=0.08,
        importance=0.15,
        confidence=0.08,
        graph=0.10,
        personalization=0.06,
    ),
    "chat": FusionWeights(
        semantic=0.28,
        keyword=0.12,
        recency=0.18,
        importance=0.15,
        confidence=0.08,
        graph=0.10,
        personalization=0.09,
    ),
    "recall": FusionWeights(
        semantic=0.25,
        keyword=0.10,
        recency=0.22,
        importance=0.18,
        confidence=0.10,
        graph=0.08,
        personalization=0.07,
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
    status_multiplier: float = 1.0
    matched_keywords: List[str] = None  # type: ignore[assignment]

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
    """Keyword overlap score and matched token list."""
    if q_hashes is not None and memory.token_hashes.size > 0:
        overlap = fast_intersect(q_hashes, memory.token_hashes)
        kw = min(overlap / max(len(query_tokens), 1), 1.0)
    else:
        matched = query_tokens & memory.tokens
        kw = min(len(matched) / max(len(query_tokens), 1), 1.0)
        return kw, sorted(matched)
    matched = sorted(query_tokens & memory.tokens)
    return kw, matched


def compute_signals(
    memory: Memory,
    query: str,
    vector_score: float,
    now: float,
    knowledge_graph: Optional[KnowledgeGraph] = None,
    query_entities: Optional[List[str]] = None,
) -> CandidateSignals:
    """Compute all scoring signals for a memory candidate."""
    query_tokens = set(_TOKENIZER.findall(query.lower()))
    q_hashes = np.sort(
        np.array([_token_hash(t) for t in query_tokens], dtype=np.uint64)
    ) if query_tokens else np.array([], dtype=np.uint64)

    kw_score, matched = compute_keyword_score(query_tokens, memory, q_hashes)
    recency = compute_recency_score(memory.timestamp, now, _RECENCY_HALF_LIFE)
    frequency = compute_frequency_score(memory.access_count)
    personalization = min(getattr(memory, "utility_score", 0.0), 1.0)
    confidence = getattr(memory, "confidence_score", 1.0)

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
        status_multiplier=status_mult,
        matched_keywords=matched,
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
) -> RetrievalExplanation:
    """Build a full fusion-based retrieval explanation."""
    w = weights or weights_for_mode(mode)
    entities = query_entities or (
        [e.name for e in knowledge_graph.find_entities_in_query(query)]
        if knowledge_graph
        else []
    )
    signals = compute_signals(
        memory, query, vector_score, now, knowledge_graph, entities
    )
    final = score_candidate(signals, w)

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
    """Score, rank, and explain a candidate memory set."""
    w = weights or weights_for_mode(mode)
    query_entities = (
        [e.name for e in knowledge_graph.find_entities_in_query(query)]
        if knowledge_graph
        else []
    )

    scored: List[tuple[Memory, float, RetrievalExplanation]] = []
    for mem in memories:
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
    for mem in memories:
        reinforce_on_access(mem, now)
