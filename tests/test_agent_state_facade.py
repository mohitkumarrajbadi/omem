"""Unit tests for Phase 5 — AgentState unified facade and AgentConfig.

All tests use the ``"memory"`` backend so no filesystem I/O is required.

Test scope:
    AgentConfig
        - defaults, validation, from_env, from_dict, to_dict, is_cloud,
          resolved_db_path, repr
    AgentState construction
        - explicit kwargs, AgentConfig injection, ephemeral(), from_config(),
          from_env(), cloud detection (warning)
    Layer properties
        - memory, state, context, knowledge accessible; stubs raise NotImplementedError
    Properties
        - is_cloud, backend_type, db_path, config, session_id, namespace
    Context manager
        - __enter__ / __exit__ with checkpoint (clean exit) and exception pass-through
    Memory shortcuts
        - remember(), recall(), forget(), consolidate()
    State shortcuts
        - set_goal, set_plan, advance, record_tool, set_workflow,
          mark_done, mark_failed, _require_session raises without session_id
    Snapshot / rollback
        - snapshot(), rollback(), list_snapshots()
    Checkpoint / resume
        - checkpoint(), resume(), resume_from(), resume_latest(),
          resume() fallback when no checkpoint exists
    Fork / merge / clone
        - fork(), clone(), clone shares engine, clone has independent session,
          with_session(), merge_fork()
    Context shortcuts
        - build_context(), estimate_context_savings()
    Knowledge shortcuts
        - learn(), know_about(), reason(), knowledge_stats()
    Status / export / restore
        - status() structure, export_state() / restore_state() roundtrip
    Representation
        - __repr__, __str__

Run:
    pytest tests/test_agent_state_facade.py -v
"""

import json
import warnings

import pytest

from omem import AgentConfig, AgentState

# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def agent():
    """Ephemeral AgentState with a session."""
    return AgentState(session_id="test-session", backend="memory")


@pytest.fixture
def sessionless():
    """Ephemeral AgentState without a session."""
    return AgentState(backend="memory")


# ──────────────────────────────────────────────────────────────────────────────
# 1. AgentConfig — defaults and validation
# ──────────────────────────────────────────────────────────────────────────────


class TestAgentConfig:
    def test_defaults(self):
        cfg = AgentConfig()
        assert cfg.session_id is None
        assert cfg.namespace == "default"
        assert cfg.backend == "sqlite"
        assert cfg.context_budget_tokens == 6000
        assert cfg.auto_checkpoint is True

    def test_invalid_backend_raises(self):
        with pytest.raises(ValueError, match="backend"):
            AgentConfig(backend="redis")

    def test_postgres_backend_requires_dsn(self):
        with pytest.raises(ValueError, match="requires db_path"):
            AgentConfig(backend="postgres")

    def test_postgres_backend_accepts_dsn(self):
        cfg = AgentConfig(
            backend="postgres",
            db_path="postgresql://omem:omem@localhost:5432/omem",
        )
        assert cfg.resolved_db_path == "postgresql://omem:omem@localhost:5432/omem"

    def test_budget_below_100_raises(self):
        with pytest.raises(ValueError):
            AgentConfig(context_budget_tokens=50)

    def test_is_cloud_false_without_endpoint(self):
        assert AgentConfig().is_cloud is False

    def test_is_cloud_true_with_both(self):
        cfg = AgentConfig(endpoint="https://state.akamai.ai", api_key="sk-test")
        assert cfg.is_cloud is True

    def test_is_cloud_true_with_endpoint_only(self):
        cfg = AgentConfig(endpoint="https://state.akamai.ai")
        assert cfg.is_cloud is True

    def test_resolved_db_path_sqlite_default(self):
        cfg = AgentConfig(backend="sqlite")
        assert cfg.resolved_db_path is not None
        assert "brain.db" in cfg.resolved_db_path

    def test_resolved_db_path_memory_is_none(self):
        cfg = AgentConfig(backend="memory")
        assert cfg.resolved_db_path is None

    def test_resolved_db_path_explicit(self):
        cfg = AgentConfig(backend="sqlite", db_path="/tmp/test.db")
        assert cfg.resolved_db_path == "/tmp/test.db"

    def test_to_dict_excludes_api_key(self):
        cfg = AgentConfig(api_key="secret-key")
        d = cfg.to_dict()
        assert "api_key" not in d

    def test_to_dict_roundtrip_via_from_dict(self):
        cfg = AgentConfig(session_id="abc", namespace="ns1", backend="memory",
                          context_budget_tokens=4000)
        d = cfg.to_dict()
        cfg2 = AgentConfig.from_dict(d)
        assert cfg2.session_id == "abc"
        assert cfg2.namespace == "ns1"
        assert cfg2.context_budget_tokens == 4000

    def test_from_env_reads_env_vars(self, monkeypatch):
        monkeypatch.setenv("OMEM_SESSION_ID", "env-session")
        monkeypatch.setenv("OMEM_NAMESPACE", "env-ns")
        monkeypatch.setenv("OMEM_BACKEND", "memory")
        cfg = AgentConfig.from_env()
        assert cfg.session_id == "env-session"
        assert cfg.namespace == "env-ns"
        assert cfg.backend == "memory"

    def test_from_env_defaults_when_vars_absent(self, monkeypatch):
        # Make sure vars are not set
        for var in ("OMEM_SESSION_ID", "OMEM_NAMESPACE", "OMEM_BACKEND"):
            monkeypatch.delenv(var, raising=False)
        cfg = AgentConfig.from_env()
        assert cfg.namespace == "default"
        assert cfg.backend == "sqlite"

    def test_repr_contains_key_info(self):
        cfg = AgentConfig(session_id="s1", namespace="ns", backend="memory")
        r = repr(cfg)
        assert "s1" in r
        assert "memory" in r


