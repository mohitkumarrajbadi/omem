"""Embedding abstraction with sentence-transformers and hash fallback.

Default is semantic: load ``all-MiniLM-L6-v2`` when installed.
Hash embeddings are used only when ``OMEM_EMBEDDER=hash`` is set, or when
the model cannot be loaded (logged at ERROR — recall will be weak).
"""

import logging
import os
from functools import lru_cache

# Must be set before numpy, FAISS, or sentence-transformers are imported to
# prevent libomp.dylib conflicts on macOS (conda/Anaconda environments).
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
# Suppress tokenizer fork warnings and noisy model-load output.
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")

import numpy as np

logger = logging.getLogger(__name__)

_HASH_FALLBACK_LOGGED = False
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


def _embedder_mode(provider: str) -> str:
    """Resolve ``OMEM_EMBEDDER``: auto | hash | st | openai."""
    raw = os.environ.get("OMEM_EMBEDDER", "").strip().lower()
    if raw in ("hash", "st", "auto", "openai"):
        return raw
    if provider == "openai":
        return "openai"
    return "auto"


@lru_cache(maxsize=4)
def _sentence_transformer(model_name: str):
    """One MiniLM process-wide — avoid reloading weights per Embedder."""
    from sentence_transformers import SentenceTransformer  # type: ignore

    return SentenceTransformer(model_name)


class Embedder:
    """Embeds text into dense vectors.

    Production path: ``sentence-transformers`` (``all-MiniLM-L6-v2``).
    Hash fallback is explicit (``OMEM_EMBEDDER=hash``) or last-resort when
    the model is missing. Includes an LRU cache for repeated ``encode()``.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2", provider: str = "local"):
        self.provider = provider
        self._model = None
        self._openai_client = None
        self._encode_cache: dict[str, np.ndarray] = {}
        self._cache_max = 10000
        self._model_loaded = False  # lazy flag
        self._kind = "hash"
        self._mode = _embedder_mode(provider)

        if self._mode == "openai" or provider == "openai":
            self.provider = "openai"
            self.dim = 1536
            self._model_name = (
                model_name
                if model_name != "all-MiniLM-L6-v2"
                else "text-embedding-3-small"
            )
            self._use_st = False
            self._kind = "openai"
            self._try_load_openai()  # OpenAI client is cheap to init
        else:
            self.dim = _DIMENSION
            self._model_name = model_name
            self._use_st = False
            if self._mode == "hash":
                self._model_loaded = True
                self._kind = "hash"
            # else lazy-load ST on first encode()

    @property
    def model_version(self) -> str:
        """Stable version string for embedding migration tracking.

        Prefixed with ``st:`` or ``hash:`` so upgrades from the hash fallback
        to sentence-transformers are detectable in stored rows.
        """
        if self.provider == "openai":
            return f"openai:{self._model_name}:v1:{self.dim}"
        if not self._model_loaded:
            self._try_load_model()
        kind = self._kind if self._kind else ("st" if self._use_st else "hash")
        return f"{kind}:{self._model_name}:v1:{self.dim}"

    @property
    def kind(self) -> str:
        """``st``, ``hash``, or ``openai``."""
        if not self._model_loaded and self.provider != "openai":
            self._try_load_model()
        return self._kind

    @property
    def is_semantic(self) -> bool:
        """True when vectors come from a real embedding model, not hashes."""
        return self.kind in ("st", "openai")

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
        if self._mode == "hash":
            self._kind = "hash"
            self._use_st = False
            return
        try:
            self._model = _sentence_transformer(self._model_name)
            self._use_st = True
            self._kind = "st"
            logger.info("Loaded sentence-transformers model: %s", self._model_name)
        except Exception as e:
            if self._mode == "st":
                raise RuntimeError(
                    "OMEM_EMBEDDER=st but sentence-transformers failed to load. "
                    "Install with: pip install 'omem-os[embeddings]'"
                ) from e
            self._kind = "hash"
            self._use_st = False
            global _HASH_FALLBACK_LOGGED
            if not _HASH_FALLBACK_LOGGED:
                _HASH_FALLBACK_LOGGED = True
                logger.error(
                    "Semantic embeddings unavailable (%s). Using hash vectors — "
                    "recall quality will be weak. Production install: "
                    "pip install 'omem-os[embeddings]'. To silence this, set "
                    "OMEM_EMBEDDER=hash.",
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
