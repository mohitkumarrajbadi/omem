"""Multi-objective retrieval fusion engine.

Combines semantic, recency, importance, confidence, graph proximity,
and personalization into a single configurable score:

    score = αS + βK + γR + δI + εC + ζG + ηP
"""

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class FusionWeights:
    """Configurable weights for hybrid retrieval scoring."""

    semantic: float = 0.30
    keyword: float = 0.12
    recency: float = 0.13
    importance: float = 0.20
    confidence: float = 0.08
    graph: float = 0.10
    personalization: float = 0.07

    def as_dict(self) -> Dict[str, float]:
        return {
            "semantic": self.semantic,
            "keyword": self.keyword,
            "recency": self.recency,
            "importance": self.importance,
            "confidence": self.confidence,
            "graph": self.graph,
            "personalization": self.personalization,
        }


DEFAULT_WEIGHTS = FusionWeights()


def fuse_score(
    semantic: float,
    keyword: float,
    recency: float,
    importance: float,
    confidence: float = 1.0,
    graph: float = 0.0,
    personalization: float = 0.0,
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
    )


def normalize_graph_distance(hops: int, max_hops: int = 3) -> float:
    """Convert hop distance to a [0, 1] proximity score (1 = closest)."""
    if hops <= 0:
        return 1.0
    if hops >= max_hops:
        return 0.0
    return 1.0 - (hops / max_hops)
