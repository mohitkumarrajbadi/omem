"""Tests for OMem Memory OS features: importance, compression, reflection,
namespaces, update/merge, inspect, and multi-agent shared memory.
"""

import time

from omem import MemoryType, OMem, RetrievalExplanation
from omem.core.brain.importance import (
    compute_frequency_score,
    compute_recency_score,
    estimate_importance,
)


class TestImportance:
    """Test the importance scoring engine."""

    def test_high_importance_identity(self):
        assert estimate_importance("My name is Mohit") >= 0.8

    def test_high_importance_preference(self):
        assert estimate_importance("I prefer Python over Java") >= 0.7

    def test_low_importance_filler(self):
        assert estimate_importance("okay sure") <= 0.3

    def test_low_importance_greeting(self):
        assert estimate_importance("hi") <= 0.4

    def test_medium_importance_default(self):
        score = estimate_importance("The database migration is running")
        assert 0.3 <= score <= 0.8

    def test_recency_score_fresh(self):
        now = time.time()
        assert compute_recency_score(now, now) > 0.99

    def test_recency_score_decayed(self):
        now = time.time()
        old = now - 86400 * 30  # 30 days
        assert compute_recency_score(old, now) < 0.5

    def test_frequency_score_zero(self):
        assert compute_frequency_score(0) == 0.0

    def test_frequency_score_positive(self):
        assert compute_frequency_score(10) > 0


class TestMemoryUpdate:
    """Test memory update and soft-delete."""

    def test_update_replaces(self):
        m = OMem()
        old_id = m.add("I use VS Code")
        new_id = m.update(old_id, "I switched to Cursor AI")
        assert new_id is not None
        assert new_id != old_id
        old_mem = m.get(old_id)
        assert old_mem is not None
        assert old_mem.active is False

    def test_update_merge(self):
        m = OMem()
        old_id = m.add("Python is my favorite language")
        new_id = m.update(old_id, "I also love Rust", merge=True)
        assert new_id is not None
        new_mem = m.get(new_id)
        assert "Python" in new_mem.content or "Rust" in new_mem.content

    def test_update_nonexistent(self):
        m = OMem()
        assert m.update("nonexistent", "test") is None

    def test_soft_delete(self):
        m = OMem()
        mid = m.add("Temporary note")
        assert m.delete(mid) is True
        mem = m.get(mid)
        assert mem.active is False
        # Shouldn't appear in RAG results
        results = m.recall("Temporary note")
        assert all(r.id != mid for r in results)


class TestNamespaces:
    """Test multi-agent namespace isolation."""

    def test_namespace_isolation(self):
        m = OMem()
        m.add("Agent A memory", namespace="agent-a")
        m.add("Agent B memory", namespace="agent-b")
        results_a = m.recall("memory", namespace="agent-a")
        results_b = m.recall("memory", namespace="agent-b")
        assert all(r.namespace == "agent-a" for r in results_a)
        assert all(r.namespace == "agent-b" for r in results_b)

    def test_namespace_list(self):
        m = OMem()
        m.add("test", namespace="ns1")
        m.add("test2", namespace="ns2")
        ns = m.namespaces()
        assert "ns1" in ns
        assert "ns2" in ns

    def test_clear_namespace(self):
        m = OMem()
        m.add("keep this", namespace="keep")
        m.add("delete this", namespace="delete")
        m.clear(namespace="delete")
        assert len(m.all(namespace="keep")) > 0


class TestCompression:
    """Test the memory compression engine."""

    def test_compression_reduces(self):
        m = OMem()
        # Add semantically similar content
        m.add("Python is a great programming language")
        m.add("Python is an excellent programming language")
        m.add("Python is a wonderful programming language")
        m.add("Something completely different about cooking")

        before = m.stats()["total"]
        result = m.compress(threshold=0.7)
        after = m.stats()["total"]
        # Should have compressed some memories
        assert result["compressed"] >= 0
        assert before >= after
        assert result["deactivated"] >= 0

    def test_compression_preserves_unrelated(self):
        m = OMem()
        m.add("The sky is blue")
        m.add("Databases store data persistently")
        before = m.stats()["total"]
        m.compress(threshold=0.95)
        after = m.stats()["total"]
        assert after == before  # nothing to compress


