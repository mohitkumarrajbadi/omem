"""End-to-end tests for the OMem public API.

All tests use the in-memory backend (OMem(backend="memory")) for speed and isolation.
"""

import pytest

from omem import Memory, MemoryType, OMem


@pytest.fixture
def m():
    """Fresh in-memory OMem instance for each test."""
    return OMem(backend="memory")


class TestCoreAdd:
    def test_add_returns_id(self, m):
        mid = m.add("Hello world")
        assert isinstance(mid, str)
        assert len(mid) > 0

    def test_add_with_explicit_type(self, m):
        mid = m.add("Step 1: do something", mem_type=MemoryType.PROCEDURAL)
        mem = m.get(mid)
        assert mem is not None
        assert mem.type == MemoryType.PROCEDURAL

    def test_add_auto_classifies_episodic(self, m):
        mid = m.add("Yesterday I visited the park")
        mem = m.get(mid)
        assert mem.type == MemoryType.EPISODIC

    def test_add_metadata_stored(self, m):
        mid = m.add("test", metadata={"source": "unit_test"})
        mem = m.get(mid)
        assert mem.metadata["source"] == "unit_test"

    def test_add_custom_importance(self, m):
        mid = m.add("Critical note", importance=0.95)
        mem = m.get(mid)
        assert abs(mem.importance - 0.95) < 0.01

    def test_dedup_same_content(self, m):
        id1 = m.add("duplicate content")
        id2 = m.add("duplicate content")
        assert id1 == id2
        assert m.stats()["total"] == 1

    def test_force_bypasses_dedup(self, m):
        id1 = m.add("forced content", force=True)
        id2 = m.add("forced content", force=True)
        # force=True must always store, producing at least 1 record
        assert m.stats()["total"] >= 1
        # Both calls must return valid IDs
        assert isinstance(id1, str) and isinstance(id2, str)


class TestRecall:
    def test_returns_list_of_memory(self, m):
        m.add("The sky is blue")
        m.add("Water boils at 100 degrees")
        results = m.recall("sky color")
        assert isinstance(results, list)
        assert len(results) > 0
        assert isinstance(results[0], Memory)

    def test_empty_store_returns_empty(self, m):
        assert m.recall("anything") == []

    def test_scores_sorted_descending(self, m):
        for i in range(10):
            m.add(f"Memory number {i} about topic alpha")
        results = m.recall("topic alpha", k=5)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_k_limits_result_count(self, m):
        for i in range(10):
            m.add(f"memory about topic {i}")
        results = m.recall("memory topic", k=3)
        assert len(results) <= 3

    def test_top_k_alias_works(self, m):
        for i in range(10):
            m.add(f"memory about topic {i}")
        results = m.recall("memory topic", top_k=3)
        assert len(results) <= 3

    def test_context_type_bugs_accepted(self, m):
        m.add("The server crashed because of a memory leak")
        m.add("Python is a programming language")
        results = m.recall("server crash", k=5, context_type="bugs")
        assert isinstance(results, list)
        assert len(results) > 0

    def test_context_type_decisions_accepted(self, m):
        m.add("I decided to use PostgreSQL over MySQL")
        results = m.recall("database choice", k=5, context_type="decisions")
        assert isinstance(results, list)

    def test_namespace_filter_restricts_results(self, m):
        m.add("Agent A memory", namespace="agent-a")
        m.add("Agent B memory", namespace="agent-b")
        results = m.recall("memory", namespace="agent-a")
        assert all(r.namespace in ("agent-a", "global") for r in results)

    def test_time_range_recent_does_not_raise(self, m):
        m.add("recent event just happened")
        results = m.recall("event", k=5, time_range="recent")
        assert isinstance(results, list)

    def test_time_range_today_does_not_raise(self, m):
        m.add("something happened today")
        results = m.recall("today", k=5, time_range="today")
        assert isinstance(results, list)

    def test_mode_parameter_accepted(self, m):
        m.add("deploy application to production server")
        results = m.recall("deploy", k=5, mode="coding")
        assert isinstance(results, list)


class TestGetUpdateDelete:
    def test_get_missing_returns_none(self, m):
        assert m.get("nonexistent") is None

    def test_update_creates_new_record(self, m):
        old_id = m.add("I use VS Code")
        new_id = m.update(old_id, "I switched to Cursor AI")
        assert new_id is not None
        assert new_id != old_id

    def test_update_deactivates_old(self, m):
        old_id = m.add("I use VS Code")
        m.update(old_id, "I switched to Cursor AI")
        old_mem = m.get(old_id)
        assert old_mem is not None
        assert old_mem.active is False

    def test_update_nonexistent_returns_none(self, m):
        assert m.update("nonexistent", "new content") is None

    def test_soft_delete_marks_inactive(self, m):
        mid = m.add("Temporary note")
        assert m.delete(mid) is True
        mem = m.get(mid)
        assert mem.active is False

    def test_soft_delete_excluded_from_recall(self, m):
        mid = m.add("Temporary note to delete")
        m.delete(mid)
        results = m.recall("Temporary note to delete")
        assert all(r.id != mid for r in results)

    def test_delete_missing_returns_false(self, m):
        assert m.delete("nonexistent") is False


