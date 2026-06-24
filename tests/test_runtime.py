"""Tests for Phase 9 — RuntimeOS.

Validates: agent registration, heartbeat, stale eviction, state sync,
crash recovery, deregistration, and AgentState shortcuts.
"""

from __future__ import annotations

import os
import tempfile
import time
from unittest.mock import MagicMock

import pytest

from omem.runtime.layer import AgentRegistration, RuntimeOS


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def tmp_db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path
    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture
def mock_state():
    m = MagicMock()
    payload = MagicMock()
    payload.session_id = "sess-1"
    payload.goal = "test"
    payload.status = "active"
    payload.step = 0
    payload.plan = []
    payload.namespace = "default"
    payload.updated_at = time.time()
    payload.version = 1
    m.load.return_value = payload
    m.resume_latest.return_value = payload
    return m


@pytest.fixture
def runtime(tmp_db, mock_state):
    return RuntimeOS(state=mock_state, db_path=tmp_db)


# ──────────────────────────────────────────────────────────────────────────────
# AgentRegistration
# ──────────────────────────────────────────────────────────────────────────────


class TestAgentRegistration:
    def test_to_dict(self):
        reg = AgentRegistration(
            agent_id="bot-1",
            session_id="sess-1",
            namespace="default",
            capabilities=["web"],
            status="active",
            registered_at=100.0,
            last_heartbeat=200.0,
        )
        d = reg.to_dict()
        assert d["agent_id"] == "bot-1"
        assert d["capabilities"] == ["web"]
        assert d["status"] == "active"

    def test_from_dict_roundtrip(self):
        reg = AgentRegistration(
            agent_id="x",
            session_id="s",
            namespace="ns",
            capabilities=["a", "b"],
            status="idle",
            registered_at=1.0,
            last_heartbeat=2.0,
            metadata={"k": "v"},
        )
        reg2 = AgentRegistration.from_dict(reg.to_dict())
        assert reg2.agent_id == "x"
        assert reg2.capabilities == ["a", "b"]
        assert reg2.metadata == {"k": "v"}


# ──────────────────────────────────────────────────────────────────────────────
# Registration
# ──────────────────────────────────────────────────────────────────────────────


class TestRuntimeOSRegistration:
    def test_register_returns_registration(self, runtime):
        reg = runtime.register("agent-1", "sess-1")
        assert reg.agent_id == "agent-1"
        assert reg.session_id == "sess-1"
        assert reg.status == "active"

    def test_register_default_namespace(self, runtime):
        reg = runtime.register("agent-2", "sess-2")
        assert reg.namespace == "default"

    def test_register_with_capabilities(self, runtime):
        reg = runtime.register("coder", "sess-c", capabilities=["git", "bash"])
        assert "git" in reg.capabilities

    def test_register_with_metadata(self, runtime):
        reg = runtime.register("b", "s", metadata={"model": "gpt-4"})
        assert reg.metadata["model"] == "gpt-4"

    def test_register_updates_existing(self, runtime):
        runtime.register("agent-x", "sess-old")
        reg = runtime.register("agent-x", "sess-new")
        assert reg.session_id == "sess-new"
        assert reg.status == "active"

    def test_register_persists_to_db(self, tmp_db, mock_state):
        r1 = RuntimeOS(state=mock_state, db_path=tmp_db)
        r1.register("persist-agent", "persist-sess", namespace="prod")
        # New RuntimeOS instance reads from the same DB
        r2 = RuntimeOS(state=mock_state, db_path=tmp_db)
        agents = r2.list_agents("prod")
        assert any(a.agent_id == "persist-agent" for a in agents)


# ──────────────────────────────────────────────────────────────────────────────
# Heartbeat and stale eviction
# ──────────────────────────────────────────────────────────────────────────────


class TestHeartbeat:
    def test_heartbeat_returns_true_for_known_agent(self, runtime):
        runtime.register("hb-agent", "sess-hb")
        assert runtime.heartbeat("hb-agent") is True

    def test_heartbeat_returns_false_for_unknown(self, runtime):
        assert runtime.heartbeat("ghost") is False

    def test_heartbeat_updates_timestamp(self, runtime):
        runtime.register("ts-agent", "sess-ts")
        before = time.time()
        time.sleep(0.01)
        runtime.heartbeat("ts-agent")
        reg = runtime.get_agent("ts-agent")
        assert reg.last_heartbeat >= before

    def test_heartbeat_updates_status(self, runtime):
        runtime.register("status-agent", "sess-st")
        runtime.heartbeat("status-agent", status="idle")
        reg = runtime.get_agent("status-agent")
        assert reg.status == "idle"

    def test_evict_stale_marks_crashed(self, runtime):
        runtime.register("stale-agent", "sess-st")
        # Backdating heartbeat
        reg = runtime._in_mem["stale-agent"]
        reg.last_heartbeat = time.time() - 400
        evicted = runtime.evict_stale(max_idle_seconds=300)
        assert "stale-agent" in evicted
        updated = runtime.get_agent("stale-agent")
        assert updated.status == "crashed"

    def test_evict_stale_does_not_evict_active(self, runtime):
        runtime.register("fresh", "sess-fr")
        evicted = runtime.evict_stale(max_idle_seconds=300)
        assert "fresh" not in evicted


