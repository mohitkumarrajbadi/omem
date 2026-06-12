"""Retrieval inspector — fusion-based explainability for multi-objective scoring."""

import time
from typing import Dict, List, Optional

from ...types import Memory, RetrievalExplanation
from ..graph.knowledge import KnowledgeGraph
from ..retrieval.fusion import FusionWeights
from ..retrieval.ranker import rank_memories, weights_for_mode


def inspect_query(
    query: str,
    memories: List[Memory],
    vector_scores: Dict[str, float],
    top_k: int = 5,
    now: Optional[float] = None,
    mode: str = "default",
    knowledge_graph: Optional[KnowledgeGraph] = None,
    weights: Optional[FusionWeights] = None,
    weight_overrides: Optional[Dict[str, float]] = None,
) -> List[RetrievalExplanation]:
    """Inspect a query using the same fusion ranker as RAG retrieval."""
    now = now or time.time()
    w = weights or weights_for_mode(mode, weight_overrides)
    _, explanations = rank_memories(
        memories,
        query,
        vector_scores,
        now,
        top_k=top_k,
        mode=mode,
        knowledge_graph=knowledge_graph,
        weights=w,
    )
    return explanations
