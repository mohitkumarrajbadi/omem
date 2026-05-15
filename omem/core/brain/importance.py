"""Importance and decay engine.

Calculates memory importance based on user input, recency, and access frequency.
Also handles automatic deactivation for low-value memories.
"""

import time
import math
import re
from typing import List, Optional

try:
    import omem_rust
except ImportError:
    omem_rust = None

from ...types import Memory, MemoryPriority

# Scoring weights
_W_IMPORTANCE = 0.50
_W_RECENCY = 0.30
_W_FREQUENCY = 0.20

# Decay configuration
_RECENCY_HALF_LIFE = 3600.0 * 24  # 24 hours
_DECAY_THRESHOLD = 0.05  # memories below this are deactivated
_MAX_FREQUENCY_BONUS = 1.0  # cap on frequency contribution
_FREQUENCY_LOG_BASE = 10  # log base for diminishing returns


# Heuristics for estimating importance
_HIGH_IMPORTANCE_SIGNALS = [
    (
        0.9,
        [
            re.compile(r"\bname\s+is\b"),
            re.compile(r"\bi\s+am\b"),
            re.compile(r"\bmy\s+name\b"),
        ],
    ),  # identity
    (
        0.85,
        [
            re.compile(r"\bprefer"),
            re.compile(r"\bfavorite\b"),
            re.compile(r"\balways\b"),
            re.compile(r"\bnever\b"),
        ],
    ),  # preferences
    (
        0.8,
        [
            re.compile(r"\bpassword\b"),
            re.compile(r"\bapi.?key\b"),
            re.compile(r"\bsecret\b"),
            re.compile(r"\btoken\b"),
        ],
    ),  # secrets
    (
        0.8,
        [
            re.compile(r"\bborn\b"),
            re.compile(r"\bbirthday\b"),
            re.compile(r"\baddress\b"),
            re.compile(r"\bphone\b"),
        ],
    ),  # PII
    (
        0.75,
        [re.compile(r"\bdecided\b"), re.compile(r"\bchose\b"), re.compile(r"\bcommit")],
    ),  # decisions
    (
        0.7,
        [
            re.compile(r"\bgoal\b"),
            re.compile(r"\bobjective\b"),
            re.compile(r"\bmission\b"),
            re.compile(r"\btarget\b"),
        ],
    ),  # goals
]

_LOW_IMPORTANCE_SIGNALS = [
    (
        0.2,
        [
            re.compile(r"\bokay\b"),
            re.compile(r"\bsure\b"),
            re.compile(r"\bgot\s+it\b"),
            re.compile(r"\bthanks?\b"),
        ],
    ),  # filler
    (
        0.25,
        [
            re.compile(r"\btest\b.*\btest\b"),
            re.compile(r"\basdf\b"),
            re.compile(r"\bfoo\b.*\bbar\b"),
        ],
    ),  # test data
    (
        0.3,
        [re.compile(r"\bhi\b$"), re.compile(r"\bhello\b$"), re.compile(r"\bhey\b$")],
    ),  # greetings
]

# Priority signals
_CORE_SIGNALS = [
    re.compile(r"\bname\s+is\b"),
    re.compile(r"\bi\s+am\b"),
    re.compile(r"\bmy\s+name\b"),
    re.compile(r"\bpassword\b"),
    re.compile(r"\bapi.?key\b"),
    re.compile(r"\bsecret\b"),
    re.compile(r"\bborn\b"),
    re.compile(r"\bbirthday\b"),
    re.compile(r"\baddress\b"),
    re.compile(r"\bphone\b"),
]

_HIGH_SIGNALS = [
    re.compile(r"\bgoal\b"),
    re.compile(r"\bobjective\b"),
    re.compile(r"\bmission\b"),
    re.compile(r"\btarget\b"),
    re.compile(r"\bprefer"),
    re.compile(r"\bfavorite\b"),
    re.compile(r"\balways\b"),
    re.compile(r"\bnever\b"),
    re.compile(r"\bdecided\b"),
    re.compile(r"\bchose\b"),
    re.compile(r"\bcommit"),
]

