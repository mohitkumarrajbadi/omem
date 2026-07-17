"""BM25 keyword scoring for live hybrid fusion.

Prefers Rust ``omem_rust.bm25_scores`` / ``tokenize_bm25`` when available;
falls back to a pure-Python BM25 Okapi implementation.
"""

from __future__ import annotations

import math
import re
from typing import List, Optional, Sequence

_TOKEN_RE = re.compile(r"[a-z0-9]{2,}")

try:
    import omem_rust

    _HAS_RUST = True
except ImportError:
    omem_rust = None  # type: ignore
    _HAS_RUST = False


def tokenize(text: str) -> List[str]:
    if _HAS_RUST and hasattr(omem_rust, "tokenize_bm25"):
        return list(omem_rust.tokenize_bm25(text or ""))
    return _TOKEN_RE.findall((text or "").lower())


def _python_bm25(
    documents: Sequence[Sequence[str]],
    query: Sequence[str],
    *,
    k1: float = 1.5,
    b: float = 0.75,
) -> List[float]:
    n = len(documents)
    if n == 0:
        return []
    df: dict = {}
    lengths = []
    term_counts = []
    for doc in documents:
        counts: dict = {}
        for t in doc:
            counts[t] = counts.get(t, 0) + 1
        for t in counts:
            df[t] = df.get(t, 0) + 1
        lengths.append(len(doc))
        term_counts.append(counts)
    avgdl = sum(lengths) / max(n, 1)
    q_tf: dict = {}
    for t in query:
        q_tf[t] = q_tf.get(t, 0) + 1

    scores = []
    for i, counts in enumerate(term_counts):
        score = 0.0
        dl = lengths[i]
        for term, qf in q_tf.items():
            if term not in counts:
                continue
            n_qi = df.get(term, 0)
            idf = math.log(1.0 + (n - n_qi + 0.5) / (n_qi + 0.5))
            tf = counts[term]
            denom = tf + k1 * (1.0 - b + b * dl / max(avgdl, 1e-6))
            score += idf * (tf * (k1 + 1.0) / max(denom, 1e-6)) * qf
        scores.append(float(score))
    return scores


def bm25_batch(
    documents: Sequence[str],
    query: str,
    *,
    k1: float = 1.5,
    b: float = 0.75,
) -> List[float]:
    """Score each document against query with BM25; returns raw scores."""
    docs_tok = [tokenize(d) for d in documents]
    q_tok = tokenize(query)
    if not q_tok or not docs_tok:
        return [0.0] * len(documents)
    if _HAS_RUST and hasattr(omem_rust, "bm25_scores"):
        return list(omem_rust.bm25_scores(docs_tok, q_tok, float(k1), float(b)))
    return _python_bm25(docs_tok, q_tok, k1=k1, b=b)


def normalize_scores(scores: Sequence[float]) -> List[float]:
    """Min-max normalize to [0, 1]."""
    if not scores:
        return []
    mx = max(scores)
    if mx <= 0:
        return [0.0] * len(scores)
    return [float(s) / mx for s in scores]


def keyword_bm25_blend(
    documents: Sequence[str],
    query: str,
    overlap_scores: Optional[Sequence[float]] = None,
    *,
    bm25_weight: float = 0.7,
) -> List[float]:
    """Blend BM25 with optional overlap scores for fusion keyword signal."""
    raw = bm25_batch(documents, query)
    bm = normalize_scores(raw)
    if overlap_scores is None:
        return bm
    out = []
    for i, bscore in enumerate(bm):
        ov = float(overlap_scores[i]) if i < len(overlap_scores) else 0.0
        out.append(bm25_weight * bscore + (1.0 - bm25_weight) * ov)
    return out
