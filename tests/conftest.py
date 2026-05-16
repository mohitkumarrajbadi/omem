import os
import shutil
import tempfile

import pytest

from omem import MemoryType, OMem


@pytest.fixture(autouse=True)
def isolated_omem_db(monkeypatch):
    """Ensure every test gets a fresh, isolated database if it uses default SQLite."""
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "brain.db")
    audit_path = os.path.join(temp_dir, "audit.db")

    original_expanduser = os.path.expanduser

    def mock_expanduser(path):
        if path == "~/.omem/brain.db":
            return db_path
        if path == "~/.omem/audit.db":
            return audit_path
        return original_expanduser(path)

    monkeypatch.setattr(os.path, "expanduser", mock_expanduser)

    yield

    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def mem():
    """Fresh in-memory OMem instance — fast, isolated, no disk I/O."""
    return OMem(backend="memory")


@pytest.fixture
def mem_with_data():
    """In-memory OMem pre-populated with diverse memories for retrieval tests."""
    m = OMem(backend="memory")
    m.add("My name is Alice and I work on AI systems", importance=0.9)
    m.add("Python is a high-level programming language", importance=0.6)
    m.add("Yesterday I deployed the new API service", mem_type=MemoryType.EPISODIC)
    m.add(
        "Step 1: clone the repo. Step 2: install dependencies.",
        mem_type=MemoryType.PROCEDURAL,
    )
    m.add("I decided to use FastAPI for the backend", mem_type=MemoryType.DECISION)
    m.add(
        "The server crashed because of a memory leak", mem_type=MemoryType.CAUSAL
    )
    return m