_LOW_SIGNALS = [
    re.compile(r"\bokay\b"),
    re.compile(r"\bsure\b"),
    re.compile(r"\bgot\s+it\b"),
    re.compile(r"\bthanks?\b"),
    re.compile(r"\btest\b.*\btest\b"),
    re.compile(r"\basdf\b"),
    re.compile(r"\bfoo\b.*\bbar\b"),
    re.compile(r"\bhi\b$"),
    re.compile(r"\bhello\b$"),
    re.compile(r"\bhey\b$"),
]


def estimate_importance(content: str) -> float:
    """Auto-estimate importance of content from 0.0 to 1.0."""
    text = content.lower().strip()

    # Check high-importance signals (return on first match)
    for score, patterns in _HIGH_IMPORTANCE_SIGNALS:
        for p in patterns:
            if p.search(text):
                return score

    # Check low-importance signals
    for score, patterns in _LOW_IMPORTANCE_SIGNALS:
        for p in patterns:
            if p.search(text):
                return score

    # Length-based heuristic: longer = usually more informative
    word_count = len(text.split())
    if word_count < 3:
        return 0.3
    elif word_count < 10:
        return 0.5
    elif word_count < 30:
        return 0.6
    else:
        return 0.7


def estimate_priority(content: str) -> MemoryPriority:
    """Auto-classify content into a priority level."""
    text = content.lower().strip()

    for p in _CORE_SIGNALS:
        if p.search(text):
            return MemoryPriority.CORE

    for p in _HIGH_SIGNALS:
        if p.search(text):
            return MemoryPriority.HIGH

    for p in _LOW_SIGNALS:
        if p.search(text):
            return MemoryPriority.LOW

    return MemoryPriority.NORMAL


def estimate_importance_batch(contents: List[str]) -> List[float]:
    """Batch estimate importance using Rust acceleration if available."""
    if omem_rust and hasattr(omem_rust, "cognition_classify_batch"):
        high_sigs = [p[1][0].pattern for p in _HIGH_IMPORTANCE_SIGNALS]
        low_sigs = [p[1][0].pattern for p in _LOW_IMPORTANCE_SIGNALS]
        return omem_rust.cognition_classify_batch(contents, high_sigs, low_sigs)

    return [estimate_importance(c) for c in contents]


def estimate_priority_batch(contents: List[str]) -> List[MemoryPriority]:
    """Batch estimate priority using Rust acceleration if available."""
    if omem_rust:
        # Note: Current Rust implementation returns float scores,
        # we might need a more specific priority classifier in Rust.
        # For now, mapping from scores or just using Python loop.
        pass

    return [estimate_priority(c) for c in contents]


def compute_recency_score(
    timestamp: float, now: Optional[float] = None, half_life: float = _RECENCY_HALF_LIFE
) -> float:
    """Exponential recency decay: 1.0 when fresh, halves every half_life seconds."""
    now = now or time.time()
    age = max(now - timestamp, 0.0)
    return 2.0 ** (-age / half_life)


def compute_frequency_score(access_count: int) -> float:
    """Logarithmic frequency bonus with diminishing returns."""
    if access_count <= 0:
        return 0.0
    return min(math.log(1 + access_count, _FREQUENCY_LOG_BASE), _MAX_FREQUENCY_BONUS)