# ──────────────────────────────────────────────────────────────────────────────
# 2. AgentState construction
# ──────────────────────────────────────────────────────────────────────────────


class TestConstruction:
    def test_defaults(self):
        a = AgentState(backend="memory")
        assert a.session_id is None
        assert a.namespace == "default"

    def test_with_session_id(self, agent):
        assert agent.session_id == "test-session"

    def test_from_config(self):
        cfg = AgentConfig(session_id="cfg-session", backend="memory")
        a = AgentState.from_config(cfg)
        assert a.session_id == "cfg-session"

    def test_config_kwarg_overrides_individual(self):
        cfg = AgentConfig(session_id="from-config", backend="memory")
        a = AgentState(session_id="ignored", config=cfg)
        assert a.session_id == "from-config"

    def test_ephemeral_factory(self):
        a = AgentState.ephemeral(session_id="eph")
        assert a.backend_type == "local:memory"
        assert a.session_id == "eph"

    def test_from_env_factory(self, monkeypatch):
        monkeypatch.setenv("OMEM_SESSION_ID", "env-agent")
        monkeypatch.setenv("OMEM_BACKEND", "memory")
        a = AgentState.from_env()
        assert a.session_id == "env-agent"

    def test_cloud_routes_to_remote_when_endpoint_set(self, monkeypatch):
        from omem.cloud.remote import RemoteAgentState

        monkeypatch.setenv("OMEM_ENDPOINT", "https://state.akamai.ai")
        monkeypatch.delenv("OMEM_API_KEY", raising=False)
        agent = AgentState(backend="memory")
        assert isinstance(agent, RemoteAgentState)
        agent.close()

    def test_stores_config(self, agent):
        assert isinstance(agent.config, AgentConfig)
        assert agent.config.session_id == "test-session"


# ──────────────────────────────────────────────────────────────────────────────
# 3. Layer properties
# ──────────────────────────────────────────────────────────────────────────────


