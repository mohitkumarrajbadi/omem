"""Import compatibility tests — Phase 1 of the v2 implementation plan.

Ensures that:
  1. All stable v1 imports still work.
  2. V2 memory layer (MemoryOS, MemoryQuery) imports correctly.
  3. All v2 package scaffolds (state, context, knowledge, ...) are importable.
  4. AgentState top-level facade is importable.
  5. No import from the new packages breaks the test suite.

These tests must stay green throughout the v2 transition.
"""

import importlib


# ---------------------------------------------------------------------------
# V1 stable API
# ---------------------------------------------------------------------------

def test_omem_importable():
    from omem import OMem  # noqa: F401
    assert OMem is not None


def test_core_types_importable():
    from omem import (  # noqa: F401
        DreamResult,
        Evidence,
        ForgetResult,
        GraphNode,
        Memory,
        MemoryLevel,
        MemoryPriority,
        MemoryStatus,
        MemoryTier,
        MemoryType,
        Provenance,
        RelationEdge,
        RetrievalExplanation,
    )


def test_version_string():
    from omem import __version__
    assert isinstance(__version__, str)
    assert len(__version__) > 0


# ---------------------------------------------------------------------------
# V2 memory layer (shipped)
# ---------------------------------------------------------------------------

def test_memory_os_importable():
    from omem import MemoryOS, MemoryQuery  # noqa: F401
    assert MemoryOS is not None
    assert MemoryQuery is not None


def test_memory_os_package_importable():
    import omem.memory
    assert hasattr(omem.memory, "MemoryOS")
    assert hasattr(omem.memory, "MemoryQuery")


def test_memory_os_instantiates():
    from omem.memory import MemoryOS
    m = MemoryOS()
    assert m is not None


# ---------------------------------------------------------------------------
# V2 package scaffolds (stubs — importable but NotImplementedError for unbuilt)
# ---------------------------------------------------------------------------

def test_state_package_importable():
    import omem.state
    from omem.state import StateOS  # noqa: F401
    assert StateOS is not None


def test_state_data_types_importable():
    from omem.state.layer import (  # noqa: F401
        StateCheckpoint,
        StatePayload,
        StateSnapshot,
        ToolResult,
    )


def test_context_package_importable():
    import omem.context
    from omem.context import ContextBundle, ContextEngine, ContextRequest  # noqa: F401
    assert ContextEngine is not None


def test_knowledge_package_importable():
    import omem.knowledge
    from omem.knowledge import KnowledgeOS  # noqa: F401
    assert KnowledgeOS is not None


def test_observe_package_importable():
    import omem.observe
    from omem.observe import ObserveOS, TraceEvent  # noqa: F401
    assert ObserveOS is not None


def test_governance_package_importable():
    import omem.governance
    from omem.governance import GovernanceOS  # noqa: F401
    assert GovernanceOS is not None


def test_provenance_package_importable():
    import omem.provenance
    from omem.provenance import ProvenanceOS  # noqa: F401
    assert ProvenanceOS is not None


def test_runtime_package_importable():
    import omem.runtime
    from omem.runtime import RuntimeOS  # noqa: F401
    assert RuntimeOS is not None


def test_cloud_package_importable():
    import omem.cloud
    from omem.cloud.client import OMemCloudClient  # noqa: F401
    assert OMemCloudClient is not None


# ---------------------------------------------------------------------------
# AgentState top-level facade
# ---------------------------------------------------------------------------

def test_agent_state_importable():
    from omem import AgentState  # noqa: F401
    assert AgentState is not None


def test_agent_state_instantiates():
    from omem import AgentState
    agent = AgentState(session_id="test-compat")
    assert agent is not None
    assert agent.session_id == "test-compat"


def test_agent_state_memory_layer_works():
    """Memory is the only fully implemented layer — verify it works."""
    from omem import AgentState
    agent = AgentState()
    mem_id = agent.memory.remember("import compat test memory")
    assert isinstance(mem_id, str)
    assert len(mem_id) > 0


def test_agent_state_unimplemented_layers_raise():
    """Unbuilt phases raise NotImplementedError — not AttributeError or ImportError."""
    import pytest
    from omem import AgentState
    agent = AgentState(session_id="test-stub")

    with pytest.raises(NotImplementedError):
        agent.state.load("test-session")

    with pytest.raises(NotImplementedError):
        agent.context.build(None)  # type: ignore

    with pytest.raises(NotImplementedError):
        agent.knowledge.entities()


# ---------------------------------------------------------------------------
# All declared __all__ entries resolve
# ---------------------------------------------------------------------------

def test_top_level_all_resolvable():
    import omem
    for name in omem.__all__:
        assert hasattr(omem, name), f"omem.__all__ contains {name!r} but it is not importable"
