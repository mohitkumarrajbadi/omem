"""AgentState — top-level product facade (Phase 5 of the implementation plan).

``AgentState`` is the single object a developer imports. It composes all
six layers (memory, state, context, knowledge, observe, governance) and
auto-detects local vs cloud mode from environment variables.

Local mode (default)::

    from omem import AgentState
    agent = AgentState(session_id="my-agent")
    agent.memory.remember("User prefers Python")
    agent.state.set_goal("Refactor auth module")

Cloud mode (set env vars)::

    export OMEM_ENDPOINT=https://state.akamai.ai
    export OMEM_API_KEY=omem_sk_...
    export OMEM_ORG=acme-corp

    from omem import AgentState
    agent = AgentState(session_id="my-agent")
    # Same code, remote backend.

Implementation target: docs/roadmap/FULL_IMPLEMENTATION_PLAN.md Phase 5.
Cloud wiring:          docs/roadmap/FULL_IMPLEMENTATION_PLAN.md Cloud Phase C1.
"""

import os
from typing import Any, Optional

from .api import OMem
from .context.engine import ContextEngine
from .governance.layer import GovernanceOS
from .knowledge.layer import KnowledgeOS
from .memory.layer import MemoryOS
from .observe.events import ObserveOS
from .provenance.layer import ProvenanceOS
from .runtime.layer import RuntimeOS
from .state.layer import StateOS


class AgentState:
    """Unified agent state facade.

    ``AgentState`` is the product. It composes all v2 layers and exposes
    them as named properties. The underlying engine is ``OMem`` (local)
    or ``CloudBackend`` (when ``OMEM_ENDPOINT`` is set).

    Layers available today:
        .memory     — MemoryOS (remember, recall, consolidate, forget)

    Layers available after each phase:
        .state      — StateOS        (Phase 2 — snapshot, rollback, fork)
        .context    — ContextEngine  (Phase 3 — token-budget context)
        .knowledge  — KnowledgeOS    (Phase 4 — graph facade)
        .observe    — ObserveOS      (Phase 6 — traces, metrics, replay)
        .governance — GovernanceOS   (Phase 8 — retention, audit, RBAC)
        .provenance — ProvenanceOS   (Phase 7 — lineage, history)
        .runtime    — RuntimeOS      (Phase 9 — multi-agent coordination)

    All layers are instantiated eagerly so type checkers see the full surface.
    The stubs raise ``NotImplementedError`` until each phase is implemented.
    """

    def __init__(
        self,
        session_id: Optional[str] = None,
        endpoint: Optional[str] = None,
        api_key: Optional[str] = None,
        org: Optional[str] = None,
        namespace: str = "default",
        **omem_kwargs: Any,
    ) -> None:
        self.session_id = session_id
        self.namespace = namespace

        # Resolve cloud vs local mode
        _endpoint = endpoint or os.environ.get("OMEM_ENDPOINT")
        _api_key = api_key or os.environ.get("OMEM_API_KEY")
        _org = org or os.environ.get("OMEM_ORG")

        if _endpoint and _api_key:
            # Cloud Phase C1: swap in CloudBackend here.
            # For now, fall through to local mode with a warning.
            import warnings
            warnings.warn(
                "OMEM_ENDPOINT is set but CloudBackend is not yet implemented "
                "(Cloud Phase C1). Falling back to local SQLite mode.",
                stacklevel=2,
            )

        # Local mode — always available.
        _omem = OMem(**omem_kwargs)

        # Layer composition — always instantiate; stubs raise NotImplementedError
        # for unimplemented phases so the interface is always inspectable.
        self._memory = MemoryOS(_omem)
        self._state = StateOS()
        self._context = ContextEngine()
        self._knowledge = KnowledgeOS()
        self._observe = ObserveOS()
        self._governance = GovernanceOS()
        self._provenance = ProvenanceOS()
        self._runtime = RuntimeOS()

    # ------------------------------------------------------------------
    # Layer properties
    # ------------------------------------------------------------------

    @property
    def memory(self) -> MemoryOS:
        """Memory layer — fully implemented (v2 MemoryOS)."""
        return self._memory

    @property
    def state(self) -> StateOS:
        """State layer — Phase 2 (raises NotImplementedError until implemented)."""
        return self._state

    @property
    def context(self) -> ContextEngine:
        """Context engine — Phase 3."""
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
    # Convenience — delegate to state layer (Phase 2)
    # ------------------------------------------------------------------

    def snapshot(self, label: Optional[str] = None) -> Any:
        """Shortcut: snapshot the current session. Delegates to state.snapshot()."""
        if not self.session_id:
            raise ValueError("session_id is required to call snapshot()")
        return self.state.snapshot(self.session_id, label=label)

    def resume(self) -> Any:
        """Shortcut: resume from the latest checkpoint. Delegates to state."""
        if not self.session_id:
            raise ValueError("session_id is required to call resume()")
        return self.state.resume(self.session_id)

    def __repr__(self) -> str:
        mode = "cloud" if os.environ.get("OMEM_ENDPOINT") else "local"
        return (
            f"AgentState(session={self.session_id!r}, "
            f"namespace={self.namespace!r}, mode={mode!r})"
        )
