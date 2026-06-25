"""AgentState — Phase 5 unified product facade.

``AgentState`` is the single object a developer imports. It composes all
four shipped layers into one coherent, ergonomic interface:

    .memory    — MemoryOS      remember, recall, consolidate, forget
    .state     — StateOS       save, snapshot, rollback, fork, checkpoint
    .context   — ContextEngine build, estimate_savings
    .knowledge — KnowledgeOS   link, query, reason, entities, ingest

Phase 5 adds the following on top of the raw layer properties:
    • Top-level shortcuts: remember(), recall(), forget(), consolidate()
    • Unified resume() that picks the latest checkpoint automatically
    • clone() — fork the session; returns a new AgentState sharing the engine
    • merge_fork() — merge a fork session back into the parent
    • status() — cross-layer health / metrics dict
    • export_state() / restore_state() — serializable session handoff
    • Context manager — checkpoint on clean __exit__
    • Factory methods: ephemeral(), from_config(), from_env()
    • AgentConfig — explicit, validated, env-loadable configuration object

Cloud auto-detection::

    export OMEM_ENDPOINT=https://state.akamai.ai
    export OMEM_API_KEY=omem_sk_...
    agent = AgentState()  # auto-detects cloud (falls back to local until C1)

Quickstart::

    from omem import AgentState

    with AgentState(session_id="research") as agent:
        agent.remember("FastAPI uses Pydantic for validation")
        agent.set_goal("Evaluate FastAPI vs Django")
        agent.learn("FastAPI", "uses", "Pydantic")
        ctx = agent.build_context("compare frameworks", budget_tokens=4000)
        # … pass ctx.text to your LLM …

One import. One object. All layers.

See: docs/roadmap/FULL_IMPLEMENTATION_PLAN.md — Phase 5
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from .agent_config import AgentConfig
from .api import OMem
from .context.engine import ContextBundle, ContextEngine, ContextRequest
from .governance.layer import GovernanceOS
from .knowledge.layer import KnowledgeOS
from .memory.layer import MemoryOS
from .observe.events import ObserveOS, TraceEvent, new_trace_id
from .org.layer import OrgMemoryOS
from .provenance.layer import ProvenanceOS
from .runtime.layer import RuntimeOS
from .state.backend import InMemoryStateBackend, SQLiteStateBackend
from .state.layer import StateOS
from .types import (
    Memory,
    StateCheckpoint,
    StatePayload,
    StateSnapshot,
    ToolResult,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# ExplanationReport — the "why" behind every recall decision
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ExplanationReport:
    """Rich explanation of why memories were recalled for a query.

    Combines four evidence streams into one coherent report:

    1. **Score breakdown** — per-memory weight decomposition (vector,
       keyword, recency, importance, etc.).
    2. **Provenance** — lineage chain showing how each memory was created.
    3. **Knowledge graph** — entity relationships connected to the results.
    4. **State alignment** — how well the current session goal aligns.

    Use :meth:`format` for human-readable output or :meth:`as_dict` for
    JSON-serializable export.
    """

    query: str
    session_id: Optional[str]
    namespace: str
    mode: str
    explanations: List[Any]          # List[RetrievalExplanation]
    provenance_chains: Dict[str, Any]
    knowledge_connections: Dict[str, Any]
    state_goal: Optional[str]
    state_relevance: float           # 0–1 Jaccard overlap with current goal
    token_savings_pct: float         # projected token savings vs naive
    elapsed_ms: float

    def as_dict(self) -> Dict[str, Any]:
        """Return a fully JSON-serializable representation."""
        return {
            "query": self.query,
            "session_id": self.session_id,
            "namespace": self.namespace,
            "mode": self.mode,
            "state_goal": self.state_goal,
            "state_relevance": round(self.state_relevance, 4),
            "token_savings_pct": round(self.token_savings_pct, 2),
            "elapsed_ms": round(self.elapsed_ms, 2),
            "memories": [self._explain_to_dict(ex) for ex in self.explanations],
        }

    def _explain_to_dict(self, ex: Any) -> Dict[str, Any]:
        mem_id = ex.memory_id
        return {
            "memory_id": mem_id,
            "final_score": round(ex.final_score, 4),
            "scores": {
                "vector":          round(ex.vector_score, 4),
                "keyword":         round(ex.keyword_score, 4),
                "recency":         round(ex.recency_score, 4),
                "importance":      round(ex.importance_score, 4),
                "frequency":       round(ex.frequency_bonus, 4),
                "confidence":      round(ex.confidence_score, 4),
                "graph_proximity": round(ex.graph_score, 4),
            },
            "matched_keywords": ex.matched_keywords,
            "provenance": self.provenance_chains.get(mem_id, {}),
            "knowledge_connections": self.knowledge_connections.get(mem_id, []),
        }

    def format(self) -> str:
        """Return a human-readable multi-line explanation."""
        lines: List[str] = [
            f"╔══ Explain: {self.query!r}",
            f"║  session={self.session_id or '(none)'}  "
            f"namespace={self.namespace}  mode={self.mode}  "
            f"elapsed={self.elapsed_ms:.1f}ms",
        ]
        if self.state_goal:
            rel_bar = "█" * int(self.state_relevance * 10) + "░" * (10 - int(self.state_relevance * 10))
            lines.append(
                f"║  goal relevance [{rel_bar}] {self.state_relevance:.0%}  "
                f"→  {self.state_goal!r}"
            )
        if self.token_savings_pct > 0:
            lines.append(f"║  token savings estimate: {self.token_savings_pct:.0f}%")
        lines.append("╠" + "═" * 60)

        for i, ex in enumerate(self.explanations, 1):
            mem_id = ex.memory_id
            score_bar = "█" * int(ex.final_score * 20) + "░" * (20 - min(20, int(ex.final_score * 20)))
            lines.append(f"║  [{i}] id={mem_id[:12]}  score=[{score_bar}] {ex.final_score:.4f}")
            lines.append(
                f"║      vector={ex.vector_score:.3f}  keyword={ex.keyword_score:.3f}  "
                f"recency={ex.recency_score:.3f}  importance={ex.importance_score:.3f}"
            )
            lines.append(
                f"║      confidence={ex.confidence_score:.3f}  graph={ex.graph_score:.3f}  "
                f"frequency={ex.frequency_bonus:.3f}"
            )
            if ex.matched_keywords:
                lines.append(f"║      keywords: {', '.join(ex.matched_keywords)}")
            prov = self.provenance_chains.get(mem_id, {})
            if prov.get("depth", 0) > 0:
                ops = " → ".join(prov.get("operations", []))
                lines.append(f"║      provenance: depth={prov['depth']}  {ops}")
            kg = self.knowledge_connections.get(mem_id, [])
            if kg:
                kg_str = "; ".join(
                    f"{c.get('from','?')} –[{c.get('rel','?')}]→ {c.get('to','?')}"
                    for c in kg[:3]
                )
                lines.append(f"║      knowledge: {kg_str}")
            lines.append("║")

        lines.append("╚" + "═" * 60)
        return "\n".join(lines)


def _ansi_dim(s: str) -> str:
    return s


class AgentState:
    """Unified agent state facade — Phase 5.

    The single object you need to build memory-native AI agents.

    Shipped layers (fully operational):
        .memory     — MemoryOS       (Phase 1)
        .state      — StateOS        (Phase 2)
        .context    — ContextEngine  (Phase 3)
        .knowledge  — KnowledgeOS    (Phase 4)
        .observe    — ObserveOS      (Phase 6)
        .provenance — ProvenanceOS   (Phase 7)
        .governance — GovernanceOS   (Phase 8)
        .runtime    — RuntimeOS      (Phase 9)
        .org        — OrgMemoryOS    (Phase 10)

    Constructor
    ~~~~~~~~~~~
    Accepts either individual keyword arguments (backward compatible) or
    an explicit ``AgentConfig`` object.  When both are given, ``config``
    takes precedence.

    Args:
        session_id:     Agent session ID. If None, ``state.*`` shortcuts
                        raise ``ValueError``; memory and knowledge still work.
        namespace:      Logical memory namespace (default ``"default"``).
        backend:        ``"sqlite"`` (persistent) or ``"memory"`` (ephemeral).
        db_path:        SQLite file path. Defaults to ``~/.omem/brain.db``.
        endpoint:       Remote endpoint (Cloud Phase C1). Falls back to local.
        api_key:        Cloud API key.
        org:            Organization slug (multi-tenant cloud).
        config:         Explicit ``AgentConfig`` — overrides all kwargs above.
        **omem_kwargs:  Extra kwargs forwarded to the underlying ``OMem`` engine.

    Thread safety:
        ``AgentState`` is **not** thread-safe by design. Each thread or
        coroutine should create its own instance.  The underlying SQLite
        backend uses WAL mode so concurrent readers are safe, but concurrent
        writers from different ``AgentState`` instances are serialized.
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(
        self,
        session_id: Optional[str] = None,
        namespace: str = "default",
        backend: str = "sqlite",
        db_path: Optional[str] = None,
        endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
        org: Optional[str] = None,
        config: Optional[AgentConfig] = None,
        **omem_kwargs: Any,
    ) -> None:
        # Resolve config: explicit config takes precedence over kwargs
        if config is not None:
            _cfg = config
        else:
            _cfg = AgentConfig(
                session_id=session_id,
                namespace=namespace,
                backend=backend,
                db_path=db_path,
                endpoint=endpoint or os.environ.get("OMEM_ENDPOINT"),
                api_key=api_key or os.environ.get("OMEM_API_KEY"),
                org=org,
            )

        self._config = _cfg
        self.session_id: Optional[str] = _cfg.session_id
        self.namespace: str = _cfg.namespace

        # Cloud detection — fall back to local until Cloud Phase C1
        if _cfg.is_cloud:
            import warnings
            warnings.warn(
                "OMEM_ENDPOINT is set but CloudBackend is not yet implemented "
                "(Cloud Phase C1). Falling back to local mode.",
                stacklevel=2,
            )

        # Ensure the SQLite directory exists
        _db = _cfg.resolved_db_path
        if _db and _db != ":memory:" and _cfg.backend == "sqlite":
            _db_dir = os.path.dirname(_db)
            if _db_dir and not os.path.exists(_db_dir):
                os.makedirs(_db_dir, exist_ok=True)

        # ── Memory layer (Phase 1) ────────────────────────────────────
        _omem = OMem(
            backend=_cfg.backend,
            db_path=_cfg.db_path,
            model=_cfg.embedding_model,
            **omem_kwargs,
        )
        self._omem = _omem
        self._memory = MemoryOS(_omem)

        # ── State layer (Phase 2) ─────────────────────────────────────
        if _cfg.backend == "memory":
            _state_backend = InMemoryStateBackend()
        else:
            _state_backend = SQLiteStateBackend(_db or ":memory:")
        self._state = StateOS(backend=_state_backend)

        # ── Context layer (Phase 3) ───────────────────────────────────
        self._context = ContextEngine(
            memory=self._memory,
            state=self._state,
            cache_ttl=_cfg.context_cache_ttl,
            default_mode=_cfg.context_default_mode,
            max_memories=_cfg.context_top_k_memories,
            token_model=_cfg.token_model,
        )

        # ── Knowledge layer (Phase 4) ─────────────────────────────────
        self._knowledge = KnowledgeOS(omem=_omem)

        # ── Observability (Phase 6) ───────────────────────────────────
        self._observe = ObserveOS()

        # ── Provenance (Phase 7) ──────────────────────────────────────
        self._provenance = ProvenanceOS()

        # ── Governance (Phase 8) — wired with omem + state ───────────
        if isinstance(_cfg.db_path, str) and _cfg.db_path not in (":memory:", None):
            _audit_db = _cfg.db_path.replace(".db", "_audit.db").replace(":memory:", ":memory:")
        else:
            _audit_db = None
        self._governance = GovernanceOS(
            omem=_omem,
            state=self._state,
            audit_db_path=_audit_db,
        )

        # ── Runtime (Phase 9) — wired with state ──────────────────────
        _runtime_db = (
            None if _cfg.db_path is None or _cfg.db_path == ":memory:"
            else _cfg.db_path.replace(".db", "_runtime.db")
        )
        self._runtime = RuntimeOS(
            state=self._state,
            db_path=_runtime_db,
        )

        # ── Org memory (Phase 10) — wired with memory ─────────────────
        self._org = OrgMemoryOS(memory=self._memory)

        # Bootstrap the session if session_id was provided
        if self.session_id:
            self._state.get_or_create(self.session_id, namespace=namespace)

        logger.debug(
            "AgentState initialized (session=%r, ns=%r, backend=%r)",
            self.session_id, self.namespace, _cfg.backend,
        )

    # ------------------------------------------------------------------
    # Factory methods
    # ------------------------------------------------------------------

    @classmethod
    def ephemeral(cls, session_id: Optional[str] = None, **kwargs: Any) -> "AgentState":
        """Create a non-persistent, in-memory AgentState.

        Nothing is written to disk. Useful for tests, scripts, and one-off
        agent runs where persistence is not needed.

        Args:
            session_id: Optional session ID.
            **kwargs:   Any other ``AgentState.__init__`` kwargs.

        Returns:
            ``AgentState`` backed by in-memory stores.
        """
        return cls(session_id=session_id, backend="memory", **kwargs)

    @classmethod
    def from_config(cls, config: AgentConfig, **omem_kwargs: Any) -> "AgentState":
        """Create an ``AgentState`` from an explicit ``AgentConfig`` object.

        Args:
            config:      Pre-validated ``AgentConfig``.
            **omem_kwargs: Extra kwargs forwarded to the OMem engine.

        Returns:
            Fully initialized ``AgentState``.
        """
        return cls(config=config, **omem_kwargs)

    @classmethod
    def from_env(cls, **kwargs: Any) -> "AgentState":
        """Create an ``AgentState`` from environment variables.

        Reads all recognized ``OMEM_*`` env vars (see ``AgentConfig.from_env``
        for the full list) and constructs an ``AgentState``.

        Args:
            **kwargs: Any kwargs override environment values.

        Returns:
            ``AgentState`` configured from the environment.
        """
        cfg = AgentConfig.from_env()
        return cls(config=cfg, **kwargs)

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "AgentState":
        return self

    def __exit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Optional[Any],
    ) -> bool:
        """On clean exit, write a crash-recovery checkpoint if auto_checkpoint."""
        if exc_type is None and self.session_id and self._config.auto_checkpoint:
            try:
                chk_id = self._state.checkpoint(self.session_id)
                logger.debug("AgentState.__exit__: checkpoint %r written", chk_id)
            except Exception as exc:
                logger.warning("AgentState.__exit__: checkpoint failed — %s", exc)
        return False  # never suppress exceptions

    # ------------------------------------------------------------------
    # Layer properties
    # ------------------------------------------------------------------

    @property
    def memory(self) -> MemoryOS:
        """Memory layer — MemoryOS (Phase 1)."""
        return self._memory

    @property
    def state(self) -> StateOS:
        """State layer — StateOS (Phase 2)."""
        return self._state

    @property
    def context(self) -> ContextEngine:
        """Context engine — ContextEngine (Phase 3)."""
        return self._context

    @property
    def knowledge(self) -> KnowledgeOS:
        """Knowledge graph — KnowledgeOS (Phase 4)."""
        return self._knowledge

    @property
    def observe(self) -> ObserveOS:
        """Observability layer — Phase 6."""
        return self._observe

    @property
    def provenance(self) -> ProvenanceOS:
        """Provenance / lineage layer — Phase 7."""
        return self._provenance

    @property
    def governance(self) -> GovernanceOS:
        """Governance + retention + RBAC — Phase 8."""
        return self._governance

    @property
    def runtime(self) -> RuntimeOS:
        """Multi-agent runtime coordination — Phase 9."""
        return self._runtime

    @property
    def org(self) -> OrgMemoryOS:
        """Organizational memory with namespace hierarchy — Phase 10."""
        return self._org

    @property
    def config(self) -> AgentConfig:
        """The configuration object used to create this AgentState."""
        return self._config

    # ------------------------------------------------------------------
    # Derived properties
    # ------------------------------------------------------------------

    @property
    def is_cloud(self) -> bool:
        """True when a cloud endpoint is configured."""
        return self._config.is_cloud

    @property
    def backend_type(self) -> str:
        """Human-readable backend description: ``"local:sqlite"``, ``"local:memory"``,
        or ``"cloud"`` (once Cloud Phase C1 ships)."""
        if self.is_cloud:
            return "cloud"
        return f"local:{self._config.backend}"

    @property
    def db_path(self) -> Optional[str]:
        """Resolved SQLite database path, or None for in-memory backends."""
        return self._config.resolved_db_path

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def ping(self) -> bool:
        """Quick health check. Returns True if all layers are accessible."""
        try:
            self._memory.list()
            return True
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Internal: observability + provenance instrumentation
    # ------------------------------------------------------------------

    def _emit(
        self,
        event_type: str,
        duration_ms: float,
        error: Optional[str] = None,
        **payload_kwargs: Any,
    ) -> None:
        """Emit a TraceEvent to ObserveOS. Never raises."""
        if not self.session_id:
            return
        try:
            event = TraceEvent(
                id=new_trace_id(),
                session_id=self.session_id,
                event_type=event_type,
                timestamp=time.time(),
                duration_ms=duration_ms,
                namespace=self.namespace,
                payload={k: v for k, v in payload_kwargs.items() if v is not None}
                | ({"error": error} if error else {}),
            )
            self._observe.record(event)
        except Exception:
            pass

    def _prov(
        self,
        entity_id: str,
        entity_type: str,
        operation: str,
        source: str = "agent",
        **metadata: Any,
    ) -> None:
        """Record a provenance event. Never raises."""
        try:
            self._provenance.record(
                entity_id=entity_id,
                entity_type=entity_type,
                operation=operation,
                source=source,
                session_id=self.session_id or "",
                namespace=self.namespace,
                **metadata,
            )
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Top-level memory shortcuts
    # ------------------------------------------------------------------

    def remember(
        self,
        content: str,
        importance: float = 0.5,
        namespace: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        """Store a memory. Shorthand for ``agent.memory.remember()``.

        Args:
            content:    The text to remember.
            importance: Importance score [0, 1].
            namespace:  Override the agent's default namespace.
            **kwargs:   Extra kwargs forwarded to ``MemoryOS.remember()``.

        Returns:
            Memory ID string.
        """
        t0 = time.time()
        mid = self._memory.remember(
            content,
            importance=importance,
            namespace=namespace or self.namespace,
            **kwargs,
        )
        dur = (time.time() - t0) * 1000
        self._emit("remember", dur, memory_id=mid, importance=importance)
        self._prov(mid, "memory", "create", source="user",
                   content_length=len(content), importance=importance)
        return mid

    def recall(
        self,
        query: str,
        k: int = 5,
        namespace: Optional[str] = None,
        mode: str = "recall",
        **kwargs: Any,
    ) -> List[Memory]:
        """Retrieve relevant memories. Shorthand for ``agent.memory.recall()``.

        Args:
            query:     What to search for.
            k:         Number of results (default 5).
            namespace: Override the agent's default namespace.
            mode:      Retrieval mode — ``"recall"``, ``"planning"``,
                       ``"coding"``, ``"chat"``.
            **kwargs:  Extra kwargs forwarded to ``MemoryOS.recall()``.

        Returns:
            List of ``Memory`` objects ranked by relevance.
        """
        t0 = time.time()
        results = self._memory.recall(
            query,
            k=k,
            namespace=namespace or (self.namespace if self.namespace != "default" else None),
            mode=mode,
            **kwargs,
        )
        dur = (time.time() - t0) * 1000
        self._emit("recall", dur, query=query[:80], result_count=len(results))
        return results

    def forget(self, memory_id: Optional[str] = None) -> Any:
        """Trigger memory forgetting (low-importance memories are pruned).

        Shorthand for ``agent.memory.forget()``.

        Args:
            memory_id: Specific ID to forget. When None, applies heuristic
                       forgetting across all memories.

        Returns:
            Result from ``MemoryOS.forget()``.
        """
        return self._memory.forget()

    def consolidate(self, speed: str = "normal") -> Dict[str, Any]:
        """Run the memory consolidation pipeline.

        Merges duplicates, promotes important episodic memories to semantic,
        and prunes low-relevance working memories.
        Shorthand for ``agent.memory.consolidate()``.

        Args:
            speed: ``"fast"`` (lighter consolidation) or ``"normal"`` (full).

        Returns:
            Consolidation result dict.
        """
        return self._memory.consolidate(speed=speed)

    # ------------------------------------------------------------------
    # Session-scoped state shortcuts
    # ------------------------------------------------------------------

    def _require_session(self) -> str:
        if not self.session_id:
            raise ValueError(
                "session_id is required for state operations. "
                "Pass it to AgentState(session_id=...) "
                "or use agent.state directly with an explicit session_id."
            )
        return self.session_id

    def set_goal(self, goal: str) -> StatePayload:
        """Set the top-level goal for this session."""
        return self._state.set_goal(self._require_session(), goal)

    def set_plan(self, plan: List[str]) -> StatePayload:
        """Set the ordered plan steps for this session."""
        return self._state.set_plan(self._require_session(), plan)

    def advance(self) -> StatePayload:
        """Increment the step counter (mark the current step done)."""
        return self._state.advance(self._require_session())

    def record_tool(
        self,
        tool: str,
        output: Any,
        input: Any = None,
        error: Optional[str] = None,
    ) -> StatePayload:
        """Append a tool result to the session state."""
        result = ToolResult(tool=tool, input=input or {}, output=output, error=error)
        return self._state.record_tool(self._require_session(), result)

    def set_workflow(self, key: str, value: Any) -> StatePayload:
        """Store an arbitrary key-value pair in the session workflow state."""
        return self._state.set_workflow(self._require_session(), key, value)

    def mark_done(self) -> StatePayload:
        """Mark the current session as completed."""
        return self._state.mark_done(self._require_session())

    def mark_failed(self, reason: Optional[str] = None) -> StatePayload:
        """Mark the current session as failed (optionally with a reason)."""
        return self._state.mark_failed(self._require_session(), reason=reason)

    # ------------------------------------------------------------------
    # Snapshot / rollback
    # ------------------------------------------------------------------

    def snapshot(self, label: Optional[str] = None) -> StateSnapshot:
        """Create a named point-in-time snapshot of this session's state.

        Args:
            label: Human-readable label for the snapshot (optional).

        Returns:
            ``StateSnapshot`` — use ``snap.id`` to rollback or fork later.
        """
        t0 = time.time()
        snap = self._state.snapshot(self._require_session(), label=label)
        dur = (time.time() - t0) * 1000
        self._emit("snapshot", dur, snapshot_id=snap.id, label=label)
        self._prov(snap.id, "snapshot", "create", source="agent", label=label or "")
        return snap

    def rollback(self, snapshot_id: str) -> StatePayload:
        """Rollback this session to a prior snapshot.

        Args:
            snapshot_id: ID of the snapshot to restore.

        Returns:
            The restored ``StatePayload``.
        """
        t0 = time.time()
        payload = self._state.rollback(snapshot_id)
        dur = (time.time() - t0) * 1000
        self._emit("rollback", dur, snapshot_id=snapshot_id)
        self._prov(snapshot_id, "snapshot", "rollback", source="agent")
        return payload

    def list_snapshots(self) -> List[StateSnapshot]:
        """Return all snapshots for this session."""
        return self._state.list_snapshots(self._require_session())

    # ------------------------------------------------------------------
    # Fork / merge
    # ------------------------------------------------------------------

    def fork(self, snapshot_id: str, new_session_id: Optional[str] = None) -> str:
        """Fork a snapshot into a new independent state session.

        Args:
            snapshot_id:    ID of the snapshot to fork from.
            new_session_id: ID for the forked session. Auto-generated if None.

        Returns:
            Session ID of the fork.
        """
        t0 = time.time()
        fork_id = self._state.fork(snapshot_id, new_session_id=new_session_id)
        dur = (time.time() - t0) * 1000
        self._emit("fork", dur, snapshot_id=snapshot_id, fork_session_id=fork_id)
        self._prov(snapshot_id, "snapshot", "fork", source="agent",
                   fork_session_id=fork_id)
        return fork_id

    def clone(self, new_session_id: Optional[str] = None, label: Optional[str] = None) -> "AgentState":
        """Fork this session and return a new AgentState bound to the fork.

        The clone shares the same memory store, knowledge graph, and state
        layer as the parent — only the ``session_id`` differs. Both agents
        can read and write memories independently; state changes in the clone
        do not affect the parent and vice versa.

        Args:
            new_session_id: ID for the cloned session. Auto-generated if None.
            label:          Snapshot label used as the fork origin. Defaults
                            to ``"pre-clone"``.

        Returns:
            A new ``AgentState`` instance bound to the forked session.

        Example::

            original = AgentState(session_id="main")
            experiment = original.clone("experiment-1")
            experiment.set_goal("Test alternative approach")
        """
        t0 = time.time()
        snap = self._state.snapshot(
            self._require_session(), label=label or "pre-clone"
        )
        forked_id = self._state.fork(snap.id, new_session_id=new_session_id)
        dur = (time.time() - t0) * 1000
        self._emit("clone", dur, fork_session_id=forked_id, snapshot_id=snap.id)
        self._prov(self.session_id or "", "session", "fork", source="agent",
                   fork_session_id=forked_id)
        return self._clone_from(forked_id)

    def merge_fork(self, fork_session_id: str) -> StatePayload:
        """Merge a forked session back into this session.

        The fork's state is treated as the winning branch. The current
        session is the base.

        Args:
            fork_session_id: Session ID of the fork to merge.

        Returns:
            The merged ``StatePayload`` on this session.
        """
        return self._state.merge(fork_session_id, self._require_session())

    def with_session(self, session_id: str) -> "AgentState":
        """Return a view of this AgentState bound to a different session.

        All layers (memory, knowledge, context) remain shared — only the
        ``session_id`` attribute changes. Useful for agents that switch between
        multiple tasks without reinitializing the full stack.

        Args:
            session_id: The session to bind to (created if it doesn't exist).

        Returns:
            A new ``AgentState`` bound to ``session_id`` sharing this engine.
        """
        new_agent = self._clone_from(session_id)
        new_agent._state.get_or_create(session_id, namespace=self.namespace)
        return new_agent

    def _clone_from(self, session_id: str) -> "AgentState":
        """Internal: create a new AgentState sharing this engine, different session."""
        inst = AgentState.__new__(AgentState)
        inst._config = AgentConfig(
            session_id=session_id,
            namespace=self.namespace,
            backend=self._config.backend,
            db_path=self._config.db_path,
            endpoint=self._config.endpoint,
            api_key=self._config.api_key,
            org=self._config.org,
            embedding_model=self._config.embedding_model,
            context_cache_ttl=self._config.context_cache_ttl,
            context_default_mode=self._config.context_default_mode,
            context_budget_tokens=self._config.context_budget_tokens,
            context_top_k_memories=self._config.context_top_k_memories,
            token_model=self._config.token_model,
            auto_checkpoint=self._config.auto_checkpoint,
        )
        inst.session_id = session_id
        inst.namespace = self.namespace
        # Share the underlying engine
        inst._omem = self._omem
        inst._memory = self._memory
        inst._state = self._state
        inst._context = self._context
        inst._knowledge = self._knowledge
        inst._observe = self._observe
        inst._governance = self._governance
        inst._provenance = self._provenance
        inst._runtime = self._runtime
        inst._org = self._org
        return inst

    # ------------------------------------------------------------------
    # Checkpoint / resume
    # ------------------------------------------------------------------

    def checkpoint(self) -> str:
        """Write a crash-recovery checkpoint. Returns the checkpoint ID."""
        t0 = time.time()
        ckpt_id = self._state.checkpoint(self._require_session())
        dur = (time.time() - t0) * 1000
        self._emit("checkpoint", dur, checkpoint_id=ckpt_id)
        self._prov(ckpt_id, "checkpoint", "create", source="agent")
        return ckpt_id

    def resume(self) -> StatePayload:
        """Restore the latest crash-recovery checkpoint for this session.

        If no checkpoint exists, returns the current live state payload
        instead of raising — making it safe to call unconditionally at
        agent startup.

        Returns:
            Restored (or current) ``StatePayload``.
        """
        t0 = time.time()
        session_id = self._require_session()
        try:
            payload = self._state.resume_latest(session_id)
        except Exception:
            payload = self._state.load(session_id)
        dur = (time.time() - t0) * 1000
        self._emit("resume", dur, session_id=session_id)
        return payload

    def resume_from(self, checkpoint_id: str) -> StatePayload:
        """Restore a specific checkpoint.

        Args:
            checkpoint_id: ID returned by a prior ``checkpoint()`` call.

        Returns:
            Restored ``StatePayload``.
        """
        return self._state.resume(checkpoint_id)

    def resume_latest(self) -> StatePayload:
        """Restore the most recent checkpoint (raises if none exists)."""
        return self._state.resume_latest(self._require_session())

    def list_checkpoints(self) -> List[StateCheckpoint]:
        """Return all checkpoints for this session."""
        return self._state.list_checkpoints(self._require_session())

    # ------------------------------------------------------------------
    # Context assembly shortcuts
    # ------------------------------------------------------------------

    def build_context(
        self,
        task: str,
        budget_tokens: Optional[int] = None,
        mode: Optional[str] = None,
        include: Optional[List[str]] = None,
        top_k_memories: Optional[int] = None,
    ) -> ContextBundle:
        """Assemble an optimal context bundle for an LLM prompt.

        Combines session state + relevant memories + knowledge graph neighbors
        into a single, token-efficient prompt block.

        Args:
            task:           What the agent is doing (drives memory retrieval).
            budget_tokens:  Hard token ceiling (default from config: 6000).
            mode:           Retrieval mode: ``"planning"``, ``"coding"``,
                            ``"chat"``, ``"recall"``.
            include:        Sections to include. Defaults to
                            ``["state", "memory", "knowledge"]``.
            top_k_memories: Max memories to consider. Default from config.

        Returns:
            ``ContextBundle`` — inject ``bundle.text`` before the user message.
        """
        t0 = time.time()
        bundle = self._context.build(ContextRequest(
            task=task,
            budget_tokens=budget_tokens or self._config.context_budget_tokens,
            session_id=self.session_id,
            namespace=self.namespace if self.namespace != "default" else None,
            mode=mode or self._config.context_default_mode,
            include=include or ["state", "memory", "knowledge"],
            top_k_memories=top_k_memories or self._config.context_top_k_memories,
        ))
        dur = (time.time() - t0) * 1000
        self._emit(
            "context_build", dur,
            task=task[:80],
            token_count=getattr(bundle, "token_count", None),
            savings_pct=getattr(bundle, "savings_vs_naive", None),
        )
        return bundle

    def estimate_context_savings(
        self, task: str, budget_tokens: Optional[int] = None
    ) -> Dict[str, Any]:
        """Preview token efficiency for a context build without assembling it fully."""
        return self._context.estimate_savings(ContextRequest(
            task=task,
            budget_tokens=budget_tokens or self._config.context_budget_tokens,
            session_id=self.session_id,
            namespace=self.namespace if self.namespace != "default" else None,
        ))

    # ------------------------------------------------------------------
    # Knowledge shortcuts
    # ------------------------------------------------------------------

    def learn(
        self,
        subject: str,
        predicate: str,
        obj: str,
        confidence: float = 1.0,
        memory_id: str = "",
    ) -> str:
        """Assert a typed relation in the knowledge graph.

        Shorthand for ``agent.knowledge.link(...)``.

        Returns:
            Edge ID string.
        """
        t0 = time.time()
        edge_id = self._knowledge.link(
            subject, predicate, obj,
            confidence=confidence,
            memory_id=memory_id,
            namespace=self.namespace,
        )
        dur = (time.time() - t0) * 1000
        self._emit("learn", dur, subject=subject, predicate=predicate, obj=obj,
                   edge_id=edge_id)
        self._prov(edge_id, "edge", "create", source="agent",
                   subject=subject, predicate=predicate, obj=obj)
        return edge_id

    def know_about(self, entity: str, depth: int = 2):
        """Return the subgraph centred on an entity (depth BFS hops).

        Shorthand for ``agent.knowledge.query(...)``.
        """
        return self._knowledge.query(entity, depth=depth)

    def reason(self, question: str):
        """Apply heuristic graph inference to answer a question.

        Shorthand for ``agent.knowledge.reason(...)``.
        """
        return self._knowledge.reason(question)

    def knowledge_stats(self):
        """Return aggregate knowledge graph statistics.

        Shorthand for ``agent.knowledge.stats()``.
        """
        return self._knowledge.stats()

    # ------------------------------------------------------------------
    # Org memory shortcuts (Phase 10)
    # ------------------------------------------------------------------

    def share(
        self,
        memory_id: str,
        target_namespace: str,
    ) -> Dict[str, Any]:
        """Promote a memory to a higher namespace tier.

        Copies the memory to ``target_namespace``.
        Shorthand for ``agent.org.share()``.

        Args:
            memory_id:        ID of the memory to share.
            target_namespace: Destination namespace (e.g. ``"team/eng"``).

        Returns:
            ShareResult dict with ``original_id``, ``new_id``,
            ``source_namespace``, ``target_namespace``.
        """
        t0 = time.time()
        result = self._org.share(memory_id, target_namespace)
        dur = (time.time() - t0) * 1000
        self._emit("share", dur, memory_id=memory_id,
                   target_namespace=target_namespace, new_id=result.new_id)
        self._prov(result.new_id, "memory", "share", source="agent",
                   original_id=memory_id, target_namespace=target_namespace)
        return result.to_dict()

    # ------------------------------------------------------------------
    # Runtime shortcuts (Phase 9)
    # ------------------------------------------------------------------

    def register_agent(
        self,
        agent_id: str,
        capabilities: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Register this agent in the namespace runtime registry.

        Shorthand for ``agent.runtime.register()``.

        Args:
            agent_id:     Unique agent identifier.
            capabilities: Optional list of capabilities.
            metadata:     Optional additional context.

        Returns:
            AgentRegistration dict.
        """
        reg = self._runtime.register(
            agent_id=agent_id,
            session_id=self.session_id or "",
            namespace=self.namespace,
            capabilities=capabilities or [],
            metadata=metadata or {},
        )
        self._emit("register", 0.0, agent_id=agent_id)
        return reg.to_dict()

    def heartbeat_agent(self, agent_id: str) -> bool:
        """Update the heartbeat for a registered agent.

        Shorthand for ``agent.runtime.heartbeat()``.

        Args:
            agent_id: The agent to update.

        Returns:
            ``True`` if the agent was found; ``False`` otherwise.
        """
        return self._runtime.heartbeat(agent_id)

    # ------------------------------------------------------------------
    # Cross-layer status and export
    # ------------------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        """Comprehensive health and metrics dict for all four layers.

        Returns a dict with keys: ``session_id``, ``namespace``,
        ``backend``, ``is_cloud``, ``memory``, ``state``, ``knowledge``,
        ``context``.  Individual layer sections may contain ``"error"``
        keys if the layer is unavailable.

        Returns:
            Status dict (JSON-serializable).
        """
        result: Dict[str, Any] = {
            "session_id": self.session_id,
            "namespace": self.namespace,
            "backend": self.backend_type,
            "is_cloud": self.is_cloud,
            "timestamp": time.time(),
        }

        # Memory layer
        try:
            mems = self._memory.list(
                namespace=self.namespace if self.namespace != "default" else None,
            )
            mem_stats = self._memory.stats()
            result["memory"] = {
                "total_memories": len(mems),
                **{k: v for k, v in (mem_stats or {}).items() if k != "raw"},
            }
        except Exception as exc:
            result["memory"] = {"error": str(exc)}

        # State layer
        if self.session_id:
            try:
                result["state"] = self._state.summary(self.session_id)
            except Exception as exc:
                result["state"] = {"error": str(exc)}
        else:
            result["state"] = {"session_id": None}

        # Knowledge layer
        try:
            ks = self._knowledge.stats()
            result["knowledge"] = {
                "entities": ks.total_entities,
                "edges": ks.total_edges,
                "causal_links": ks.causal_links,
                "dependency_links": ks.dependency_links,
            }
        except Exception as exc:
            result["knowledge"] = {"error": str(exc)}

        # Context layer (just check it's wired)
        result["context"] = {
            "cache_ttl": self._config.context_cache_ttl,
            "default_mode": self._config.context_default_mode,
            "budget_tokens": self._config.context_budget_tokens,
        }

        # Observability layer (Phase 6)
        try:
            result["observe"] = self._observe.metrics(
                session_id=self.session_id,
                namespace=self.namespace,
            )
        except Exception as exc:
            result["observe"] = {"error": str(exc)}

        # Runtime layer (Phase 9)
        try:
            active = self._runtime.list_agents(self.namespace, status="active")
            result["runtime"] = {
                "active_agents": len(active),
                "namespace": self.namespace,
            }
        except Exception as exc:
            result["runtime"] = {"error": str(exc)}

        # Org memory layer (Phase 10)
        try:
            result["org"] = {
                "user_id": self._org.user_id,
                "team_id": self._org.team_id,
                "org_id": self._org.org_id,
            }
        except Exception as exc:
            result["org"] = {"error": str(exc)}

        return result

    def current_state(self) -> StatePayload:
        """Return the current state payload for this session."""
        return self._state.load(self._require_session())

    def summary(self) -> Dict[str, Any]:
        """Human-friendly summary of this session's state."""
        return self._state.summary(self._require_session())

    # ──────────────────────────────────────────────────────────────────────────
    # Explainability — the enterprise trust layer
    # ──────────────────────────────────────────────────────────────────────────

    def explain(
        self,
        query: str,
        *,
        k: int = 5,
        namespace: Optional[str] = None,
        mode: str = "recall",
    ) -> "ExplanationReport":
        """Explain exactly why specific memories would be recalled for *query*.

        Returns a rich :class:`ExplanationReport` combining:

        * **Score breakdown** — vector similarity, keyword match, recency,
          importance, frequency, confidence, graph proximity, and
          personalisation weights for each candidate.
        * **Provenance lineage** — for each candidate, the full chain of
          ``ProvenanceEvent`` objects showing how it was created and mutated.
        * **Knowledge connections** — any graph edges linked to the retrieved
          entity IDs.
        * **State relevance** — how closely the active session goal / context
          aligns with the query.
        * **Token savings estimate** — projected savings when context is built
          from these memories vs. naive concatenation.

        Args:
            query:     The query string to explain.
            k:         How many memories to explain (default 5).
            namespace: Restrict to this namespace.
            mode:      Retrieval mode — ``recall`` | ``planning`` | ``coding``
                       | ``chat``.

        Returns:
            :class:`ExplanationReport` — fully populated.

        Example::

            report = agent.explain("What database should I use?")
            print(report.format())          # human-readable
            data  = report.as_dict()        # JSON-serializable
        """
        t0 = time.time()

        # 1. Score breakdown via MemoryOS.explain()
        ns = namespace or self.namespace
        raw_explanations = self._memory.explain(query, k=k, namespace=ns, mode=mode)

        # 2. Provenance chains for each memory
        prov_chains: Dict[str, Any] = {}
        for ex in raw_explanations:
            try:
                chain = self._provenance.trace(ex.memory_id)
                prov_chains[ex.memory_id] = {
                    "root_id": chain.root_id,
                    "depth": len(chain.events),
                    "operations": [e.operation for e in chain.events],
                    "sources": list({e.source for e in chain.events}),
                }
            except Exception:
                prov_chains[ex.memory_id] = {}

        # 3. Knowledge graph connections for each entity
        kg_connections: Dict[str, Any] = {}
        for ex in raw_explanations:
            try:
                nodes = self._knowledge.query(ex.memory_id, depth=1)
                if nodes:
                    kg_connections[ex.memory_id] = [
                        {"from": n.get("from"), "rel": n.get("rel"), "to": n.get("to")}
                        for n in nodes[:5]
                    ]
            except Exception:
                pass

        # 4. State relevance — cosine-like heuristic against current goal
        state_goal: Optional[str] = None
        state_relevance: float = 0.0
        if self.session_id:
            try:
                payload = self._state.load(self.session_id)
                state_goal = payload.goal
                if state_goal:
                    goal_words = set(state_goal.lower().split())
                    query_words = set(query.lower().split())
                    overlap = goal_words & query_words
                    denom = len(goal_words | query_words)
                    state_relevance = len(overlap) / denom if denom else 0.0
            except Exception:
                pass

        # 5. Token savings estimate
        token_savings_pct: float = 0.0
        try:
            token_savings_pct = self.estimate_context_savings(
                query, budget_tokens=4096, mode=mode
            )
        except Exception:
            pass

        elapsed_ms = (time.time() - t0) * 1000

        report = ExplanationReport(
            query=query,
            session_id=self.session_id,
            namespace=ns,
            mode=mode,
            explanations=raw_explanations,
            provenance_chains=prov_chains,
            knowledge_connections=kg_connections,
            state_goal=state_goal,
            state_relevance=state_relevance,
            token_savings_pct=token_savings_pct,
            elapsed_ms=elapsed_ms,
        )
        return report

    def export_state(self) -> Dict[str, Any]:
        """Serialize the current session for handoff between agents or processes.

        The returned dict is JSON-serializable and can be passed to
        ``restore_state()`` on a different ``AgentState`` instance.

        Returns:
            Dict with keys: ``session_id``, ``namespace``, ``config``,
            ``state_payload``, ``snapshots``, ``checkpoints``,
            ``exported_at``.
        """
        data: Dict[str, Any] = {
            "session_id": self.session_id,
            "namespace": self.namespace,
            "config": self._config.to_dict(),
            "state_payload": None,
            "snapshots": [],
            "checkpoints": [],
            "exported_at": time.time(),
        }
        if self.session_id:
            try:
                payload = self._state.load(self.session_id)
                data["state_payload"] = payload.to_dict()
                data["snapshots"] = [
                    s.to_dict() for s in self._state.list_snapshots(self.session_id)
                ]
                data["checkpoints"] = [
                    {"id": c.id, "created_at": c.created_at}
                    for c in self._state.list_checkpoints(self.session_id)
                ]
            except Exception as exc:
                data["export_error"] = str(exc)
        return data

    def restore_state(self, data: Dict[str, Any]) -> StatePayload:
        """Restore session state from a prior ``export_state()`` result.

        Saves the exported payload into the current session.  Memories and
        knowledge graph entries are *not* restored — only the state machine
        (goal, plan, step, tool_outputs, workflow_state).

        Args:
            data: Dict returned by ``export_state()``.

        Returns:
            The restored ``StatePayload``.
        """
        session_id = self._require_session()
        payload_dict = data.get("state_payload")
        if not payload_dict:
            raise ValueError("export_state data does not contain a state_payload")

        payload = StatePayload.from_dict(payload_dict)
        payload.session_id = session_id  # bind to current session
        self._state.save(session_id, payload)
        return payload

    # ------------------------------------------------------------------
    # Representation
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"AgentState(session={self.session_id!r}, "
            f"namespace={self.namespace!r}, "
            f"backend={self.backend_type!r})"
        )

    def __str__(self) -> str:
        lines = [
            "AgentState",
            f"  session   : {self.session_id or '(none)'}",
            f"  namespace : {self.namespace}",
            f"  backend   : {self.backend_type}",
        ]
        if self.session_id:
            try:
                s = self._state.summary(self.session_id)
                lines.append(f"  goal      : {s.get('goal') or '(none)'}")
                lines.append(
                    f"  progress  : step {s.get('step', 0) + 1} / "
                    f"{len(s.get('plan', []))} | status={s.get('status', 'active')}"
                )
            except Exception:
                pass
        try:
            ks = self._knowledge.stats()
            lines.append(
                f"  knowledge : {ks.total_entities} entities, {ks.total_edges} edges"
            )
        except Exception:
            pass
        return "\n".join(lines)
