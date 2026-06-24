"""AgentConfig — explicit configuration object for AgentState (Phase 5).

Separating configuration from instantiation lets agents be:
  - Configured from environment variables (``AgentConfig.from_env()``)
  - Constructed from a serialized config (``AgentConfig.from_dict()``)
  - Validated at construction time, not at the first API call
  - Compared, diffed, and logged without exposing secrets

Usage::

    # Option A — keyword args (same as before)
    agent = AgentState(session_id="my-agent", backend="sqlite")

    # Option B — explicit config (recommended for production)
    cfg = AgentConfig(session_id="my-agent", backend="sqlite")
    agent = AgentState(config=cfg)

    # Option C — from environment
    cfg = AgentConfig.from_env()
    agent = AgentState(config=cfg)
"""

import os
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class AgentConfig:
    """Full configuration for an AgentState instance.

    All parameters have sensible defaults so ``AgentConfig()`` works out of
    the box for local development.

    Attributes:
        session_id:              Agent session identifier. If None, the facade
                                 works in sessionless mode (memory only).
        namespace:               Logical namespace to scope memories.
        backend:                 ``"sqlite"`` (default, persistent) or
                                 ``"memory"`` (ephemeral, for tests/scripts).
        db_path:                 SQLite file path. Defaults to
                                 ``~/.omem/brain.db``. Ignored in memory mode.
        endpoint:                Remote OMem endpoint URL (Cloud Phase C1).
                                 When set alongside ``api_key``, cloud mode
                                 will be used once Cloud Phase C1 ships.
        api_key:                 Cloud API key corresponding to ``endpoint``.
        org:                     Organization slug (cloud multi-tenant).
        embedding_model:         Sentence-transformers model name.
        context_cache_ttl:       Seconds to cache assembled context bundles.
                                 0 disables caching.
        context_default_mode:    Default retrieval mode for context assembly
                                 (``"planning"``, ``"coding"``, ``"chat"``,
                                 ``"recall"``).
        context_budget_tokens:   Default token budget for ``build_context()``.
        context_top_k_memories:  Max memories considered per context build.
        token_model:             OpenAI model name for exact tiktoken counting
                                 (e.g. ``"gpt-4o"``). Falls back to word-
                                 based approximation when None.
        auto_checkpoint:         When True (default), write a crash-recovery
                                 checkpoint on context-manager ``__exit__``.
    """

    session_id: Optional[str] = None
    namespace: str = "default"
    backend: str = "sqlite"
    db_path: Optional[str] = None

    # Cloud
    endpoint: Optional[str] = None
    api_key: Optional[str] = None
    org: Optional[str] = None

    # Memory engine
    embedding_model: str = "all-MiniLM-L6-v2"

    # Context engine
    context_cache_ttl: float = 30.0
    context_default_mode: str = "planning"
    context_budget_tokens: int = 6000
    context_top_k_memories: int = 15
    token_model: Optional[str] = None

    # Behavior
    auto_checkpoint: bool = True

    def __post_init__(self) -> None:
        if self.backend not in ("sqlite", "memory"):
            raise ValueError(
                f"backend must be 'sqlite' or 'memory', got {self.backend!r}"
            )
        if self.context_budget_tokens < 100:
            raise ValueError("context_budget_tokens must be >= 100")
        if not (0.0 <= self.context_cache_ttl):
            raise ValueError("context_cache_ttl must be >= 0")

    # ------------------------------------------------------------------
    # Factory methods
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls) -> "AgentConfig":
        """Build an ``AgentConfig`` from environment variables.

        Recognised variables:

        ============================================ ==========================
        Variable                                     Field
        ============================================ ==========================
        ``OMEM_SESSION_ID``                          ``session_id``
        ``OMEM_NAMESPACE``                           ``namespace``
        ``OMEM_BACKEND``                             ``backend``
        ``OMEM_DB``                                  ``db_path``
        ``OMEM_ENDPOINT``                            ``endpoint``
        ``OMEM_API_KEY``                             ``api_key``
        ``OMEM_ORG``                                 ``org``
        ``OMEM_EMBEDDING_MODEL``                     ``embedding_model``
        ``OMEM_CONTEXT_BUDGET``                      ``context_budget_tokens``
        ``OMEM_CONTEXT_MODE``                        ``context_default_mode``
        ``OMEM_CONTEXT_TOP_K``                       ``context_top_k_memories``
        ``OMEM_TOKEN_MODEL``                         ``token_model``
        ``OMEM_AUTO_CHECKPOINT``                     ``auto_checkpoint``
        ============================================ ==========================
        """
        def _int(var: str, default: int) -> int:
            try:
                return int(os.environ[var])
            except (KeyError, ValueError):
                return default

        def _float(var: str, default: float) -> float:
            try:
                return float(os.environ[var])
            except (KeyError, ValueError):
                return default

        def _bool(var: str, default: bool) -> bool:
            val = os.environ.get(var)
            if val is None:
                return default
            return val.lower() not in ("0", "false", "no", "off")

        return cls(
            session_id=os.environ.get("OMEM_SESSION_ID"),
            namespace=os.environ.get("OMEM_NAMESPACE", "default"),
            backend=os.environ.get("OMEM_BACKEND", "sqlite"),
            db_path=os.environ.get("OMEM_DB"),
            endpoint=os.environ.get("OMEM_ENDPOINT"),
            api_key=os.environ.get("OMEM_API_KEY"),
            org=os.environ.get("OMEM_ORG"),
            embedding_model=os.environ.get(
                "OMEM_EMBEDDING_MODEL", "all-MiniLM-L6-v2"
            ),
            context_cache_ttl=_float("OMEM_CONTEXT_CACHE_TTL", 30.0),
            context_budget_tokens=_int("OMEM_CONTEXT_BUDGET", 6000),
            context_default_mode=os.environ.get("OMEM_CONTEXT_MODE", "planning"),
            context_top_k_memories=_int("OMEM_CONTEXT_TOP_K", 15),
            token_model=os.environ.get("OMEM_TOKEN_MODEL"),
            auto_checkpoint=_bool("OMEM_AUTO_CHECKPOINT", True),
        )

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "AgentConfig":
        """Restore an ``AgentConfig`` from a plain dict (e.g. from JSON)."""
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in d.items() if k in known}
        return cls(**filtered)

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> Dict[str, Any]:
        """Serializable dict — excludes api_key for safety."""
        return {
            "session_id": self.session_id,
            "namespace": self.namespace,
            "backend": self.backend,
            "db_path": self.db_path,
            "endpoint": self.endpoint,
            "org": self.org,
            "embedding_model": self.embedding_model,
            "context_cache_ttl": self.context_cache_ttl,
            "context_default_mode": self.context_default_mode,
            "context_budget_tokens": self.context_budget_tokens,
            "context_top_k_memories": self.context_top_k_memories,
            "token_model": self.token_model,
            "auto_checkpoint": self.auto_checkpoint,
        }

    # ------------------------------------------------------------------
    # Derived helpers
    # ------------------------------------------------------------------

    @property
    def is_cloud(self) -> bool:
        """True when both endpoint and api_key are set."""
        return bool(self.endpoint and self.api_key)

    @property
    def resolved_db_path(self) -> Optional[str]:
        """Effective DB path: explicit or the default ``~/.omem/brain.db``."""
        if self.backend == "memory":
            return None
        return self.db_path or os.path.expanduser("~/.omem/brain.db")

    def __repr__(self) -> str:
        mode = "cloud" if self.is_cloud else f"local:{self.backend}"
        return (
            f"AgentConfig(session={self.session_id!r}, "
            f"namespace={self.namespace!r}, mode={mode!r})"
        )