class TestLayerProperties:
    def test_memory_accessible(self, agent):
        from omem.memory.layer import MemoryOS
        assert isinstance(agent.memory, MemoryOS)

    def test_state_accessible(self, agent):
        from omem.state.layer import StateOS
        assert isinstance(agent.state, StateOS)

    def test_context_accessible(self, agent):
        from omem.context.engine import ContextEngine
        assert isinstance(agent.context, ContextEngine)

    def test_knowledge_accessible(self, agent):
        from omem.knowledge.layer import KnowledgeOS
        assert isinstance(agent.knowledge, KnowledgeOS)

    def test_observe_accessible(self, agent):
        """Phase 6: ObserveOS is now fully implemented."""
        from omem.observe.events import ObserveOS
        assert isinstance(agent.observe, ObserveOS)
        # metrics() should return a dict (no longer raises)
        m = agent.observe.metrics()
        assert isinstance(m, dict)

    def test_governance_accessible(self, agent):
        """Phase 8: GovernanceOS is now fully implemented."""
        from omem.governance.layer import GovernanceOS
        assert isinstance(agent.governance, GovernanceOS)
        # audit() should return a list (no longer raises)
        entries = agent.governance.audit()
        assert isinstance(entries, list)

    def test_runtime_accessible(self, agent):
        """Phase 9: RuntimeOS is now fully implemented."""
        from omem.runtime.layer import RuntimeOS
        assert isinstance(agent.runtime, RuntimeOS)
        # list_agents() should return a list (no longer raises)
        agents = agent.runtime.list_agents("default")
        assert isinstance(agents, list)

    def test_org_accessible(self, agent):
        """Phase 10: OrgMemoryOS is now fully implemented."""
        from omem.memory.org.layer import OrgMemoryOS
        assert isinstance(agent.org, OrgMemoryOS)


# ──────────────────────────────────────────────────────────────────────────────
# 4. Derived properties
# ──────────────────────────────────────────────────────────────────────────────


class TestDerivedProperties:
    def test_is_cloud_false(self, agent):
        assert agent.is_cloud is False

    def test_backend_type_memory(self, agent):
        assert agent.backend_type == "local:memory"

    def test_db_path_memory_is_none(self, agent):
        assert agent.db_path is None

    def test_ping_returns_true(self, agent):
        assert agent.ping() is True


# ──────────────────────────────────────────────────────────────────────────────
# 5. Context manager
# ──────────────────────────────────────────────────────────────────────────────


class TestContextManager:
    def test_enter_returns_self(self, agent):
        with agent as a:
            assert a is agent

    def test_exit_writes_checkpoint_on_clean_exit(self):
        a = AgentState(session_id="cm-session", backend="memory")
        with a:
            pass  # clean exit
        # Verify a checkpoint was written
        checkpoints = a.list_checkpoints()
        assert len(checkpoints) >= 1

    def test_exit_does_not_suppress_exceptions(self):
        a = AgentState(session_id="cm-exc", backend="memory")
        with pytest.raises(ValueError, match="test-error"):
            with a:
                raise ValueError("test-error")

    def test_exit_no_checkpoint_when_auto_checkpoint_false(self):
        cfg = AgentConfig(session_id="no-chk", backend="memory", auto_checkpoint=False)
        a = AgentState(config=cfg)
        with a:
            pass
        checkpoints = a.list_checkpoints()
        assert len(checkpoints) == 0

    def test_exit_without_session_is_safe(self):
        a = AgentState(backend="memory")
        with a:
            pass  # no session, should not raise


# ──────────────────────────────────────────────────────────────────────────────
# 6. Memory shortcuts
# ──────────────────────────────────────────────────────────────────────────────


class TestMemoryShortcuts:
    def test_remember_returns_string_id(self, agent):
        mid = agent.remember("test content")
        assert isinstance(mid, str)
        assert len(mid) > 0

    def test_recall_returns_list(self, agent):
        agent.remember("Python is a great language for AI")
        results = agent.recall("Python AI")
        assert isinstance(results, list)

    def test_recall_k_respected(self, agent):
        for i in range(10):
            agent.remember(f"Memory item number {i} about Python")
        results = agent.recall("Python", k=3)
        assert len(results) <= 3

    def test_forget_runs_without_error(self, agent):
        agent.remember("temporary fact")
        agent.forget()  # should not raise

    def test_consolidate_returns_dict(self, agent):
        agent.remember("fact one about Python")
        agent.remember("fact two about Python")
        result = agent.consolidate(speed="fast")
        assert isinstance(result, dict)


# ──────────────────────────────────────────────────────────────────────────────
# 7. State shortcuts
# ──────────────────────────────────────────────────────────────────────────────


