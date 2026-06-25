"""Tests for Phase 7 — ProvenanceOS.

Validates: event recording, trace queries, history, summary,
and AgentState integration.
"""

from __future__ import annotations

import time

import pytest

from omem.provenance.layer import ProvenanceChain, ProvenanceEvent, ProvenanceOS

# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def prov():
    return ProvenanceOS()


# ──────────────────────────────────────────────────────────────────────────────
# ProvenanceEvent and ProvenanceChain
# ──────────────────────────────────────────────────────────────────────────────


class TestProvenanceEvent:
    def test_to_dict_roundtrip(self):
        ev = ProvenanceEvent(
            id="prov_1",
            entity_id="mem-abc",
            entity_type="memory",
            operation="create",
            source="user",
            timestamp=1234567890.0,
            session_id="s1",
            namespace="default",
            confidence=0.9,
            related_ids=["mem-xyz"],
            metadata={"importance": 0.7},
        )
        d = ev.to_dict()
        assert d["entity_id"] == "mem-abc"
        assert d["operation"] == "create"
        assert d["related_ids"] == ["mem-xyz"]
        assert d["metadata"]["importance"] == 0.7


class TestProvenanceChain:
    def test_empty_chain(self):
        chain = ProvenanceChain(root_id="e1")
        assert chain.created_at is None
        assert chain.last_modified_at is None
        assert chain.source_chain == []
        assert chain.to_dict()["event_count"] == 0

    def test_chain_with_events(self):
        t1 = time.time()
        t2 = t1 + 10
        events = [
            ProvenanceEvent(
                id="p1", entity_id="e1", entity_type="memory",
                operation="create", source="user", timestamp=t1,
            ),
            ProvenanceEvent(
                id="p2", entity_id="e1", entity_type="memory",
                operation="update", source="agent", timestamp=t2,
            ),
        ]
        chain = ProvenanceChain(root_id="e1", events=events)
        assert chain.created_at == pytest.approx(t1, abs=0.001)
        assert chain.last_modified_at == pytest.approx(t2, abs=0.001)
        assert chain.source_chain == ["user", "agent"]


# ──────────────────────────────────────────────────────────────────────────────
# ProvenanceOS
# ──────────────────────────────────────────────────────────────────────────────


