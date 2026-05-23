"""Tests for omem.types and omem.classify."""

import numpy as np

from omem.classify import auto_classify
from omem.types import Memory, MemoryType


class TestMemoryType:
    def test_all_ten_values(self):
        assert len(MemoryType) == 10

    def test_enum_values(self):
        assert MemoryType.WORKING.value == 0
        assert MemoryType.ACTIVE.value == 6

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

    def test_semantic_fallback(self):
        assert auto_classify("The capital of France is Paris") == MemoryType.SEMANTIC
        assert auto_classify("Python is a programming language") == MemoryType.SEMANTIC