class TestStateShortcuts:
    def test_require_session_raises_without_session(self, sessionless):
        with pytest.raises(ValueError, match="session_id"):
            sessionless.set_goal("test")

    def test_set_goal(self, agent):
        payload = agent.set_goal("Build a web API")
        assert payload.goal == "Build a web API"

    def test_set_plan(self, agent):
        payload = agent.set_plan(["step1", "step2", "step3"])
        assert len(payload.plan) == 3

    def test_advance(self, agent):
        agent.set_plan(["step1", "step2"])
        p1 = agent.current_state()
        agent.advance()
        p2 = agent.current_state()
        assert p2.step == p1.step + 1

    def test_record_tool(self, agent):
        payload = agent.record_tool("search", {"results": [1, 2, 3]})
        assert len(payload.tool_outputs) >= 1
        assert payload.tool_outputs[-1].tool == "search"

    def test_set_workflow(self, agent):
        payload = agent.set_workflow("auth_token", "abc-123")
        assert payload.workflow_state.get("auth_token") == "abc-123"

    def test_mark_done(self, agent):
        payload = agent.mark_done()
        assert payload.status == "done"

    def test_mark_failed(self, agent):
        payload = agent.mark_failed("timeout")
        assert payload.status == "failed"

    def test_current_state(self, agent):
        payload = agent.current_state()
        assert payload.session_id == "test-session"

    def test_summary_returns_dict(self, agent):
        s = agent.summary()
        assert isinstance(s, dict)
        assert "session_id" in s


# ──────────────────────────────────────────────────────────────────────────────
# 8. Snapshot / rollback
# ──────────────────────────────────────────────────────────────────────────────


class TestSnapshotRollback:
    def test_snapshot_returns_snapshot(self, agent):
        from omem.types import StateSnapshot
        snap = agent.snapshot(label="test-snap")
        assert isinstance(snap, StateSnapshot)
        assert snap.label == "test-snap"

    def test_rollback_restores_state(self, agent):
        agent.set_goal("original goal")
        snap = agent.snapshot()
        agent.set_goal("different goal")
        payload = agent.rollback(snap.id)
        assert payload.goal == "original goal"

    def test_list_snapshots_grows(self, agent):
        agent.snapshot("snap-1")
        agent.snapshot("snap-2")
        snaps = agent.list_snapshots()
        assert len(snaps) >= 2


# ──────────────────────────────────────────────────────────────────────────────
# 9. Checkpoint / resume
# ──────────────────────────────────────────────────────────────────────────────


class TestCheckpointResume:
    def test_checkpoint_returns_id(self, agent):
        chk_id = agent.checkpoint()
        assert isinstance(chk_id, str)
        assert len(chk_id) > 0

    def test_resume_returns_payload(self, agent):
        agent.set_goal("original goal")
        agent.checkpoint()
        agent.set_goal("changed goal")
        payload = agent.resume()
        assert payload.goal == "original goal"

    def test_resume_without_checkpoint_returns_current(self, agent):
        agent.set_goal("no-checkpoint goal")
        payload = agent.resume()
        assert payload.session_id == "test-session"

    def test_resume_from_specific_checkpoint(self, agent):
        agent.set_goal("goal-A")
        chk1 = agent.checkpoint()
        agent.set_goal("goal-B")
        agent.checkpoint()
        payload = agent.resume_from(chk1)
        assert payload.goal == "goal-A"

    def test_list_checkpoints_returns_list(self, agent):
        agent.checkpoint()
        chks = agent.list_checkpoints()
        assert isinstance(chks, list)
        assert len(chks) >= 1


# ──────────────────────────────────────────────────────────────────────────────
# 10. Fork / clone / with_session
# ──────────────────────────────────────────────────────────────────────────────


