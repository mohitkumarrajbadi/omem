"""Tests for omem.types and core brain classification."""

import numpy as np

from omem.core.brain.classify import auto_classify
from omem.types import (
    PRIORITY_MULTIPLIER,
    Memory,
    MemoryPriority,
    MemoryStatus,
    MemoryTier,
    MemoryType,
    RetrievalExplanation,
)


class TestMemoryType:
    def test_all_twelve_values(self):
        assert len(MemoryType) == 12

    def test_enum_values(self):
        assert MemoryType.WORKING.value == 0
        assert MemoryType.ACTIVE.value == 6
        assert MemoryType.TOOL.value == 10
        assert MemoryType.SKILL.value == 11

    def test_names(self):
        names = {m.name for m in MemoryType}
        assert names == {
            "WORKING",
            "EPISODIC",
            "SEMANTIC",
            "CAUSAL",
            "DECISION",
            "PROCEDURAL",
            "ACTIVE",
            "REFLECTION",
            "SENSORY",
            "INSIGHT",
            "TOOL",
            "SKILL",
        }


class TestMemory:
    def test_creation(self):
        vec = np.zeros(384, dtype=np.float32)
        m = Memory(
            id="abc",
            type=MemoryType.SEMANTIC,
            content="hello",
            vector=vec,
            timestamp=1.0,
        )
        assert m.id == "abc"
        assert m.score == 0.0
        assert m.metadata == {}

    def test_to_dict(self):
        vec = np.zeros(384, dtype=np.float32)
        m = Memory(
            id="x",
            type=MemoryType.CAUSAL,
            content="test",
            vector=vec,
            timestamp=2.0,
            score=0.9,
        )
        d = m.to_dict()
        assert d["type"] == "CAUSAL"
        assert d["score"] == 0.9

    def test_repr_truncates(self):
        vec = np.zeros(384, dtype=np.float32)
        m = Memory(
            id="x",
            type=MemoryType.SEMANTIC,
            content="a" * 100,
            vector=vec,
            timestamp=0.0,
        )
        assert "..." in repr(m)


class TestAutoClassify:
    def test_procedural(self):
        assert auto_classify("Step 1: open the door") == MemoryType.PROCEDURAL
        assert auto_classify("How to bake a cake") == MemoryType.PROCEDURAL

    def test_causal(self):
        assert auto_classify("Rain caused flooding") == MemoryType.CAUSAL
        assert auto_classify("Due to high demand prices rose") == MemoryType.CAUSAL

    def test_decision(self):
        assert auto_classify("I decided to use Python") == MemoryType.DECISION
        assert auto_classify("User chose option B") == MemoryType.DECISION

    def test_episodic(self):
        assert auto_classify("Yesterday I went to the market") == MemoryType.EPISODIC
        assert auto_classify("Last week we visited the museum") == MemoryType.EPISODIC

    def test_working(self):
        assert auto_classify("Currently processing the request") == MemoryType.WORKING

    def test_active(self):
        assert auto_classify("Urgent: server is down") == MemoryType.ACTIVE

    def test_tool(self):
        assert auto_classify("MCP tool call returned status 200") == MemoryType.TOOL

    def test_skill(self):
        assert auto_classify("Learned workflow: always run migrate before deploy") == MemoryType.SKILL

    def test_semantic_fallback(self):
        assert auto_classify("The capital of France is Paris") == MemoryType.SEMANTIC
        assert auto_classify("Python is a programming language") == MemoryType.SEMANTIC


class TestMemoryStatus:
    def test_all_four_values(self):
        assert len(MemoryStatus) == 4

    def test_enum_values(self):
        assert MemoryStatus.ACTIVE.value == 0
        assert MemoryStatus.DEPRECATED.value == 1
        assert MemoryStatus.CONFLICTED.value == 2
        assert MemoryStatus.ARCHIVED.value == 3

    def test_names(self):
        names = {s.name for s in MemoryStatus}
        assert names == {"ACTIVE", "DEPRECATED", "CONFLICTED", "ARCHIVED"}


class TestMemoryTier:
    def test_all_six_values(self):
        assert len(MemoryTier) == 6

    def test_core_is_zero(self):
        assert MemoryTier.CORE.value == 0

    def test_forgotten_is_three(self):
        assert MemoryTier.FORGOTTEN.value == 3

    def test_names(self):
        names = {t.name for t in MemoryTier}
        assert names == {"CORE", "ACTIVE", "ARCHIVE", "FORGOTTEN", "SENSORY", "INSIGHT"}


