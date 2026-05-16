"""Tests for SQLite backend."""

import numpy as np

from omem.backends.sqlite import SQLiteBackend
from omem.types import Memory, MemoryType


def _make_memory(
    mid: str = "m1",
    content: str = "test content",
    namespace: str = "default",
    active: bool = True,
) -> Memory:
    # Use a normalized random vector for realistic similarity computations
    vec = np.random.rand(384).astype(np.float32)
    vec /= np.linalg.norm(vec)
    return Memory(
        id=mid,
        type=MemoryType.SEMANTIC,
        content=content,
        vector=vec,
        timestamp=1000.0,
        score=0.0,
        namespace=namespace,
        active=active,
        metadata={"key": "value"},
    )


class TestSQLiteBackend:
    def setup_method(self):
        self.backend = SQLiteBackend(":memory:")

    def test_save_and_load(self):
        m = _make_memory("abc")
        self.backend.save(m)
        loaded = self.backend.load("abc")
        assert loaded is not None
        assert loaded.id == "abc"
        assert loaded.content == "test content"
        assert loaded.metadata == {"key": "value"}

    def test_load_missing(self):
        assert self.backend.load("nonexistent") is None

    def test_count(self):
        assert self.backend.count() == 0
        self.backend.save(_make_memory("a"))
        self.backend.save(_make_memory("b", "other"))
        assert self.backend.count() == 2

    def test_search(self):
        self.backend.save(_make_memory("a", "the quick brown fox"))
        self.backend.save(_make_memory("b", "lazy dog jumps"))
        results = self.backend.search("brown")
        assert len(results) == 1
        assert results[0].content == "the quick brown fox"

    def test_delete(self):
        self.backend.save(_make_memory("d"))
        assert self.backend.delete("d") is True
        assert self.backend.delete("d") is False
        assert self.backend.count() == 0

    def test_clear(self):
        for i in range(5):
            self.backend.save(_make_memory(f"m{i}"))
        assert self.backend.count() == 5
        self.backend.clear()
        assert self.backend.count() == 0

    def test_all(self):
        self.backend.save(_make_memory("x"))
        self.backend.save(_make_memory("y", "another"))
        all_mems = self.backend.all()
        assert len(all_mems) == 2
        ids = {m.id for m in all_mems}
        assert ids == {"x", "y"}

    def test_upsert(self):
        self.backend.save(_make_memory("u", "version 1"))
        self.backend.save(_make_memory("u", "version 2"))
        assert self.backend.count() == 1
        loaded = self.backend.load("u")
        assert loaded.content == "version 2"

    def test_vector_roundtrip(self):
        m = _make_memory("v")
        self.backend.save(m)
        loaded = self.backend.load("v")
        np.testing.assert_array_almost_equal(loaded.vector, m.vector, decimal=5)

    def test_namespace_stored_and_retrieved(self):
        m = _make_memory("ns1", namespace="my-ns")
        self.backend.save(m)
        loaded = self.backend.load("ns1")
        assert loaded is not None
        assert loaded.namespace == "my-ns"

    def test_active_flag_stored_and_retrieved(self):
        m = _make_memory("act1", active=False)
        self.backend.save(m)
        loaded = self.backend.load("act1")
        assert loaded is not None
        assert loaded.active is False

    def test_save_multiple_then_all(self):
        for i in range(3):
            self.backend.save(_make_memory(f"multi{i}", f"content {i}"))
        all_mems = self.backend.all()
        assert len(all_mems) == 3
        contents = {m.content for m in all_mems}
        assert contents == {"content 0", "content 1", "content 2"}

    def test_search_no_results(self):
        self.backend.save(_make_memory("s1", "completely unrelated"))
        results = self.backend.search("xyznomatch12345")
        assert results == []
