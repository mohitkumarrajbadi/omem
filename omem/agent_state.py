"""AgentState — top-level product facade.

``AgentState`` is the single object a developer imports. It composes the
memory and state layers (both production-ready as of Phase 2) and holds
typed stubs for future layers (context, knowledge, observe, governance).

Local mode (default)::

    from omem import AgentState
    agent = AgentState(session_id="my-agent")
    agent.memory.remember("User prefers Python")
    agent.state.set_goal("my-agent", "Refactor auth module")
    snap = agent.snapshot("before-oauth")
    branch = agent.fork(snap.id)
    chk = agent.checkpoint()
    agent.resume_from(chk)

Cloud mode (set env vars, Cloud Phase C1)::

    export OMEM_ENDPOINT=https://state.akamai.ai
    export OMEM_API_KEY=omem_sk_...

    from omem import AgentState
    agent = AgentState(session_id="my-agent")   # auto-detects cloud

Phase 5 note: this facade will grow as each layer ships. Until then,
layers beyond memory and state raise ``NotImplementedError``.
"""

import os
from typing import Any, List, Optional

from .api import OMem
from .context.engine import ContextBundle, ContextEngine, ContextRequest
from .governance.layer import GovernanceOS
from .knowledge.layer import KnowledgeOS
from .memory.layer import MemoryOS
from .observe.events import ObserveOS
from .provenance.layer import ProvenanceOS
from .runtime.layer import RuntimeOS
from .state.backend import InMemoryStateBackend, SQLiteStateBackend
from .state.layer import StateOS
from .types import StateCheckpoint, StatePayload, StateSnapshot, ToolResult