def compute_composite_score(
    memory: Memory,
    vector_score: float = 0.0,
    keyword_score: float = 0.0,
    now: Optional[float] = None,
) -> float:
    """Compute the full composite retrieval score."""
    recency = compute_recency_score(memory.timestamp, now)
    frequency = compute_frequency_score(memory.access_count)

    # Base retrieval signal (vector + keyword)
    retrieval_signal = 0.55 * vector_score + 0.20 * keyword_score

    # Memory quality signal (importance + utility + recency + frequency)
    # Utility score is a strong signal for retention/retrieval
    quality_signal = (
        0.40 * memory.importance
        + 0.25 * memory.utility_score
        + 0.20 * recency
        + 0.15 * frequency
    )

    return 0.50 * retrieval_signal + 0.50 * quality_signal


def should_decay(memory: Memory, now: Optional[float] = None) -> bool:
    """Return True if memory's recency score has dropped below threshold.

    Adaptive Decay: High utility or CORE priority prevents decay.
    """
    if getattr(memory, "priority", None) == MemoryPriority.CORE:
        return False

    recency = compute_recency_score(memory.timestamp, now)

    # Utility-augmented decay threshold:
    # High utility memories effectively "age" much slower.
    effective_utility = getattr(memory, "utility_score", 0.0)

    # If utility is very high (>0.8), protect from decay entirely for 10x longer
    if effective_utility > 0.8:
        return False

    effective_score = recency * (memory.importance * 0.7 + effective_utility * 0.3)
    return effective_score < _DECAY_THRESHOLD


from enum import Enum  # noqa: E402


class ResolutionStrategy(Enum):
    """Strategies for resolving logical contradictions."""

    LATEST_WINS = 0
    HIGHEST_CONFIDENCE = 1
    CONSENSUS = 2
    LLM_RESOLVE = 3


def compute_confidence_score(memory: Memory) -> float:
    """Calculate the reliability of a memory based on source and consistency."""
    # 1. Source base reliability
    source_weights = {
        "user": 1.0,
        "system": 0.9,
        "reflection": 0.8,
        "inference": 0.6,
        "external": 0.5,
    }
    base_conf = source_weights.get(memory.source.lower(), 0.7)

    # 2. Consensus bonus (verified by others)
    consensus_bonus = min(len(memory.verifiers) * 0.1, 0.2)

    # 3. Conflict penalty (if ever marked as CONFLICTED)
    from ...types import MemoryStatus

    conflict_penalty = 0.2 if memory.status == MemoryStatus.CONFLICTED else 0.0

    # 4. Utility feedback influence
    utility_mod = memory.utility_score * 0.2

    final_conf = base_conf + consensus_bonus - conflict_penalty + utility_mod
    return max(min(final_conf, 1.0), 0.0)


def resolve_conflict(
    memories: List[Memory],
    strategy: ResolutionStrategy = ResolutionStrategy.LATEST_WINS,
    summarizer=None,
) -> Optional[Memory]:
    """Resolve a set of conflicting memories into a single truth."""
    if not memories:
        return None
    if len(memories) == 1:
        return memories[0]

    if strategy == ResolutionStrategy.LATEST_WINS:
        return max(memories, key=lambda m: m.timestamp)

    elif strategy == ResolutionStrategy.HIGHEST_CONFIDENCE:
        # Re-calc confidence for comparison
        for m in memories:
            m.confidence_score = compute_confidence_score(m)
        return max(memories, key=lambda m: m.confidence_score)

    elif strategy == ResolutionStrategy.CONSENSUS:
        # Pick the one with the most verifiers/accesses
        return max(memories, key=lambda m: m.access_count + len(m.verifiers))

    elif strategy == ResolutionStrategy.LLM_RESOLVE and summarizer:
        # This strategy is typically handled in BrainTrace.consolidate()
        # via reflect_on_conflicts, but we keep the hook here.
        pass

    return memories[0]


def run_decay_sweep(memories: List[Memory], now: Optional[float] = None) -> List[str]:
    """Mark memories as inactive if they've decayed. Returns list of deactivated IDs."""
    deactivated = []
    for mem in memories:
        if mem.active and should_decay(mem, now):
            mem.active = False
            deactivated.append(mem.id)
    return deactivated