class TestForkClone:
    def test_fork_returns_new_session_id(self, agent):
        agent.set_goal("base goal")
        snap = agent.snapshot()
        fork_id = agent.fork(snap.id)
        assert isinstance(fork_id, str)
        assert fork_id != agent.session_id

    def test_clone_returns_new_agent(self, agent):
        agent.set_goal("original")
        clone = agent.clone()
        assert isinstance(clone, AgentState)
        assert clone.session_id != agent.session_id

    def test_clone_shares_memory_layer(self, agent):
        clone = agent.clone()
        assert clone._memory is agent._memory

    def test_clone_shares_knowledge_layer(self, agent):
        clone = agent.clone()
        assert clone._knowledge is agent._knowledge

    def test_clone_shares_state_layer(self, agent):
        clone = agent.clone()
        assert clone._state is agent._state

    def test_clone_independent_session(self, agent):
        agent.set_goal("parent goal")
        clone = agent.clone()
        clone.set_goal("clone goal")
        # Parent's goal should be unchanged
        assert agent.current_state().goal == "parent goal"
        assert clone.current_state().goal == "clone goal"

    def test_clone_with_explicit_session_id(self, agent):
        clone = agent.clone(new_session_id="my-clone")
        assert clone.session_id == "my-clone"

    def test_with_session_returns_new_agent(self, agent):
        other = agent.with_session("other-session")
        assert other.session_id == "other-session"
        assert other._memory is agent._memory

    def test_with_session_different_session_id(self, agent):
        other = agent.with_session("different")
        assert other.session_id != agent.session_id

    def test_merge_fork(self, agent):
        agent.set_goal("parent goal")
        snap = agent.snapshot()
        fork_id = agent.fork(snap.id, new_session_id="merge-fork-test")
        # Advance the fork
        forked = agent.with_session(fork_id)
        forked.set_goal("fork goal")
        # Merge back — returns the winning (fork) payload
        merged = agent.merge_fork(fork_id)
        # Merge resolves to the winning branch's payload
        assert merged is not None
        assert merged.session_id in (agent.session_id, fork_id)


# ──────────────────────────────────────────────────────────────────────────────
# 11. Context shortcuts
# ──────────────────────────────────────────────────────────────────────────────


class TestContextShortcuts:
    def test_build_context_returns_bundle(self, agent):
        from omem.context.engine import ContextBundle
        bundle = agent.build_context("test task")
        assert isinstance(bundle, ContextBundle)
        assert bundle.token_count >= 0

    def test_build_context_respects_budget(self, agent):
        bundle = agent.build_context("test task", budget_tokens=500)
        assert bundle.budget_tokens == 500

    def test_estimate_context_savings_returns_dict(self, agent):
        result = agent.estimate_context_savings("some task")
        assert isinstance(result, dict)
        assert "savings_pct" in result


# ──────────────────────────────────────────────────────────────────────────────
# 12. Knowledge shortcuts
# ──────────────────────────────────────────────────────────────────────────────


class TestKnowledgeShortcuts:
    def test_learn_returns_edge_id(self, agent):
        edge_id = agent.learn("FastAPI", "uses", "Pydantic")
        assert isinstance(edge_id, str)

    def test_know_about_returns_subgraph(self, agent):
        agent.learn("Python", "uses", "CPython")
        from omem.knowledge.types import GraphSubgraph
        sg = agent.know_about("Python")
        assert isinstance(sg, GraphSubgraph)

    def test_reason_returns_list(self, agent):
        agent.learn("FastAPI", "uses", "Starlette")
        results = agent.reason("FastAPI Starlette")
        assert isinstance(results, list)

    def test_knowledge_stats_returns_stats(self, agent):
        agent.learn("A", "related_to", "B")
        from omem.knowledge.types import KnowledgeStats
        stats = agent.knowledge_stats()
        assert isinstance(stats, KnowledgeStats)
        assert stats.total_entities >= 2


# ──────────────────────────────────────────────────────────────────────────────
# 13. Status
# ──────────────────────────────────────────────────────────────────────────────


class TestStatus:
    def test_status_returns_dict(self, agent):
        s = agent.status()
        assert isinstance(s, dict)

    def test_status_has_required_keys(self, agent):
        s = agent.status()
        for key in ("session_id", "namespace", "backend", "is_cloud",
                    "memory", "state", "knowledge", "context"):
            assert key in s, f"missing key: {key}"

    def test_status_memory_has_total(self, agent):
        agent.remember("something")
        s = agent.status()
        assert "total_memories" in s["memory"] or "error" in s["memory"]

    def test_status_state_has_goal(self, agent):
        agent.set_goal("Test goal")
        s = agent.status()
        if "error" not in s.get("state", {}):
            assert "goal" in s["state"]

    def test_status_knowledge_has_entities(self, agent):
        agent.learn("X", "uses", "Y")
        s = agent.status()
        if "error" not in s.get("knowledge", {}):
            assert "entities" in s["knowledge"]

    def test_status_is_json_serializable(self, agent):
        s = agent.status()
        json.dumps(s, default=str)  # should not raise

    def test_ping(self, agent):
        assert agent.ping() is True


