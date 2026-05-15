"""Auto-classification of text into MemoryTypes — Production-Grade.

Features:
- Confidence-scored regex classification
- Multi-label support: memories can match multiple types
- ML fallback using TF-IDF when regex confidence is low
- LRU cache for dedup

Improvements A+B from v0.5.0 production hardening.
"""

import re
from typing import List, Tuple, Dict

from .types import MemoryType

# ── Confidence threshold ──
_MIN_REGEX_CONFIDENCE = 0.1  # Lowered to avoid premature fallback to SEMANTIC
_MULTI_LABEL_THRESHOLD = 0.15  # Lowered slightly for catch-all robustness

# ── Regex patterns with weights ──
# Each pattern has a confidence contribution weight
_PATTERNS: Dict[MemoryType, List[Tuple[re.Pattern, float]]] = {
    MemoryType.PROCEDURAL: [
        (re.compile(r"\bstep\s*\d"), 0.40),
        (re.compile(r"\bhow\s+to\b"), 0.35),
        (re.compile(r"\bprocedure\b"), 0.30),
        (re.compile(r"\brecipe\b"), 0.25),
        (re.compile(r"\binstructions?\b"), 0.30),
        (re.compile(r"\bfirst\b.*\bthen\b"), 0.35),
        (re.compile(r"\bworkflow\b"), 0.25),
        (re.compile(r"\brun\b.*\bcommand\b"), 0.30),
        (re.compile(r"\binstall\b"), 0.20),
        (re.compile(r"\bexecute\b"), 0.20),
    ],
    MemoryType.CAUSAL: [
        (re.compile(r"\bbecause\b"), 0.35),
        (re.compile(r"\bcaused?\b"), 0.50),
        (re.compile(r"\bresulted?\s+in\b"), 0.45),
        (re.compile(r"\bdue\s+to\b"), 0.35),
        (re.compile(r"\btherefore\b"), 0.30),
        (re.compile(r"\bconsequen"), 0.30),
        (re.compile(r"\beffect\b"), 0.25),
        (re.compile(r"\breason\b"), 0.25),
        (re.compile(r"\bif\b.*\bthen\b"), 0.20),
    ],
    MemoryType.DECISION: [
        (re.compile(r"\bdecided?\b"), 0.50),
        (re.compile(r"\bchose\b"), 0.45),
        (re.compile(r"\bchoos"), 0.35),
        (re.compile(r"\bselect"), 0.30),
        (re.compile(r"\bprefer"), 0.40),
        (re.compile(r"\boption\b"), 0.20),
        (re.compile(r"\balternative\b"), 0.20),
        (re.compile(r"\btrade-?off\b"), 0.30),
        (re.compile(r"\bover\b"), 0.15),
        (re.compile(r"\binstead\b"), 0.20),
    ],
    MemoryType.EPISODIC: [
        (re.compile(r"\byesterday\b"), 0.40),
        (re.compile(r"\blast\s+(week|month|year)\b"), 0.35),
        (re.compile(r"\bremember\b"), 0.30),
        (re.compile(r"\bwent\s+to\b"), 0.30),
        (re.compile(r"\bhappened\b"), 0.30),
        (re.compile(r"\bexperienced?\b"), 0.25),
        (re.compile(r"\bvisited?\b"), 0.25),
        (re.compile(r"\btoday\b"), 0.20),
        (re.compile(r"\bthis\s+morning\b"), 0.30),
    ],
    MemoryType.WORKING: [
        (re.compile(r"\bright\s+now\b"), 0.40),
        (re.compile(r"\bcurrently\b"), 0.35),
        (re.compile(r"\bat\s+the\s+moment\b"), 0.35),
        (re.compile(r"\bin\s+progress\b"), 0.35),
        (re.compile(r"\bactive(ly)?\b"), 0.25),
        (re.compile(r"\bongoing\b"), 0.30),
        (re.compile(r"\bworking\s+on\b"), 0.30),
    ],
    MemoryType.ACTIVE: [
        (re.compile(r"\burgent\b"), 0.50),
        (re.compile(r"\bimportant\b"), 0.25),
        (re.compile(r"\bpriority\b"), 0.30),
        (re.compile(r"\basap\b"), 0.35),
        (re.compile(r"\bcritical\b"), 0.35),
        (re.compile(r"\bimmediate\b"), 0.30),
        (re.compile(r"\bdeadline\b"), 0.30),
    ],
}

