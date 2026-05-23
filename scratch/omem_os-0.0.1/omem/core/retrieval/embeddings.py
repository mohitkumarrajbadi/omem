"""Embedding abstraction with sentence-transformers and random fallback."""

import os
import logging
from functools import lru_cache

import numpy as np

# Suppress noisy HuggingFace Hub warnings by default.
# Users can override by setting HF_HUB_OFFLINE=0 in their environment.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")

logger = logging.getLogger(__name__)

_DIMENSION = 384  # all-MiniLM-L6-v2 output dimension


# Standalone cached hash-embed function (must be module-level for lru_cache)
@lru_cache(maxsize=10000)
def _cached_hash_embed(text: str, dim: int) -> bytes:
    """Deterministic hash-based embedding (cached, returns bytes for hashability)."""
    import hashlib

    salts = ["salt1", "salt2", "salt3", "salt4"]
    vec = np.zeros(dim, dtype=np.float32)

    for i, salt in enumerate(salts):
        h = hashlib.sha256((text + salt).encode()).digest()
        chunk = np.frombuffer(h, dtype=np.int8).astype(np.float32) / 128.0

        start = (i * len(chunk)) % dim
        end = min(start + len(chunk), dim)
        vec[start:end] += chunk[: end - start]

    # L2-normalise
    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec.tobytes()


class Embedder:
    """Embeds text into dense vectors.

    Uses ``sentence-transformers`` (``all-MiniLM-L6-v2``) when available,
    otherwise falls back to deterministic hash-based vectors so that the
    library works out-of-the-box without downloading a 90 MB model.

    Includes an LRU cache for repeated encode() calls.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2", provider: str = "local"):
        self.provider = provider
        self._model = None
        self._openai_client = None
        self._encode_cache: dict[str, np.ndarray] = {}
        self._cache_max = 10000
        self._model_loaded = False  # lazy flag

        if provider == "openai":
            self.dim = 1536
            self._model_name = (
                model_name
                if model_name != "all-MiniLM-L6-v2"
                else "text-embedding-3-small"
            )
            self._use_st = False
            self._try_load_openai()  # OpenAI client is cheap to init
        else:
            self.dim = _DIMENSION
            self._model_name = model_name
            self._use_st = False
            # *** LAZY: do NOT load model here — wait until first encode() call ***

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------

    def _try_load_openai(self) -> None:
        try:
            from openai import OpenAI

            self._openai_client = OpenAI()
            logger.info(
                "Loaded OpenAI embeddings client with model: %s", self._model_name
            )
        except ImportError:
            logger.error("OpenAI package not installed. Run `pip install openai`")
            raise
        except Exception as e:
            logger.error("Failed to initialize OpenAI client: %s", str(e))
            raise

    def _try_load_model(self) -> None:
        """Load sentence-transformers model (called lazily on first encode)."""
        if self._model_loaded:
            return
        self._model_loaded = True  # set early to prevent re-entry on failure
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore

            self._model = SentenceTransformer(self._model_name)
            self._use_st = True
            logger.debug("Loaded sentence-transformers model: %s", self._model_name)
        except Exception as e:
            logger.debug(
                "sentence-transformers not available (%s). Using fast hash-based embedder.",
                str(e),
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def encode(self, text: str) -> np.ndarray:
        """Return a unit-norm float32 vector of shape ``(dim,)``.

        Results are cached for repeated calls with the same text.
        Model is loaded lazily on the first call.
        """
        # Check cache first — fastest path
        cached = self._encode_cache.get(text)
        if cached is not None:
            return cached.copy()

        if self.provider == "openai" and self._openai_client is not None:
            res = self._openai_client.embeddings.create(
                input=[text], model=self._model_name
            )
            vec = np.array(res.data[0].embedding, dtype=np.float32)
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
        else:
            # Lazy-load the sentence-transformers model on first call
            if not self._model_loaded:
                self._try_load_model()

            if self._use_st and self._model is not None:
                vec = self._model.encode(text, convert_to_numpy=True).astype(np.float32)
                norm = np.linalg.norm(vec)
                if norm > 0:
                    vec = vec / norm
            else:
                # Instant hash-based fallback — zero ML overhead
                vec = np.frombuffer(
                    _cached_hash_embed(text, self.dim), dtype=np.float32
                ).copy()

        # Store in bounded LRU cache
        if len(self._encode_cache) >= self._cache_max:
            oldest = next(iter(self._encode_cache))
            del self._encode_cache[oldest]
        self._encode_cache[text] = vec
        return vec.copy()

    def encode_batch(self, texts: list[str]) -> np.ndarray:
        """Encode multiple texts, returning ``(N, dim)`` float32 matrix."""
        if self.provider == "openai" and self._openai_client is not None:
            res = self._openai_client.embeddings.create(
                input=texts, model=self._model_name
            )
            vecs = np.array([r.embedding for r in res.data], dtype=np.float32)
        else:
            # Lazy-load on first batch encode too
            if not self._model_loaded:
                self._try_load_model()

            if self._use_st and self._model is not None:
                vecs = self._model.encode(
                    texts, convert_to_numpy=True, show_progress_bar=False
                ).astype(np.float32)
            else:
                vecs = np.array(
                    [
                        np.frombuffer(
                            _cached_hash_embed(t, self.dim), dtype=np.float32
                        ).copy()
                        for t in texts
                    ],
                    dtype=np.float32,
                )
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return vecs / norms