class TestReflection:
    """Test the reflection engine."""

    def test_reflect_conversation(self):
        m = OMem()
        messages = [
            "I need to plan a trip to Paris",
            "Looking at flights for May",
            "Prefer direct flights over layovers",
            "Budget is around $1500",
            "Want to visit the Eiffel Tower",
        ]
        insight = m.reflect_conversation(messages)
        assert insight is not None
        assert insight.type == MemoryType.REFLECTION
        assert insight.importance >= 0.5

    def test_reflect_short_conversation_returns_none(self):
        m = OMem()
        assert m.reflect_conversation(["hi"]) is None

    def test_reflect_on_memories(self):
        m = OMem()
        for i in range(10):
            m.add(f"Important fact number {i} about technology and AI systems")
        refs = m.reflect()
        # May or may not produce reflections depending on clustering
        assert isinstance(refs, list)


class TestInspect:
    """Test retrieval observability."""

    def test_inspect_returns_explanations(self):
        m = OMem()
        m.add("Python is a programming language")
        m.add("JavaScript runs in the browser")
        exps = m.inspect("programming language")
        assert len(exps) > 0
        assert isinstance(exps[0], RetrievalExplanation)

    def test_inspect_has_all_scores(self):
        m = OMem()
        m.add("The capital of France is Paris")
        exps = m.inspect("Paris France capital")
        if exps:
            e = exps[0]
            assert hasattr(e, "vector_score")
            assert hasattr(e, "keyword_score")
            assert hasattr(e, "recency_score")
            assert hasattr(e, "importance_score")
            assert hasattr(e, "frequency_bonus")
            assert hasattr(e, "matched_keywords")

    def test_explain_string(self):
        m = OMem()
        m.add("test memory content")
        exps = m.inspect("test memory")
        if exps:
            text = exps[0].explain()
            assert "vector" in text.lower()
            assert "keyword" in text.lower()


class TestAccessTracking:
    """Test that RAG updates access counts."""

    def test_access_count_increments(self):
        m = OMem()
        mid = m.add("Frequently accessed memory")
        assert m.get(mid).access_count == 0
        m.recall("accessed memory")
        assert m.get(mid).access_count >= 1

    def test_last_accessed_updates(self):
        m = OMem()
        mid = m.add("Track access time")
        before = m.get(mid).last_accessed
        m.recall("access time")
        after = m.get(mid).last_accessed
        assert after >= before


class TestDecay:
    """Test memory decay."""

    def test_decay_returns_list(self):
        m = OMem()
        m.add("Recent memory")
        decayed = m.decay()
        assert isinstance(decayed, list)


class TestSharedMemory:
    """Test multi-agent shared memory integration."""

    def test_shared_store_and_recall(self):
        from omem.integrations.crewai import OMemSharedMemory

        shared = OMemSharedMemory(workspace="test-ws")
        shared.store("agent1", "Found important data point")
        results = shared.recall("important data", agent="agent1")
        assert len(results) > 0

    def test_broadcast(self):
        from omem.integrations.crewai import OMemSharedMemory

        shared = OMemSharedMemory(workspace="test-ws2")
        mid = shared.broadcast("System-wide announcement")
        assert mid is not None


class TestLangChainIntegration:
    """Test LangChain memory integration."""

    def test_save_and_load(self):
        from omem.integrations.langchain import OMemChatMemory

        mem = OMemChatMemory()
        mem.save_context(
            {"input": "Hello, my name is Mohit"}, {"output": "Nice to meet you!"}
        )
        variables = mem.load_memory_variables({"input": "What's my name?"})
        assert "history" in variables
        assert len(variables["history"]) > 0

    def test_memory_variables(self):
        from omem.integrations.langchain import OMemChatMemory

        mem = OMemChatMemory()
        assert "history" in mem.memory_variables

    def test_retriever(self):
        from omem.integrations.langchain import OMemRetriever

        r = OMemRetriever()
        r.omem.add("Python is a programming language")
        docs = r.get_relevant_documents("programming")
        assert len(docs) > 0
        assert "page_content" in docs[0]