# ──────────────────────────────────────────────────────────────────────────────
# 14. Export / restore
# ──────────────────────────────────────────────────────────────────────────────


class TestExportRestore:
    def test_export_state_returns_dict(self, agent):
        data = agent.export_state()
        assert isinstance(data, dict)

    def test_export_has_required_keys(self, agent):
        data = agent.export_state()
        for key in ("session_id", "namespace", "config", "state_payload",
                    "snapshots", "checkpoints", "exported_at"):
            assert key in data

    def test_export_contains_state_payload(self, agent):
        agent.set_goal("exported goal")
        data = agent.export_state()
        assert data["state_payload"] is not None
        assert data["state_payload"].get("goal") == "exported goal"

    def test_restore_state_roundtrip(self, agent):
        agent.set_goal("goal before export")
        data = agent.export_state()

        # Create a fresh session and restore
        fresh = AgentState(session_id="restore-target", backend="memory")
        payload = fresh.restore_state(data)
        assert payload.goal == "goal before export"
        assert payload.session_id == "restore-target"

    def test_restore_state_without_payload_raises(self, agent):
        with pytest.raises(ValueError, match="state_payload"):
            agent.restore_state({"no_payload": True})

    def test_export_without_session(self, sessionless):
        data = sessionless.export_state()
        assert data["session_id"] is None
        assert data["state_payload"] is None

    def test_export_is_json_serializable(self, agent):
        agent.set_goal("json test goal")
        data = agent.export_state()
        json.dumps(data, default=str)  # should not raise


# ──────────────────────────────────────────────────────────────────────────────
# 15. Representation
# ──────────────────────────────────────────────────────────────────────────────


class TestRepresentation:
    def test_repr_contains_session(self, agent):
        r = repr(agent)
        assert "test-session" in r

    def test_repr_contains_backend(self, agent):
        r = repr(agent)
        assert "local:memory" in r

    def test_str_multiline(self, agent):
        s = str(agent)
        assert "\n" in s
        assert "test-session" in s

    def test_str_sessionless(self, sessionless):
        s = str(sessionless)
        assert "none" in s.lower() or "(none)" in s


# ──────────────────────────────────────────────────────────────────────────────
# 16. Cross-layer integration
# ──────────────────────────────────────────────────────────────────────────────


class TestCrossLayerIntegration:
    def test_remember_and_recall_roundtrip(self, agent):
        agent.remember("The database uses PostgreSQL for persistence")
        results = agent.recall("PostgreSQL database")
        texts = [m.content for m in results]
        assert any("PostgreSQL" in t for t in texts)

    def test_memory_and_knowledge_in_same_session(self, agent):
        mem_id = agent.remember("FastAPI depends on Pydantic for schema validation")
        agent.learn("FastAPI", "uses", "Pydantic", memory_id=mem_id)
        sg = agent.know_about("FastAPI", depth=1)
        assert sg.entity_count >= 1

    def test_full_agent_workflow(self):
        """Simulate a realistic agent flow end-to-end."""
        a = AgentState(session_id="workflow-test", backend="memory")

        # Set up
        a.set_goal("Implement user authentication")
        a.set_plan(["Design schema", "Implement models", "Add endpoints", "Test"])
        a.remember("We're using FastAPI + SQLAlchemy")
        a.learn("FastAPI", "uses", "SQLAlchemy")

        # Work
        a.snapshot(label="before-models")
        a.advance()
        a.record_tool("code_gen", {"file": "models.py", "lines": 120})

        # Checkpoint
        chk_id = a.checkpoint()
        a.advance()

        # Simulate crash recovery
        a.resume_from(chk_id)
        payload = a.current_state()
        assert payload.step == 1  # rolled back to after first advance

        # Build context for LLM
        ctx = a.build_context("implement auth endpoints", budget_tokens=3000)
        assert ctx.token_count >= 0

        # Status check
        s = a.status()
        assert s["session_id"] == "workflow-test"
        assert "memory" in s
