"""Multi-objective retrieval fusion engine.

Combines semantic, keyword, recency, importance, confidence, graph,
personalization, success, and goal alignment into one configurable score:

    score = αS + βK + γR + δI + εC + ζG + ηP + θSuccess + ιGoal
"""

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class FusionWeights:
    """Configurable weights for hybrid retrieval scoring."""

    semantic: float = 0.28
    keyword: float = 0.11
    recency: float = 0.12
    importance: float = 0.18
    confidence: float = 0.07
    graph: float = 0.09
    personalization: float = 0.05
    success: float = 0.05
    goal: float = 0.05

    def as_dict(self) -> Dict[str, float]:
        return {
            "semantic": self.semantic,
            "keyword": self.keyword,
            "recency": self.recency,
            "importance": self.importance,
            "confidence": self.confidence,
            "graph": self.graph,
            "personalization": self.personalization,
            "success": self.success,
            "goal": self.goal,
        }

    def as_weight_vector(self) -> List[float]:
        """Ordered vector matching Rust ``rag_fuse_batch`` / scorer layout."""
        return [
            self.semantic,
            self.keyword,
            self.recency,
            self.importance,
            self.confidence,
            self.graph,
            self.personalization,
            self.success,
            self.goal,
        ]


DEFAULT_WEIGHTS = FusionWeights()


def fuse_score(
    semantic: float,
    keyword: float,
    recency: float,
    importance: float,
    confidence: float = 1.0,
    graph: float = 0.0,
    personalization: float = 0.0,
    success: float = 0.0,
    goal: float = 0.0,
    weights: Optional[FusionWeights] = None,
) -> float:
    """Compute fused retrieval score from normalized component signals."""
    w = weights or DEFAULT_WEIGHTS
    return (
        w.semantic * semantic
        + w.keyword * keyword
        + w.recency * recency
        + w.importance * importance
        + w.confidence * confidence
        + w.graph * graph
        + w.personalization * personalization
        + w.success * success
        + w.goal * goal
    )


def normalize_graph_distance(hops: int, max_hops: int = 3) -> float:
    """Convert hop distance to a [0, 1] proximity score (1 = closest)."""
    if hops <= 0:
        return 1.0
    if hops >= max_hops:
        return 0.0
    return 1.0 - (hops / max_hops)


def rrf_from_ranked_ids(
    ranked_lists: List[List[str]],
    k: int = 60,
) -> Dict[str, float]:
    """Reciprocal rank fusion: ``score(d) = Σ 1 / (k + rank_i(d))``.

    ``ranked_lists`` are ordered best-first (rank 1 = index 0).
    """
    scores: Dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, doc_id in enumerate(ranked, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return scores


def rrf_from_score_maps(
    *score_maps: Dict[str, float],
    k: int = 60,
) -> Dict[str, float]:
    """RRF over score dictionaries (higher score = better)."""
    ranked_lists: List[List[str]] = []
    for smap in score_maps:
        if not smap:
            continue
        ordered = sorted(smap.keys(), key=lambda i: smap[i], reverse=True)
        ranked_lists.append(ordered)
    return rrf_from_ranked_ids(ranked_lists, k=k)


def minmax_norm(scores: Dict[str, float]) -> Dict[str, float]:
    if not scores:
        return {}
    vals = list(scores.values())
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-12:
        return {i: 1.0 for i in scores}
    return {i: (v - lo) / (hi - lo) for i, v in scores.items()}
