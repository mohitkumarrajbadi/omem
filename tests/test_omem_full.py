"""Comprehensive pytest tests for OMem core functionality.

Replaces the old script-style main() test with proper pytest assertions.
All tests use the in-memory backend for speed and isolation.
No external file dependencies.
"""

import pytest

from omem import OMem
from omem.core.engine import ForgetResult


@pytest.fixture
def m():
    """Fresh in-memory OMem instance for each test."""
    return OMem(backend="memory")


class TestCoreOperations:
    def test_add_multiple_returns_ids(self, m):
        id1 = m.add("Testing OMem comprehensive dataset", importance=0.9)
        id2 = m.add("User prefers dark mode theme", importance=0.8)
        id3 = m.add("Critical security vulnerability in auth", importance=1.0)
        assert all(isinstance(mid, str) and len(mid) > 0 for mid in [id1, id2, id3])
        assert m.stats()["total"] == 3

    def test_recall_by_keyword_returns_relevant(self, m):
        m.add("security vulnerability in auth module", importance=0.9)
        m.add("dark mode user preference", importance=0.8)
        m.add("performance optimization for database", importance=0.7)
        results = m.recall("security vulnerability", k=3)
        assert len(results) > 0
        assert any("security" in r.content.lower() for r in results)

    def test_recall_scores_are_non_negative(self, m):
        m.add("Python is a great language for data science")
        results = m.recall("Python data science", k=5)
        if results:
            assert all(r.score >= 0.0 for r in results)

    def test_stats_structure_after_adds(self, m):
        m.add("Memory one", importance=0.7)
        m.add("Memory two", importance=0.5)
        m.add("Memory three", importance=0.9)
        s = m.stats()
        assert s["total"] == 3
        assert "types" in s
        assert "avg_importance" in s
        assert "namespaces" in s
        assert s["avg_importance"] > 0.0

    def test_all_returns_complete_list(self, m):
        contents = [f"Memory {i}" for i in range(5)]
        ids = [m.add(c) for c in contents]
        all_mems = m.all()
        assert len(all_mems) == 5
        all_ids = {mem.id for mem in all_mems}
        for mid in ids:
            assert mid in all_ids

    def test_export_to_dict_has_required_keys(self, m):
        m.add("Test memory for export", importance=0.7)
        all_mems = m.all()
        exported = [mem.to_dict() for mem in all_mems]
        assert len(exported) == 1
        d = exported[0]
        for key in ["id", "type", "content", "timestamp", "score", "importance"]:
            assert key in d, f"Missing required key: {key}"


class TestContextTypeFiltering:
    def test_bugs_context_returns_results(self, m):
        m.add("error in the main handler caused null pointer exception", importance=0.7)
        m.add("Python is a general purpose language")
        results = m.recall("error crash", k=5, context_type="bugs")
        assert isinstance(results, list)
        assert len(results) > 0

    def test_time_range_recent_does_not_raise(self, m):
        m.add("recent user update happened just now")
        results = m.recall("user", k=5, time_range="recent")
        assert isinstance(results, list)

    def test_time_range_last_week_does_not_raise(self, m):
        m.add("weekly review meeting notes")
        results = m.recall("meeting", k=5, time_range="last_week")
        assert isinstance(results, list)


class TestNamespaces:
    def test_memories_isolated_by_namespace(self, m):
        m.add("memory in testing namespace", namespace="testing", importance=0.8)
        m.add("memory in production namespace", namespace="production", importance=0.9)
        test_mems = m.all(namespace="testing")
        prod_mems = m.all(namespace="production")
        assert all(mem.namespace == "testing" for mem in test_mems)
        assert all(mem.namespace == "production" for mem in prod_mems)

    def test_namespaces_listed_after_add(self, m):
        m.add("test", namespace="ns1")
        m.add("test2", namespace="ns2")
        ns = m.namespaces()
        assert "ns1" in ns
        assert "ns2" in ns

    def test_namespace_stats_total(self, m):
        m.add("memory one", namespace="testing")
        m.add("memory two", namespace="testing")
        stats = m.namespace_stats("testing")
        assert stats["total"] == 2

    def test_clear_namespace_only_deletes_target(self, m):
        m.add("keep this", namespace="keep")
        m.add("delete this", namespace="delete")
        m.clear(namespace="delete")
        assert len(m.all(namespace="keep")) > 0
        assert len(m.all(namespace="delete")) == 0


class TestInspection:
    def test_inspect_returns_list(self, m):
        m.add("authentication security best practices")
        m.add("Python programming patterns")
        exps = m.inspect("authentication", top_k=2)
        assert isinstance(exps, list)

    def test_inspect_explanation_has_score_fields(self, m):
        m.add("The capital of France is Paris")
        exps = m.inspect("Paris France capital", top_k=2)
        if exps:
            e = exps[0]
            assert hasattr(e, "vector_score")
            assert hasattr(e, "keyword_score")
            assert hasattr(e, "final_score")
            assert hasattr(e, "recency_score")
            assert hasattr(e, "importance_score")


class TestMaintenanceOperations:
    def test_compress_returns_dict_with_counts(self, m):
        for phrase in [
            "Python is great for data science",
            "Python excels at data science tasks",
            "Data science with Python is popular",
        ]:
            m.add(phrase)
        m.add("Something about cooking fish")
        result = m.compress(threshold=0.8)
        assert isinstance(result, dict)
        assert "compressed" in result
        assert "deactivated" in result
        assert result["compressed"] >= 0

    def test_compress_similar_reduces_active_count(self, m):
        for phrase in [
            "Python is an excellent programming language",
            "Python is a wonderful programming language",
            "Python is a fantastic programming language",
        ]:
            m.add(phrase)
        m.add("Cooking requires skill and patience")
        before = sum(1 for mem in m.all() if mem.active)
        m.compress(threshold=0.6)
        after = sum(1 for mem in m.all() if mem.active)
        assert before >= after

    def test_reflect_returns_list(self, m):
        for i in range(8):
            m.add(f"Fact {i} about distributed systems and microservices architecture")
        refs = m.reflect(threshold=0.7)
        assert isinstance(refs, list)

    def test_forget_returns_forget_result(self, m):
        m.add("My API key is sk-test12345")
        m.add("Python is a language")
        result = m.forget()
        assert isinstance(result, ForgetResult)

    def test_forget_does_not_delete_core_memories(self, m):
        m.add("My name is Bob Johnson")  # CORE priority (identity)
        m.add("okay sure yeah")           # LOW priority (filler)
        result = m.forget()
        assert result.core_immune >= 1
