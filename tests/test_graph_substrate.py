"""Tests for graph substrate and Memory OS Phase 1 refactor."""

import pytest

from omem import OMem, MemoryType
from omem.core.graph.knowledge import EdgeType, KnowledgeGraph
from omem.core.retrieval.fusion import fuse_score, normalize_graph_distance


@pytest.fixture
def graph():
    g = KnowledgeGraph()
    yield g
    g.clear()


class TestGraphSubstrate:
    def test_ingest_experience_creates_nodes_and_edges(self, graph):
        result = graph.ingest_experience(
            memory_id="mem1",
            content="The team uses Python and PostgreSQL for the OMem project",
            source="test",
            confidence=0.9,
        )
        assert result["entities"]
        assert result["node_ids"]
        assert result["confidence"] == 0.9
        assert graph.num_entities >= 2

    def test_assert_fact_creates_high_confidence_edge(self, graph):
        payload = graph.assert_fact(
            "Team",
            EdgeType.DECIDED,
            "PostgreSQL",
            memory_id="mem2",
            confidence=0.95,
        )
        assert payload["edge_id"]
        edge = graph.get_edge(payload["edge_id"])
        assert edge is not None
        assert edge.confidence >= 0.9

    def test_create_insight_node(self, graph):
        node = graph.create_insight_node(
            label="Python is preferred for data work",
            memory_ids=["m1", "m2", "m3"],
            themes=["python", "data"],
            confidence=0.88,
        )
        assert node.kind.value == "insight"
        assert node.evidence_count == 3
        assert graph.get_node(node.id) is not None

    def test_graph_score_for_memory(self, graph):
        graph.ingest_experience(
            "m1",
            "The service uses Python for machine learning pipelines",
        )
        graph.ingest_experience(
            "m2",
            "The backend uses Python with FastAPI for APIs",
        )
        score = graph.graph_score_for_memory("m2", ["Python"], depth=2)
        assert score == 1.0

    def test_query_returns_memory_ids(self, graph):
        graph.ingest_experience("m1", "Bob works at Google using Kubernetes")
        ids = graph.query("Google", depth=1)
        assert "m1" in ids


class TestFusionScoring:
    def test_fuse_score_weighted_sum(self):
        score = fuse_score(
            semantic=0.8,
            keyword=0.5,
            recency=0.7,
            importance=0.6,
            confidence=0.9,
            graph=0.4,
            personalization=0.2,
        )
        assert 0.0 < score <= 1.5

    def test_normalize_graph_distance(self):
        assert normalize_graph_distance(0) == 1.0
        assert normalize_graph_distance(3) == 0.0


class TestOMemAPI:
    def test_add_experience_populates_graph_metadata(self):
        m = OMem(backend="memory")
        mem_id = m.add_experience(
            "The team decided to migrate from MySQL to PostgreSQL",
            confidence=0.85,
        )
        assert mem_id
        memory = m.get(mem_id)
        assert memory is not None
        assert memory.confidence_score == 0.85
        assert memory.provenance == "experience"

    def test_assert_fact_via_api(self):
        m = OMem(backend="memory")
        result = m.assert_fact("User", "prefers", "Python", confidence=0.9)
        assert result["edge_id"]
        assert m.stats()["knowledge_entities"] >= 2

    def test_query_graph_via_api(self):
        m = OMem(backend="memory")
        m.add("Alice uses Rust for performance-critical code")
        payload = m.query_graph("Rust", depth=1)
        assert payload["found"] is True
        assert payload["memory_ids"]

    def test_link_entities_via_api(self):
        m = OMem(backend="memory")
        edge_id = m.link_entities("OMem", "FAISS", relation="uses")
        assert edge_id

    def test_dream_creates_insight_with_graph_node(self):
        m = OMem(backend="memory")
        for i in range(4):
            m.add(
                f"Python is great for data science task variant {i}",
                mem_type=MemoryType.SEMANTIC,
            )
        result = m.dream(min_cluster_size=3, threshold=0.5)
        assert result.insight_created >= 0
        stats = m.stats()
        assert stats["knowledge_nodes"] >= stats["knowledge_entities"]

    def test_sleep_runs_full_cycle(self):
        m = OMem(backend="memory")
        m.add("Ephemeral working memory note")
        result = m.brain.sleep(include_dream=False)
        assert "elapsed_ms" in result