# ──────────────────────────────────────────────────────────────────────────────
# State sync and recovery
# ──────────────────────────────────────────────────────────────────────────────


class TestSync:
    def test_sync_returns_state_dict(self, runtime):
        result = runtime.sync("sess-1")
        assert result["session_id"] == "sess-1"
        assert "goal" in result
        assert "status" in result

    def test_sync_without_state_raises(self):
        r = RuntimeOS(state=None, db_path=":memory:")
        with pytest.raises(RuntimeError):
            r.sync("any-session")

    def test_sync_invalid_session_raises(self, tmp_db):
        m = MagicMock()
        m.load.side_effect = Exception("not found")
        r = RuntimeOS(state=m, db_path=tmp_db)
        with pytest.raises(RuntimeError):
            r.sync("invalid")


class TestRecovery:
    def test_recover_returns_state_for_known_agent(self, runtime, mock_state):
        runtime.register("crash-agent", "sess-1")
        reg = runtime._in_mem["crash-agent"]
        reg.status = "crashed"
        result = runtime.recover("crash-agent")
        assert result is not None
        assert result["session_id"] == "sess-1"
        assert result["recovered_for_agent"] == "crash-agent"

    def test_recover_re_registers_as_active(self, runtime, mock_state):
        runtime.register("re-agent", "sess-r")
        runtime._in_mem["re-agent"].status = "crashed"
        runtime.recover("re-agent")
        reg = runtime.get_agent("re-agent")
        assert reg.status == "active"

    def test_recover_returns_none_for_unknown_agent(self, runtime):
        result = runtime.recover("ghost-agent")
        assert result is None

    def test_recover_returns_none_if_no_checkpoint(self, tmp_db):
        m = MagicMock()
        m.resume_latest.side_effect = Exception("no checkpoint")
        r = RuntimeOS(state=m, db_path=tmp_db)
        r.register("no-ckpt-agent", "sess-nc")
        result = r.recover("no-ckpt-agent")
        assert result is None


# ──────────────────────────────────────────────────────────────────────────────
# List and query
# ──────────────────────────────────────────────────────────────────────────────


class TestListAgents:
    def test_list_agents_in_namespace(self, runtime):
        runtime.register("a1", "s1", namespace="prod")
        runtime.register("a2", "s2", namespace="prod")
        runtime.register("a3", "s3", namespace="staging")
        agents = runtime.list_agents("prod")
        assert len(agents) == 2
        assert all(a.namespace == "prod" for a in agents)

    def test_list_agents_status_filter(self, runtime):
        runtime.register("active-a", "s1", namespace="ns")
        runtime.register("idle-a", "s2", namespace="ns")
        runtime._in_mem["idle-a"].status = "idle"
        active = runtime.list_agents("ns", status="active")
        assert len(active) == 1
        assert active[0].agent_id == "active-a"

    def test_list_agents_empty_namespace(self, runtime):
        assert runtime.list_agents("empty-ns") == []

    def test_get_agent_found(self, runtime):
        runtime.register("get-me", "sess-gm")
        reg = runtime.get_agent("get-me")
        assert reg is not None
        assert reg.agent_id == "get-me"

    def test_get_agent_not_found(self, runtime):
        assert runtime.get_agent("not-here") is None


class TestDeregister:
    def test_deregister_returns_true(self, runtime):
        runtime.register("bye", "sess-bye")
        assert runtime.deregister("bye") is True

    def test_deregister_returns_false_for_unknown(self, runtime):
        assert runtime.deregister("ghost") is False

    def test_deregistered_agent_not_in_active_list(self, runtime):
        runtime.register("done-agent", "sess-d", namespace="ns")
        runtime.deregister("done-agent")
        active = runtime.list_agents("ns", status="active")
        assert not any(a.agent_id == "done-agent" for a in active)


class TestNamespaceSummary:
    def test_summary_counts(self, runtime):
        runtime.register("a1", "s1", namespace="summary-ns")
        runtime.register("a2", "s2", namespace="summary-ns")
        runtime._in_mem["a2"].status = "crashed"
        s = runtime.namespace_summary("summary-ns")
        assert s["total"] == 2
        assert s["active"] == 1
        assert s["crashed"] == 1


# ──────────────────────────────────────────────────────────────────────────────
# Integration: AgentState shortcuts
# ──────────────────────────────────────────────────────────────────────────────


class TestAgentStateRuntime:
    def test_register_agent_shorthand(self):
        from omem import AgentState
        agent = AgentState(session_id="rt-test", backend="memory")
        reg = agent.register_agent("my-bot", capabilities=["rag"])
        assert reg["agent_id"] == "my-bot"
        assert reg["status"] == "active"

    def test_heartbeat_agent_shorthand(self):
        from omem import AgentState
        agent = AgentState(session_id="hb-test", backend="memory")
        agent.register_agent("hb-bot")
        ok = agent.heartbeat_agent("hb-bot")
        assert ok is True

    def test_heartbeat_unknown_agent(self):
        from omem import AgentState
        agent = AgentState(backend="memory")
        assert agent.heartbeat_agent("unknown") is False