class AgentState:
    """Unified agent state facade.

    ``AgentState`` is the product object. It wires all shipped layers together
    so agents get a single coherent interface for all persistence needs.

    Shipped layers:
        .memory    — MemoryOS      (remember, recall, consolidate, forget)
        .state     — StateOS       (save, snapshot, rollback, fork, checkpoint)
        .context   — ContextEngine (build, estimate_savings)
        .knowledge — KnowledgeOS   (link, query, reason, entities, ingest)

    Future layers (stubs — raise NotImplementedError):
        .observe    — ObserveOS      (Phase 6)
        .provenance — ProvenanceOS   (Phase 7)
        .governance — GovernanceOS   (Phase 8)
        .runtime    — RuntimeOS      (Phase 9)
    """

    def __init__(
        self,
        session_id: Optional[str] = None,
        namespace: str = "default",
        backend: str = "sqlite",
        db_path: Optional[str] = None,
        endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
        org: Optional[str] = None,
        **omem_kwargs: Any,
    ) -> None:
        self.session_id = session_id
        self.namespace = namespace

        # Resolve cloud vs local mode
        _endpoint = endpoint or os.environ.get("OMEM_ENDPOINT")
        _api_key = api_key or os.environ.get("OMEM_API_KEY")

        if _endpoint and _api_key:
            import warnings
            warnings.warn(
                "OMEM_ENDPOINT is set but CloudBackend is not yet implemented "
                "(Cloud Phase C1). Falling back to local mode.",
                stacklevel=2,
            )

        # Resolve the db_path used for both memory and state backends
        _resolved_db = db_path
        if backend == "sqlite" and _resolved_db is None:
            _resolved_db = os.path.expanduser("~/.omem/brain.db")
            _db_dir = os.path.dirname(_resolved_db)
            if not os.path.exists(_db_dir):
                os.makedirs(_db_dir, exist_ok=True)

        # Memory layer — OMem with the resolved path
        _omem = OMem(backend=backend, db_path=db_path, **omem_kwargs)
        self._omem = _omem
        self._memory = MemoryOS(_omem)

        # State layer — same SQLite file, separate tables
        if backend == "memory":
            state_backend = InMemoryStateBackend()
        else:
            state_backend = SQLiteStateBackend(_resolved_db or ":memory:")
        self._state = StateOS(backend=state_backend)

        # Context layer — Phase 3 (fully wired)
        self._context = ContextEngine(
            memory=self._memory,
            state=self._state,
        )

        # Knowledge layer — Phase 4 (fully wired to the live engine graph)
        self._knowledge = KnowledgeOS(omem=_omem)
        self._observe = ObserveOS()
        self._governance = GovernanceOS()
        self._provenance = ProvenanceOS()
        self._runtime = RuntimeOS()

        # Bootstrap the session if session_id was given
        if self.session_id:
            self._state.get_or_create(self.session_id, namespace=namespace)

    # ------------------------------------------------------------------
    # Layer properties
    # ------------------------------------------------------------------

    @property
    def memory(self) -> MemoryOS:
        """Memory layer — fully implemented."""
        return self._memory

    @property
    def state(self) -> StateOS:
        """State layer — fully implemented (Phase 2)."""
        return self._state

    @property
    def context(self) -> ContextEngine:
        """Context engine — Phase 3 (raises NotImplementedError)."""
        return self._context

    @property
    def knowledge(self) -> KnowledgeOS:
        """Knowledge graph facade — Phase 4."""
        return self._knowledge

    @property
    def observe(self) -> ObserveOS:
        """Observability layer — Phase 6."""
        return self._observe

    @property
    def governance(self) -> GovernanceOS:
        """Governance layer — Phase 8."""
        return self._governance

    @property
    def provenance(self) -> ProvenanceOS:
        """Provenance layer — Phase 7."""
        return self._provenance

    @property
    def runtime(self) -> RuntimeOS:
        """Runtime coordination — Phase 9."""
        return self._runtime

    # ------------------------------------------------------------------
    # Convenience — session-scoped shortcuts for common state operations
    # ------------------------------------------------------------------

    def _require_session(self) -> str:
        if not self.session_id:
            raise ValueError(
                "session_id is required. Pass it to AgentState(session_id=...) "
                "or use agent.state directly with an explicit session_id."
            )
        return self.session_id

    def set_goal(self, goal: str) -> StatePayload:
        """Set the top-level goal for this session."""
        return self.state.set_goal(self._require_session(), goal)

    def set_plan(self, plan: List[str]) -> StatePayload:
        """Replace the plan steps for this session."""
        return self.state.set_plan(self._require_session(), plan)

    def advance(self) -> StatePayload:
        """Increment the step counter for this session."""
        return self.state.advance(self._require_session())

    def record_tool(self, tool: str, output: Any, input: Any = None, error: Optional[str] = None) -> StatePayload:
        """Append a tool result to this session's state."""
        result = ToolResult(
            tool=tool,
            input=input or {},
            output=output,
            error=error,
        )
        return self.state.record_tool(self._require_session(), result)

    def snapshot(self, label: Optional[str] = None) -> StateSnapshot:
        """Create a named snapshot of this session's current state."""
        return self.state.snapshot(self._require_session(), label=label)

    def rollback(self, snapshot_id: str) -> StatePayload:
        """Rollback this session to a prior snapshot."""
        return self.state.rollback(snapshot_id)

    def fork(self, snapshot_id: str, new_session_id: Optional[str] = None) -> str:
        """Fork from a snapshot into a new independent session."""
        return self.state.fork(snapshot_id, new_session_id=new_session_id)

    def checkpoint(self) -> str:
        """Write a crash-recovery checkpoint. Returns the checkpoint ID."""
        return self.state.checkpoint(self._require_session())

    def resume_from(self, checkpoint_id: str) -> StatePayload:
        """Restore this session from a specific checkpoint."""
        return self.state.resume(checkpoint_id)

    def resume_latest(self) -> StatePayload:
        """Restore this session from the most recent checkpoint."""
        return self.state.resume_latest(self._require_session())

    def build_context(
        self,
        task: str,
        budget_tokens: int = 6000,
        mode: str = "planning",
        include: Optional[List[str]] = None,
        top_k_memories: int = 15,
    ) -> ContextBundle:
        """Assemble an optimal LLM context bundle for this session.

        Combines the current session state, most relevant memories, and
        knowledge graph neighbors into a single prompt block.

        Args:
            task:          What the agent is doing right now.
            budget_tokens: Hard token ceiling (default 6000).
            mode:          Retrieval mode: ``"planning"``, ``"coding"``,
                           ``"chat"``, ``"recall"``.
            include:       Sections to include. Defaults to
                           ``["state", "memory", "knowledge"]``.
            top_k_memories: Max number of memories to consider.

        Returns:
            ``ContextBundle`` — inject ``ctx.text`` before your LLM prompt.
        """
        return self.context.build(ContextRequest(
            task=task,
            budget_tokens=budget_tokens,
            session_id=self.session_id,
            namespace=self.namespace if self.namespace != "default" else None,
            mode=mode,
            include=include or ["state", "memory", "knowledge"],
            top_k_memories=top_k_memories,
        ))

    def estimate_context_savings(self, task: str, budget_tokens: int = 6000) -> dict:
        """Preview how many tokens the context engine will save for a given task."""
        return self.context.estimate_savings(ContextRequest(
            task=task,
            budget_tokens=budget_tokens,
            session_id=self.session_id,
            namespace=self.namespace if self.namespace != "default" else None,
        ))

    # ------------------------------------------------------------------
    # Convenience — session-scoped shortcuts for knowledge operations
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
        return self.knowledge.link(
            subject, predicate, obj,
            confidence=confidence,
            memory_id=memory_id,
            namespace=self.namespace,
        )

    def know_about(self, entity: str, depth: int = 2):
        """Return the subgraph centred on an entity.

        Shorthand for ``agent.knowledge.query(...)``.

        Returns:
            ``GraphSubgraph``
        """
        return self.knowledge.query(entity, depth=depth, namespace=self.namespace)

    def reason(self, question: str):
        """Apply heuristic graph inference to answer a question.

        Shorthand for ``agent.knowledge.reason(...)``.

        Returns:
            List of ``InferenceResult`` sorted by confidence.
        """
        return self.knowledge.reason(question, namespace=self.namespace)

    def knowledge_stats(self):
        """Return aggregate knowledge graph statistics.

        Shorthand for ``agent.knowledge.stats()``.

        Returns:
            ``KnowledgeStats``
        """
        return self.knowledge.stats()

    def current_state(self) -> StatePayload:
        """Return the current state payload for this session."""
        return self.state.load(self._require_session())

    def summary(self) -> dict:
        """Return a human-friendly summary of this session."""
        return self.state.summary(self._require_session())

    def __repr__(self) -> str:
        mode = "cloud" if os.environ.get("OMEM_ENDPOINT") else "local"
        return (
            f"AgentState(session={self.session_id!r}, "
            f"namespace={self.namespace!r}, mode={mode!r})"
        )