class TestProvenanceOS:
    def test_record_and_trace(self, prov):
        prov.record("mem-1", "memory", "create", source="user")
        chain = prov.trace("mem-1")
        assert chain.root_id == "mem-1"
        assert len(chain.events) == 1
        assert chain.events[0].operation == "create"

    def test_trace_empty(self, prov):
        chain = prov.trace("nonexistent")
        assert chain.root_id == "nonexistent"
        assert chain.events == []

    def test_record_multiple_events_for_same_entity(self, prov):
        prov.record("snap-1", "snapshot", "create", source="agent")
        prov.record("snap-1", "snapshot", "rollback", source="agent")
        prov.record("snap-1", "snapshot", "fork", source="agent")
        chain = prov.trace("snap-1")
        assert len(chain.events) == 3
        ops = [e.operation for e in chain.events]
        assert "create" in ops and "rollback" in ops and "fork" in ops

    def test_chain_sorted_chronologically(self, prov):
        now = time.time()
        # Record in reverse order
        for i in range(5, 0, -1):
            ev = ProvenanceEvent(
                id=f"p{i}",
                entity_id="chron-1",
                entity_type="memory",
                operation="update",
                source="agent",
                timestamp=now + i,
            )
            prov._store.add(ev)
        chain = prov.trace("chron-1")
        tss = [e.timestamp for e in chain.events]
        assert tss == sorted(tss)

    def test_history_returns_events(self, prov):
        prov.record("m1", "memory", "create", namespace="ns-a")
        prov.record("m2", "memory", "update", namespace="ns-a")
        prov.record("m3", "memory", "create", namespace="ns-b")
        history = prov.history("ns-a", limit=10)
        assert all(e.namespace == "ns-a" for e in history)
        assert len(history) == 2

    def test_history_limit(self, prov):
        for i in range(20):
            prov.record(f"e{i}", "memory", "create", namespace="limited")
        history = prov.history("limited", limit=5)
        assert len(history) <= 5

    def test_history_since(self, prov):
        prov.record("old", "memory", "create", namespace="time-test")
        after = time.time() + 0.001
        prov.record("new", "memory", "create", namespace="time-test")
        history_all = prov.history("time-test", limit=100)
        history_recent = prov.history("time-test", limit=100, since=after)
        assert len(history_recent) < len(history_all)

    def test_history_for_session(self, prov):
        prov.record("e1", "memory", "create", session_id="s-abc")
        prov.record("e2", "memory", "update", session_id="s-abc")
        prov.record("e3", "memory", "create", session_id="s-xyz")
        events = prov.history_for_session("s-abc")
        assert all(e.session_id == "s-abc" for e in events)

    def test_known_entities(self, prov):
        prov.record("ea", "memory", "create")
        prov.record("eb", "snapshot", "create")
        entities = prov.known_entities()
        assert "ea" in entities
        assert "eb" in entities

    def test_summary(self, prov):
        prov.record("m1", "memory", "create", source="user")
        prov.record("m2", "memory", "update", source="agent")
        prov.record("s1", "snapshot", "create", source="agent")
        s = prov.summary()
        assert s["total_events"] == 3
        assert s["entity_count"] == 3
        assert "create" in s["operations_breakdown"]
        assert "agent" in s["sources_breakdown"]

    def test_record_with_related_ids(self, prov):
        prov.record("m2", "memory", "merge",
                    related_ids=["m0", "m1"],
                    source="consolidation")
        chain = prov.trace("m2")
        assert chain.events[0].related_ids == ["m0", "m1"]

    def test_record_with_metadata(self, prov):
        prov.record("e1", "memory", "create",
                    source="user",
                    importance=0.8,
                    content_length=42)
        chain = prov.trace("e1")
        assert chain.events[0].metadata["importance"] == 0.8
        assert chain.events[0].metadata["content_length"] == 42

    def test_clear_entity(self, prov):
        prov.record("del", "memory", "create")
        prov.clear("del")
        chain = prov.trace("del")
        assert chain.events == []

    def test_clear_all(self, prov):
        prov.record("x", "memory", "create")
        prov.record("y", "snapshot", "create")
        prov.clear()
        assert prov.known_entities() == []

    def test_record_never_raises(self, prov):
        # Monkey-patch to force error
        original = prov._store.add
        prov._store.add = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
        prov.record("safe", "memory", "create")  # should not raise
        prov._store.add = original


# ──────────────────────────────────────────────────────────────────────────────
# Integration: AgentState provenance
# ──────────────────────────────────────────────────────────────────────────────


class TestAgentStateProvenance:
    def test_remember_records_provenance(self):
        from omem import AgentState
        agent = AgentState(session_id="prov-test", backend="memory")
        mid = agent.remember("Rust is fast")
        chain = agent.provenance.trace(mid)
        assert len(chain.events) >= 1
        assert chain.events[0].operation == "create"
        assert chain.events[0].entity_type == "memory"

    def test_learn_records_provenance(self):
        from omem import AgentState
        agent = AgentState(session_id="prov-learn", backend="memory")
        edge_id = agent.learn("Rust", "compiles_to", "native")
        chain = agent.provenance.trace(edge_id)
        assert len(chain.events) >= 1
        assert chain.events[0].entity_type == "edge"

    def test_snapshot_records_provenance(self):
        from omem import AgentState
        agent = AgentState(session_id="prov-snap", backend="memory")
        agent.set_goal("Test provenance")
        snap = agent.snapshot("test-snap")
        chain = agent.provenance.trace(snap.id)
        assert len(chain.events) >= 1
        assert chain.events[0].operation == "create"