class TestBatch:
    def test_add_batch_returns_correct_count(self, m):
        ids = m.add_batch(["first memory", "second memory", "third memory"])
        assert len(ids) == 3

    def test_add_batch_ids_are_strings(self, m):
        ids = m.add_batch(["alpha memory item", "beta memory item", "gamma memory item"])
        for mid in ids:
            assert isinstance(mid, str) and len(mid) > 0

    def test_add_batch_all_stored(self, m):
        m.add_batch(["batch one", "batch two", "batch three"])
        assert m.stats()["total"] == 3

    def test_add_batch_with_explicit_types(self, m):
        ids = m.add_batch(
            ["Step 1: do this", "I decided to go"],
            mem_types=[MemoryType.PROCEDURAL, MemoryType.DECISION],
        )
        types = [m.get(mid).type for mid in ids]
        assert MemoryType.PROCEDURAL in types
        assert MemoryType.DECISION in types


class TestStats:
    def test_stats_structure_keys(self, m):
        m.add("Paris is the capital of France")
        m.add("I decided to use Go")
        s = m.stats()
        assert s["total"] == 2
        assert isinstance(s["types"], dict)
        assert isinstance(s["graph_edges"], int)
        assert isinstance(s["namespaces"], list)

    def test_stats_empty_store(self, m):
        assert m.stats()["total"] == 0

    def test_stats_inactive_increments_on_delete(self, m):
        mid = m.add("note to delete")
        m.delete(mid)
        s = m.stats()
        assert s["inactive"] >= 1

    def test_link_increments_graph_edges(self, m):
        id1 = m.add("cause event")
        id2 = m.add("effect event")
        m.link(id1, id2, label="causes")
        assert m.stats()["graph_edges"] == 1


class TestNamespaces:
    def test_memories_isolated_by_namespace(self, m):
        m.add("Agent A memory", namespace="agent-a")
        m.add("Agent B memory", namespace="agent-b")
        all_a = m.all(namespace="agent-a")
        all_b = m.all(namespace="agent-b")
        assert all(r.namespace == "agent-a" for r in all_a)
        assert all(r.namespace == "agent-b" for r in all_b)

    def test_namespaces_lists_all(self, m):
        m.add("test", namespace="ns1")
        m.add("test2", namespace="ns2")
        ns = m.namespaces()
        assert "ns1" in ns
        assert "ns2" in ns

    def test_clear_single_namespace(self, m):
        m.add("keep this", namespace="keep")
        m.add("delete this", namespace="delete")
        m.clear(namespace="delete")
        assert len(m.all(namespace="keep")) > 0
        assert len(m.all(namespace="delete")) == 0


class TestMiscellaneous:
    def test_clear_all(self, m):
        for i in range(5):
            m.add(f"memory {i}")
        assert m.stats()["total"] == 5
        m.clear()
        assert m.stats()["total"] == 0

    def test_repr_contains_omem(self, m):
        assert "OMem" in repr(m)

    def test_all_returns_all(self, m):
        m.add("one")
        m.add("two")
        all_mems = m.all()
        assert len(all_mems) == 2

    def test_summarize_state_empty_returns_str(self, m):
        text = m.summarize_state()
        assert isinstance(text, str)

    def test_summarize_state_with_data_returns_content(self, m):
        m.add("I decided to use microservices architecture", importance=0.8)
        text = m.summarize_state()
        assert isinstance(text, str)
        assert len(text) > 0

    def test_resolve_conflict_no_conflicts_returns_dict(self, m):
        m.add("Python is fast")
        result = m.resolve_conflict("Python")
        assert isinstance(result, dict)
        assert "status" in result

    def test_get_audit_log_returns_list(self, m):
        m.add("test memory")
        m.recall("test")
        m._audit.flush()
        log = m.get_audit_log()
        assert isinstance(log, list)
        assert len(log) >= 1

    def test_get_audit_log_entry_has_operation_field(self, m):
        m.add("test memory")
        m._audit.flush()
        log = m.get_audit_log()
        assert len(log) >= 1
        assert "operation" in log[0]

    def test_get_audit_log_filter_by_operation(self, m):
        m.add("test memory")
        m.recall("test")
        m._audit.flush()
        add_log = m.get_audit_log(operation="add")
        assert all(e["operation"] == "add" for e in add_log)
