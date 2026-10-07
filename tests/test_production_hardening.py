"""P0 production-hardening: durable graph/provenance, TMS, usage importance, embedder."""

import numpy as np
import pytest

from omem import AgentState, MemoryStatus, OMem
from omem.core.brain.importance import record_packed, update_importance_from_utility
from omem.core.brain.tms import extract_triplet
from omem.core.retrieval.embeddings import Embedder
from omem.types import Memory, MemoryType


@pytest.fixture
def hash_embedder(monkeypatch):
    monkeypatch.setenv("OMEM_EMBEDDER", "hash")
    return Embedder()


def test_embedder_hash_mode_is_explicit(hash_embedder):
    e = hash_embedder
    vec = e.encode("production database is PostgreSQL")
    assert e.kind == "hash"
    assert e.is_semantic is False
    assert vec.shape == (384,)
    assert np.isfinite(vec).all()


def test_learn_graph_survives_restart(tmp_path):
    db = str(tmp_path / "brain.db")
    a = AgentState(backend="sqlite", db_path=db, session_id="s1")
    try:
        edge_id = a.learn("FastAPI", "uses", "Pydantic")
        assert edge_id
        a.flush()
    finally:
        a.close()

    b = AgentState(backend="sqlite", db_path=db, session_id="s2")
    try:
        sub = b.know_about("FastAPI", depth=1)
        preds = {e.predicate for e in sub.edges}
        sources = {e.source for e in sub.edges}
        targets = {e.target for e in sub.edges}
        assert sub.edge_count >= 1
        assert "uses" in preds
        assert "fastapi" in sources
        assert "pydantic" in targets
    finally:
        b.close()


def test_provenance_survives_restart(tmp_path):
    db = str(tmp_path / "brain.db")
    a = AgentState(backend="sqlite", db_path=db, session_id="prov-1")
    try:
        mid = a.remember("Decision: use PKCE, not HMAC", importance=0.95)
        assert mid
        a.flush()
        before = a.provenance.trace(mid)
        assert len(before.events) >= 1
    finally:
        a.close()

    b = AgentState(backend="sqlite", db_path=db, session_id="prov-2")
    try:
        after = b.provenance.trace(mid)
        assert len(after.events) >= 1
        assert after.events[0].entity_id == mid
        assert after.events[0].operation == "create"
    finally:
        b.close()


def test_location_belief_revision_newer_wins():
    m = OMem(backend="memory")
    id1 = m.add("User lives in NYC", importance=0.8)
    id2 = m.add("User moved to SF", importance=0.8)
    old = m.get(id1)
    new = m.get(id2)
    assert old is not None and new is not None
    assert old.status == MemoryStatus.DEPRECATED
    assert old.active is False
    assert old.superseded_by == id2
    assert old.valid_to is not None
    assert new.status == MemoryStatus.ACTIVE
    assert new.active is True
    assert new.valid_to is None


def test_extract_triplet_location_same_logical_key():
    t1 = extract_triplet("User lives in NYC")
    t2 = extract_triplet("User moved to SF")
    assert t1 is not None and t2 is not None
    assert t1[0] == t2[0] == "user"
    assert t1[1] == t2[1] == "location"
    assert t1[2] != t2[2]


def test_packed_memory_gains_importance_over_unused():
    unused = Memory(
        id="a",
        type=MemoryType.SEMANTIC,
        content="My favorite color is blue",
        vector=np.zeros(8, dtype=np.float32),
        importance=0.85,
        initial_importance=0.85,
    )
    useful = Memory(
        id="b",
        type=MemoryType.DECISION,
        content="Our production database is PostgreSQL",
        vector=np.zeros(8, dtype=np.float32),
        importance=0.5,
        initial_importance=0.5,
    )
    for _ in range(8):
        record_packed(useful)
        useful.retrieved_count += 2
        update_importance_from_utility(useful)
    update_importance_from_utility(unused)
    assert useful.importance > unused.importance
    assert useful.packed_count == 8


def test_unclassified_type_is_low_confidence_hint():
    from omem.core.brain.classify import auto_classify_multi

    scores = auto_classify_multi("zzz qqq www")
    assert scores[0][0] == MemoryType.SEMANTIC
    assert scores[0][1] <= 0.4


def test_concurrent_remember_records_provenance(tmp_path):
    import threading

    db = str(tmp_path / "prov.db")
    agent = AgentState(backend="sqlite", db_path=db, session_id="prov-conc")
    errors: list[str] = []
    ids: list[str] = []
    lock = threading.Lock()

    def worker(wid: int) -> None:
        try:
            mid = agent.remember(f"concurrent-prov-{wid} unique payload", force=True)
            with lock:
                ids.append(mid)
        except Exception as exc:  # noqa: BLE001
            with lock:
                errors.append(str(exc))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)
    try:
        assert errors == [], errors
        assert len(ids) == 8
        for mid in ids:
            chain = agent.provenance.trace(mid)
            assert len(chain.events) >= 1
    finally:
        agent.close()