class TestMemoryPriority:
    def test_all_four_values(self):
        assert len(MemoryPriority) == 4

    def test_core_is_zero(self):
        assert MemoryPriority.CORE.value == 0

    def test_low_is_last(self):
        assert MemoryPriority.LOW.value == 3

    def test_priority_multipliers_values(self):
        assert PRIORITY_MULTIPLIER[MemoryPriority.CORE] == 2.0
        assert PRIORITY_MULTIPLIER[MemoryPriority.HIGH] == 1.5
        assert PRIORITY_MULTIPLIER[MemoryPriority.NORMAL] == 1.0
        assert PRIORITY_MULTIPLIER[MemoryPriority.LOW] == 0.7

    def test_core_multiplier_is_highest(self):
        multipliers = list(PRIORITY_MULTIPLIER.values())
        assert PRIORITY_MULTIPLIER[MemoryPriority.CORE] == max(multipliers)


class TestMemoryDefaults:
    def test_defaults_without_optional_fields(self):
        vec = np.zeros(384, dtype=np.float32)
        m = Memory(
            id="default_test",
            type=MemoryType.SEMANTIC,
            content="test defaults",
            vector=vec,
        )
        assert m.importance == 0.5
        assert m.utility_score == 0.0
        assert m.access_count == 0
        assert m.namespace == "default"
        assert m.active is True
        assert m.metadata == {}
        assert m.score == 0.0

    def test_status_defaults_to_active(self):
        vec = np.zeros(384, dtype=np.float32)
        m = Memory(id="s1", type=MemoryType.SEMANTIC, content="test", vector=vec)
        assert m.status == MemoryStatus.ACTIVE

    def test_tier_defaults_to_active(self):
        vec = np.zeros(384, dtype=np.float32)
        m = Memory(id="t1", type=MemoryType.SEMANTIC, content="test", vector=vec)
        assert m.tier == MemoryTier.ACTIVE

    def test_priority_defaults_to_normal(self):
        vec = np.zeros(384, dtype=np.float32)
        m = Memory(id="p1", type=MemoryType.SEMANTIC, content="test", vector=vec)
        assert m.priority == MemoryPriority.NORMAL

    def test_to_dict_has_all_required_keys(self):
        vec = np.zeros(384, dtype=np.float32)
        m = Memory(
            id="dict_test",
            type=MemoryType.DECISION,
            content="I decided to use Redis",
            vector=vec,
            score=0.9,
        )
        d = m.to_dict()
        required_keys = [
            "id", "type", "content", "timestamp", "score", "importance",
            "utility_score", "access_count", "namespace", "active",
            "status", "tier", "priority", "metadata",
        ]
        for key in required_keys:
            assert key in d, f"Missing key: {key}"
        assert d["type"] == "DECISION"
        assert d["tier"] == "ACTIVE"
        assert d["priority"] == "NORMAL"


class TestRetrievalExplanation:
    def test_creation_defaults(self):
        exp = RetrievalExplanation(
            memory_id="abc",
            final_score=0.8,
            vector_score=0.7,
            keyword_score=0.3,
            recency_score=0.9,
            importance_score=0.8,
            frequency_bonus=0.1,
            query="test query",
        )
        assert exp.memory_id == "abc"
        assert exp.final_score == 0.8
        assert exp.mode == "default"
        assert exp.matched_keywords == []

    def test_explain_contains_all_components(self):
        exp = RetrievalExplanation(
            memory_id="xyz",
            final_score=0.75,
            vector_score=0.6,
            keyword_score=0.4,
            recency_score=0.8,
            importance_score=0.7,
            frequency_bonus=0.05,
            query="explain test",
            matched_keywords=["test"],
        )
        text = exp.explain()
        assert "vector" in text.lower()
        assert "keyword" in text.lower()
        assert "recency" in text.lower()
        assert "importance" in text.lower()

    def test_explain_includes_memory_id(self):
        exp = RetrievalExplanation(
            memory_id="my-id-123",
            final_score=0.5,
            vector_score=0.4,
            keyword_score=0.2,
            recency_score=0.6,
            importance_score=0.5,
            frequency_bonus=0.0,
            query="query",
        )
        assert "my-id-123" in exp.explain()
