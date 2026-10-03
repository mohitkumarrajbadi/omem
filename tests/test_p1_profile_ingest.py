"""P1: profile briefing, document ingest, RRF, as_of recall, LangGraph adapters."""

import time

import pytest

from omem import AgentState, OMem
from omem.memory import Profile
from omem.core.retrieval.fusion import rrf_from_score_maps
from omem.ingest.chunker import chunk_text, parse_frontmatter
from omem.integrations.langgraph import OMemCheckpointSaver, OMemStore
from omem.state import StateOS


@pytest.fixture
def hash_mode(monkeypatch):
    monkeypatch.setenv("OMEM_EMBEDDER", "hash")
    monkeypatch.delenv("OMEM_RERANK", raising=False)


def test_profile_after_location_revision(hash_mode):
    agent = AgentState(backend="memory", session_id="p1-profile")
    try:
        agent.remember("User lives in NYC", importance=0.8)
        agent.remember("User moved to SF", importance=0.8)
        agent.set_goal("book a flight to the west coast")
        profile = agent.profile(user_id="alice")
        assert isinstance(profile, Profile)
        values = " ".join(f.value for f in profile.facts).lower()
        attrs = {f.attribute.lower() for f in profile.facts}
        assert "location" in attrs
        assert "sf" in values
        assert "nyc" not in values
        assert profile.goal and "west coast" in profile.goal.lower()
        assert "alice" in profile.text.lower()
        assert profile.fact_count >= 1
    finally:
        agent.close()


def test_remember_document_chunks_and_frontmatter(hash_mode, tmp_path):
    md = tmp_path / "policy.md"
    md.write_text(
        "---\n"
        "title: Retention Policy\n"
        "owner: legal\n"
        "---\n\n"
        "# Overview\n"
        "OMem stores what the caller wrote without an LLM extract.\n\n"
        "# Retention window\n"
        "Episodic rows expire after ninety unique days.\n",
        encoding="utf-8",
    )
    agent = AgentState(backend="memory")
    try:
        result = agent.remember_document(md, max_chars=80, overlap=10)
        assert result.chunk_count >= 2
        assert result.frontmatter.get("title") == "Retention Policy"
        assert len(result.fact_ids) >= 1
        hits = agent.recall("ninety unique days", k=5, project_only=True)
        assert any("ninety unique days" in h.content.lower() for h in hits)
        listed = agent.memory.list()
        facts = [
            m
            for m in listed
            if (m.metadata or {}).get("kind") == "document_fact"
        ]
        assert facts
        titles = [
            m.metadata.get("triplet")
            for m in facts
            if m.metadata.get("triplet")
        ]
        assert any(t[1] == "title" and t[2] == "Retention Policy" for t in titles)
    finally:
        agent.close()


def test_chunker_frontmatter_and_headings():
    text = "---\ntitle: Doc\n---\n\n# A\nhello\n\n# B\nworld\n"
    meta, body = parse_frontmatter(text)
    assert meta["title"] == "Doc"
    chunks = chunk_text(body, max_chars=8, overlap=0, kind="markdown")
    assert len(chunks) >= 2
    joined = " ".join(chunks).lower()
    assert "hello" in joined and "world" in joined


def test_rrf_promotes_keyword_winner():
    vec = {"a": 0.95, "b": 0.90, "c": 0.10}
    kw = {"b": 0.99, "c": 0.50, "a": 0.01}
    scores = rrf_from_score_maps(vec, kw)
    assert scores["b"] > scores["a"]
    assert scores["b"] > scores["c"]


def test_recall_prefers_exact_token_over_cousin(hash_mode):
    m = OMem(backend="memory")
    exact = m.add("Checkout SKU is SKU-998877 for the winter jacket.", importance=0.5)
    m.add("The shopping cart service uses Redis for session state.", importance=0.9)
    hits = m.recall("SKU-998877", k=5)
    assert hits
    assert hits[0].id == exact


def test_as_of_recall_returns_superseded_belief(hash_mode):
    m = OMem(backend="memory")
    id1 = m.add("User lives in NYC", importance=0.8)
    time.sleep(0.05)
    m.add("User moved to SF", importance=0.8)
    old_after = m.get(id1)
    assert old_after is not None
    assert old_after.active is False
    assert old_after.valid_to is not None
    assert old_after.valid_from is not None
    assert old_after.valid_to > old_after.valid_from

    now_hits = m.recall("NYC", k=5)
    assert not any(h.id == id1 for h in now_hits)

    then_hits = m.recall("NYC", k=5, as_of=old_after.valid_to - 1e-6)
    assert any(h.id == id1 for h in then_hits)


def test_langgraph_checkpointer_roundtrip(tmp_path):
    db = str(tmp_path / "lg-state.db")
    config = {"configurable": {"thread_id": "thread-a"}}
    saver = OMemCheckpointSaver(state=StateOS(db_path=db))
    returned = saver.put(
        config,
        {"id": "chk-1", "channel_values": {"n": 7, "msg": "hello"}},
        metadata={"source": "test"},
    )
    assert returned["configurable"]["checkpoint_id"] == "chk-1"

    other = OMemCheckpointSaver(state=StateOS(db_path=db))
    got = other.get(config)
    assert got is not None
    assert got["channel_values"]["n"] == 7
    tup = other.get_tuple(config)
    assert tup["metadata"]["source"] == "test"
    listed = list(other.list(config, limit=5))
    assert len(listed) >= 1


def test_omem_store_put_get_search(hash_mode):
    store = OMemStore(omem=OMem(backend="memory"), namespace="lg-store")
    store.put(("users", "alice"), "prefs", {"theme": "dark"})
    assert store.get(("users", "alice"), "prefs") == {"theme": "dark"}
    hits = store.search(("users", "alice"), "theme dark", limit=3)
    assert hits
    assert hits[0]["key"] == "prefs"
    assert hits[0]["value"]["theme"] == "dark"


def test_rerank_flag_is_noop_without_cross_encoder(hash_mode):
    m = OMem(backend="memory")
    m.add("Alpha token ZZZ-unique-1 sits in the warehouse.", importance=0.6)
    m.add("Unrelated note about weather in Berlin.", importance=0.6)
    a = m.recall("ZZZ-unique-1", k=2, rerank=False)
    b = m.recall("ZZZ-unique-1", k=2, rerank=True)
    assert a and b
    assert a[0].id == b[0].id
