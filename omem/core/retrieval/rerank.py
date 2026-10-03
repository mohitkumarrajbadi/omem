"""Optional cross-encoder rerank. Encoder model, not a generative LLM.

Off by default. Enable with ``mode="strong"`` or ``OMEM_RERANK=1``.
Falls back to the input order when sentence-transformers is missing.
"""

from __future__ import annotations

import logging
import os
from typing import List, Optional

from ...types import Memory

logger = logging.getLogger(__name__)

_MODEL = None
_MODEL_FAILED = False


def rerank_enabled(mode: str = "default") -> bool:
    if str(os.environ.get("OMEM_RERANK", "")).strip().lower() in ("1", "true", "yes"):
        return True
    return mode == "strong"


def rerank_cross_encoder(
    query: str,
    memories: List[Memory],
    *,
    top_k: Optional[int] = None,
    model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2",
) -> List[Memory]:
    """Reorder memories by pairwise relevance. No-op if the model is absent."""
    global _MODEL, _MODEL_FAILED
    if not memories:
        return memories
    if _MODEL_FAILED:
        return memories[:top_k] if top_k else memories
    try:
        if _MODEL is None:
            from sentence_transformers import CrossEncoder  # type: ignore

            _MODEL = CrossEncoder(model_name)
        pairs = [(query, m.content) for m in memories]
        scores = _MODEL.predict(pairs)
        ranked = sorted(
            zip(memories, scores),
            key=lambda x: float(x[1]),
            reverse=True,
        )
        out = []
        for mem, sc in ranked:
            mem.score = float(sc)
            out.append(mem)
        return out[:top_k] if top_k else out
    except Exception as exc:
        _MODEL_FAILED = True
        logger.debug("cross-encoder rerank unavailable (%s) — keeping fusion order", exc)
        return memories[:top_k] if top_k else memories
