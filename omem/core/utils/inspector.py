"""Retrieval inspector — explain why memories are retrieved.

Provides full transparency into the scoring pipeline so developers
can debug and tune their memory retrieval.
"""

import re
import time
from typing import Dict, List, Optional

from ...types import Memory, RetrievalExplanation
from ..brain.importance import compute_frequency_score, compute_recency_score

# Match the weights used in BrainTrace
_W_VECTOR = 0.35
_W_KEYWORD = 0.15
_W_IMPORTANCE = 0.25
_W_RECENCY = 0.15
_W_FREQUENCY = 0.10


def explain_retrieval(
    query: str,
    memory: Memory,
    vector_score: float,
    now: Optional[float] = None,
) -> RetrievalExplanation:
    """Build a full explanation of why a memory scored the way it did."""
    now = now or time.time()

    query_tokens = set(re.findall(r"\w+", query.lower()))
    matched = query_tokens & memory.tokens
    keyword_score = min(len(matched) / max(len(query_tokens), 1), 1.0)

    recency_score = compute_recency_score(memory.timestamp, now)
    frequency_bonus = compute_frequency_score(memory.access_count)

    final = (
        _W_VECTOR * vector_score
        + _W_KEYWORD * keyword_score
        + _W_IMPORTANCE * memory.importance
        + _W_RECENCY * recency_score
        + _W_FREQUENCY * frequency_bonus
    )

    return RetrievalExplanation(
        memory_id=memory.id,
        final_score=final,
        vector_score=vector_score,
        keyword_score=keyword_score,
        recency_score=recency_score,
        importance_score=memory.importance,
        frequency_bonus=frequency_bonus,
        query=query,
        matched_keywords=sorted(matched),
    )


def inspect_query(
    query: str,
    memories: List[Memory],
    vector_scores: Dict[str, float],
    top_k: int = 5,
    now: Optional[float] = None,
) -> List[RetrievalExplanation]:
    """Inspect a query against all memories and return explanations sorted by score."""
    explanations = []
    for mem in memories:
        vs = vector_scores.get(mem.id, 0.0)
        exp = explain_retrieval(query, mem, vs, now)
        explanations.append(exp)

    explanations.sort(key=lambda e: e.final_score, reverse=True)
    return explanations[:top_k]