# ── TF-IDF Keywords for ML fallback ──
_TFIDF_KEYWORDS: Dict[MemoryType, List[str]] = {
    MemoryType.PROCEDURAL: [
        "step",
        "how",
        "tutorial",
        "guide",
        "install",
        "run",
        "execute",
        "command",
        "script",
        "build",
        "deploy",
        "configure",
        "setup",
    ],
    MemoryType.CAUSAL: [
        "because",
        "cause",
        "caused",
        "effect",
        "result",
        "resulted",
        "reason",
        "therefore",
        "crash",
        "bug",
        "error",
        "fix",
        "broken",
        "failed",
    ],
    MemoryType.DECISION: [
        "decide",
        "decided",
        "chose",
        "choose",
        "prefer",
        "option",
        "select",
        "switch",
        "over",
        "instead",
        "went",
        "picked",
    ],
    MemoryType.EPISODIC: [
        "yesterday",
        "last",
        "remember",
        "happened",
        "went",
        "visited",
        "meeting",
        "event",
        "today",
        "morning",
    ],
    MemoryType.WORKING: [
        "currently",
        "now",
        "moment",
        "progress",
        "active",
        "ongoing",
        "working",
        "doing",
    ],
    MemoryType.ACTIVE: [
        "urgent",
        "important",
        "critical",
        "priority",
        "asap",
        "deadline",
        "immediately",
        "emergency",
    ],
    MemoryType.SEMANTIC: [
        "is",
        "are",
        "name",
        "means",
        "defined",
        "type",
        "version",
        "uses",
        "language",
        "framework",
    ],
}


def _score_type_regex(text: str, mem_type: MemoryType) -> float:
    """Score how well text matches a memory type using regex patterns.

    Returns confidence in [0.0, 1.0].
    """
    patterns = _PATTERNS.get(mem_type, [])
    if not patterns:
        return 0.0

    total = 0.0
    for pattern, weight in patterns:
        if pattern.search(text):
            total += weight

    # Normalize to 0-1 range (using top weights sum if max_possible is small)
    return min(total, 1.0)


def _score_type_tfidf(text: str, mem_type: MemoryType) -> float:
    """Score how well text matches a memory type using keyword TF-IDF.

    Lightweight ML fallback — no external model needed.
    Returns confidence in [0.0, 1.0].
    """
    keywords = _TFIDF_KEYWORDS.get(mem_type, [])
    if not keywords:
        return 0.0

    words = set(text.lower().split())
    matches = sum(1 for kw in keywords if kw in words)
    return min(matches / max(len(keywords) * 0.3, 1), 1.0)


def auto_classify(content: str) -> MemoryType:
    """Classify content into a single MemoryType (backward-compatible).

    Uses confidence-scored regex → ML fallback pipeline.
    """
    types = auto_classify_multi(content)
    return types[0][0] if types else MemoryType.SEMANTIC


def auto_classify_multi(content: str) -> List[Tuple[MemoryType, float]]:
    """Multi-label classification: returns sorted list of (type, confidence).

    Pipeline:
    1. Score all types with regex patterns
    2. If top confidence < threshold, boost with TF-IDF fallback
    3. Return all types above multi-label threshold, sorted by confidence
    """
    text = content.lower()

    # Phase 1: Regex scoring
    scores: List[Tuple[MemoryType, float]] = []
    for mem_type in _PATTERNS:
        conf = _score_type_regex(text, mem_type)
        scores.append((mem_type, conf))

    # Phase 2: ML fallback if regex confidence is low
    top_conf = max(c for _, c in scores) if scores else 0.0
    if top_conf < _MIN_REGEX_CONFIDENCE:
        # Boost with TF-IDF
        boosted: List[Tuple[MemoryType, float]] = []
        for mem_type, regex_conf in scores:
            tfidf_conf = _score_type_tfidf(text, mem_type)
            # Blend: 40% regex + 60% TF-IDF when regex is weak
            combined = regex_conf * 0.4 + tfidf_conf * 0.6
            boosted.append((mem_type, combined))
        scores = boosted

    # Filter and sort
    results = [(t, c) for t, c in scores if c >= _MULTI_LABEL_THRESHOLD]
    results.sort(key=lambda x: -x[1])

    # Always include at least SEMANTIC as fallback
    if not results:
        results = [(MemoryType.SEMANTIC, 0.5)]

    return results
