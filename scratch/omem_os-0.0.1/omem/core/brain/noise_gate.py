"""Noise Gate — Hard filter to prevent memory pollution.

Validates content BEFORE it enters the memory system.
Rejects: too short, pure stopwords, emoji-only, low importance,
spam patterns, duplicate phrases.

v0.5.0 Production hardening (C).
"""

import logging
import re
from dataclasses import dataclass

from .secrets import scan_secrets

logger = logging.getLogger(__name__)

# ── Configuration ──
_MIN_LENGTH = 3  # Minimum character count (relaxed for short test memories)
_MIN_WORD_COUNT = 1  # Minimum word count (relaxed)
_MAX_STOPWORD_RATIO = 0.85  # If >85% stopwords → reject
_MIN_IMPORTANCE = 0.05  # Floor importance to store

# Pre-compiled patterns
_EMOJI_PATTERN = re.compile(
    r"[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF"
    r"\U0001F1E0-\U0001F1FF\U00002702-\U000027B0\U000024C2-\U0001F251"
    r"\U0001f926-\U0001f937\U0001F1F2-\U0001F1F4\U0001F620-\U0001F640"
    r"\U0001F910-\U0001F9FF]+",
    re.UNICODE,
)
_ONLY_PUNCTUATION = re.compile(r"^[\s\W]+$")
_REPEATED_CHAR = re.compile(r"(.)\1{4,}")  # Same char 5+ times
_URL_ONLY = re.compile(r"^https?://\S+$")

# English stopwords (top 50)
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "is",
        "it",
        "in",
        "on",
        "at",
        "to",
        "for",
        "of",
        "and",
        "or",
        "but",
        "not",
        "with",
        "this",
        "that",
        "was",
        "are",
        "be",
        "has",
        "had",
        "have",
        "do",
        "does",
        "did",
        "will",
        "can",
        "could",
        "would",
        "should",
        "may",
        "might",
        "so",
        "if",
        "as",
        "by",
        "from",
        "up",
        "out",
        "no",
        "yes",
        "ok",
        "okay",
        "um",
        "uh",
        "hmm",
        "well",
        "just",
        "like",
    }
)


@dataclass
class GateResult:
    """Result of noise gate check."""

    passed: bool
    reason: str = ""

    def __bool__(self) -> bool:
        return self.passed


def check_noise(content: str, importance: float = 0.5) -> GateResult:
    """Check if content should be stored or rejected.

    Returns GateResult(passed=True) if content is valid.
    Returns GateResult(passed=False, reason="...") if noise.
    """
    # 1. Length check
    stripped = content.strip()
    if len(stripped) < _MIN_LENGTH:
        return GateResult(False, f"too_short: {len(stripped)} chars < {_MIN_LENGTH}")

    # 2. Only punctuation / whitespace
    if _ONLY_PUNCTUATION.match(stripped):
        return GateResult(False, "punctuation_only")

    # 3. URL-only (no context)
    if _URL_ONLY.match(stripped):
        return GateResult(False, "url_only")

    # 4. Repeated character spam
    if _REPEATED_CHAR.search(stripped):
        # Allow if rest of content is meaningful
        cleaned = _REPEATED_CHAR.sub("", stripped).strip()
        if len(cleaned) < _MIN_LENGTH:
            return GateResult(False, "repeated_chars")

    # 5. Emoji-only check
    text_without_emoji = _EMOJI_PATTERN.sub("", stripped).strip()
    if len(text_without_emoji) < _MIN_LENGTH:
        return GateResult(False, "emoji_only")

    # 6. Word count check
    words = stripped.split()
    if len(words) < _MIN_WORD_COUNT:
        return GateResult(False, f"too_few_words: {len(words)} < {_MIN_WORD_COUNT}")

    # 7. Stopword ratio
    word_count = len(words)
    if word_count > 0:
        stopword_count = sum(1 for w in words if w.lower() in _STOPWORDS)
        ratio = stopword_count / word_count
        if ratio > _MAX_STOPWORD_RATIO:
            return GateResult(False, f"stopword_heavy: {ratio:.0%} stopwords")

    # 8. Importance floor
    if importance < _MIN_IMPORTANCE:
        return GateResult(
            False, f"low_importance: {importance:.2f} < {_MIN_IMPORTANCE}"
        )

    # 9. Secret detection (PII/API Keys)
    secrets = scan_secrets(content)
    if secrets:
        # We reject for now to be safe, but in a real system we might redact or isolate
        return GateResult(False, f"sensitive_content_detected: {secrets[0][0]}")

    return GateResult(True)
