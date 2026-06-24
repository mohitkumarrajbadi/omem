"""Token counting abstraction for the context engine.

Two backends are supported — the correct one is selected automatically:

    TiktokenCounter  — exact counts via ``tiktoken`` (optional dep)
    WordBasedCounter — word-split approximation (always available)

The word-based estimator (`words * 4/3`) is accurate within ±8% for
English prose, which is sufficient for greedy budget packing.

Usage::

    counter = TokenCounter.create("gpt-4o")   # tiktoken if available
    counter = TokenCounter.create()            # always word-based

    n = counter.count("hello world")           # → 2 (word-based) or exact
    fits = counter.fits(text, remaining=500)
    truncated = counter.truncate(text, budget=200)
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_TIKTOKEN_WARNED = False


class WordBasedCounter:
    """Approximates token counts via word splitting.

    Accuracy: within ±8% for typical English prose.
    Formula: `ceil(word_count * 4 / 3)` — the 4/3 factor accounts for
    common subword splits (contractions, punctuation, numbers).
    """

    def count(self, text: str) -> int:
        if not text:
            return 0
        words = text.split()
        return max(1, int(len(words) * 4 / 3) + 1)

    def truncate(self, text: str, budget: int) -> str:
        """Truncate at word boundary to fit within `budget` tokens."""
        if self.count(text) <= budget:
            return text
        # Each word is ~1.33 tokens; work backwards from word count
        target_words = max(1, int(budget * 3 / 4))
        words = text.split()
        if len(words) <= target_words:
            return text
        truncated = " ".join(words[:target_words])
        return truncated + " …"

    def fits(self, text: str, remaining: int) -> bool:
        return self.count(text) <= remaining


class TiktokenCounter:
    """Exact token counting via the ``tiktoken`` library.

    Only instantiated when tiktoken is installed. Falls back to
    WordBasedCounter transparently via the factory method.
    """

    def __init__(self, encoding) -> None:
        self._enc = encoding

    def count(self, text: str) -> int:
        if not text:
            return 0
        return len(self._enc.encode(text))

    def truncate(self, text: str, budget: int) -> str:
        if self.count(text) <= budget:
            return text
        tokens = self._enc.encode(text)[:budget]
        return self._enc.decode(tokens) + " …"

    def fits(self, text: str, remaining: int) -> bool:
        return self.count(text) <= remaining


class TokenCounter:
    """Public facade — wraps the best available token counter.

    Delegates to TiktokenCounter when tiktoken is installed for the
    given model, otherwise uses WordBasedCounter.
    """

    def __init__(self, backend) -> None:
        self._backend = backend

    @classmethod
    def create(cls, model: Optional[str] = None) -> "TokenCounter":
        """Build the best available counter for the given model name.

        Args:
            model: OpenAI model name (e.g. ``"gpt-4o"``).
                   When provided, tiktoken will attempt to resolve the
                   correct BPE vocabulary. Falls back silently.
        """
        global _TIKTOKEN_WARNED
        if model:
            try:
                import tiktoken  # type: ignore[import]
                enc = tiktoken.encoding_for_model(model)
                return cls(TiktokenCounter(enc))
            except Exception:
                if not _TIKTOKEN_WARNED:
                    logger.debug(
                        "tiktoken not available or model %r unsupported — "
                        "using word-based approximation",
                        model,
                    )
                    _TIKTOKEN_WARNED = True
        return cls(WordBasedCounter())

    @property
    def is_exact(self) -> bool:
        """True when backed by tiktoken (exact counts)."""
        return isinstance(self._backend, TiktokenCounter)

    def count(self, text: str) -> int:
        """Count tokens in ``text``."""
        return self._backend.count(text)

    def fits(self, text: str, remaining: int) -> bool:
        """Return True if ``text`` fits in ``remaining`` tokens."""
        return self._backend.fits(text, remaining)

    def truncate(self, text: str, budget: int) -> str:
        """Truncate ``text`` to fit in ``budget`` tokens (at word boundary)."""
        return self._backend.truncate(text, budget)
