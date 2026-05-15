"""End-to-end tests for the OMem public API."""

from omem import OMem, MemoryType, Memory


class TestOMem:
    def setup_method(self):
        self.m = OMem()

    def test_add_returns_id(self):
        mid = self.m.add("Hello world")
        assert isinstance(mid, str)
        assert len(mid) > 0

    def test_add_with_type(self):
        mid = self.m.add("Step 1: do something", mem_type=MemoryType.PROCEDURAL)
        mem = self.m.get(mid)
        assert mem is not None
        assert mem.type == MemoryType.PROCEDURAL

    def test_add_auto_classifies(self):
        mid = self.m.add("Yesterday I visited the park")
        mem = self.m.get(mid)
        assert mem.type == MemoryType.EPISODIC

    def test_rag_returns_list(self):
        self.m.add("The sky is blue")
        self.m.add("Water boils at 100 degrees")
        results = self.m.recall("sky color")
        assert isinstance(results, list)
        assert len(results) > 0
        assert isinstance(results[0], Memory)

    def test_rag_empty(self):
        results = self.m.recall("anything")
        assert results == []

    def test_rag_scores_sorted(self):
        for i in range(10):
            self.m.add(f"Memory number {i} about topic alpha")
        results = self.m.recall("topic alpha", top_k=5)
        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_dedup(self):
        id1 = self.m.add("duplicate content")
        id2 = self.m.add("duplicate content")
        assert id1 == id2
        assert self.m.stats()["total"] == 1

    def test_stats(self):
        self.m.add("Paris is the capital of France")
        self.m.add("I decided to use Go")
        s = self.m.stats()
        assert s["total"] == 2
        assert isinstance(s["types"], dict)
        assert s["graph_edges"] == 0

    def test_link(self):
        id1 = self.m.add("cause event")
        id2 = self.m.add("effect event")
        self.m.link(id1, id2, label="causes")
        assert self.m.stats()["graph_edges"] == 1

    def test_clear(self):
        for i in range(5):
            self.m.add(f"memory {i}")
        assert self.m.stats()["total"] == 5
        self.m.clear()
        assert self.m.stats()["total"] == 0

    def test_all(self):
        self.m.add("one")
        self.m.add("two")
        all_mems = self.m.all()
        assert len(all_mems) == 2

    def test_get_missing(self):
        assert self.m.get("nonexistent") is None

    def test_repr(self):
        r = repr(self.m)
        assert "OMem" in r

    def test_metadata(self):
        mid = self.m.add("test", metadata={"source": "unit_test"})
        mem = self.m.get(mid)
        assert mem.metadata["source"] == "unit_test"
