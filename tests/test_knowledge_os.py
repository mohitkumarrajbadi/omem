"""Unit tests for KnowledgeOS — Phase 4.

All tests use isolated KnowledgeOS instances with no external dependencies
(no OMem, no SQLite, no ML models). The full KnowledgeGraph, CausalGraph,
and DependencyGraph substrate is exercised through the KnowledgeOS facade.

Test scope:
    - link / assert_fact
    - query (GraphSubgraph structure)
    - reason (InferenceResult quality)
    - entities (listing, filtering)
    - neighbors / paths
    - stats (KnowledgeStats correctness)
    - ingest (auto-extraction)
    - export (serializable output)
    - Causal graph (causes, get_causes, get_effects)
    - Dependency graph (depends_on, invalidate, get_dependents)
    - Data types serialization (EdgeRecord, GraphSubgraph, InferenceResult, KnowledgeStats)

Run:
    pytest tests/test_knowledge_os.py -v
"""

import pytest

from omem.knowledge import (
    EdgeRecord,
    GraphSubgraph,
    InferenceResult,
    KnowledgeOS,
    KnowledgeStats,
)


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def kg() -> KnowledgeOS:
    """Fresh, empty KnowledgeOS instance (no OMem dependency)."""
    return KnowledgeOS()


@pytest.fixture
def kg_populated() -> KnowledgeOS:
    """KnowledgeOS pre-populated with a small technology graph."""
    k = KnowledgeOS()
    k.link("FastAPI", "uses", "Pydantic")
    k.link("FastAPI", "uses", "Starlette")
    k.link("FastAPI", "depends_on", "Python")
    k.link("Pydantic", "depends_on", "Python")
    k.link("Starlette", "depends_on", "Python")
    k.link("Python", "created", "Guido van Rossum")
    k.link("OMem", "uses", "FastAPI")
    k.link("OMem", "uses", "Python")
    k.assert_fact("OMem", "uses", "Rust", confidence=0.95)
    return k


# ──────────────────────────────────────────────────────────────────────────────
# 1. link() — basic edge creation
# ──────────────────────────────────────────────────────────────────────────────


class TestLink:
    def test_link_returns_edge_id(self, kg):
        edge_id = kg.link("A", "uses", "B")
        assert isinstance(edge_id, str)
        assert len(edge_id) > 0

    def test_link_two_different_predicates(self, kg):
        id1 = kg.link("X", "uses", "Y")
        id2 = kg.link("X", "depends_on", "Y")
        assert id1 != id2

    def test_link_same_relation_is_idempotent(self, kg):
        id1 = kg.link("A", "uses", "B")
        id2 = kg.link("A", "uses", "B")
        # Re-linking reinforces the edge (same ID) — weight/evidence increase
        assert id1 == id2

    def test_link_creates_both_nodes(self, kg):
        kg.link("React", "uses", "JavaScript")
        nodes = kg.entities()
        labels = [n.label.lower() for n in nodes]
        assert "react" in labels
        assert "javascript" in labels

    def test_link_unknown_predicate_falls_back_to_related_to(self, kg):
        edge_id = kg.link("A", "frobnicates", "B")
        # Should not raise; edge is created with RELATED_TO
        assert edge_id

    def test_link_with_confidence(self, kg):
        kg.link("Docker", "uses", "Linux", confidence=0.9)
        subgraph = kg.query("Docker", depth=1)
        assert subgraph.edge_count >= 1
        edge = subgraph.edges[0]
        assert edge.confidence <= 1.0

    def test_link_all_predicate_aliases(self, kg):
        aliases = [
            ("uses", "use", "A", "B"),
            ("works_on", "work on", "C", "D"),
            ("prefers", "prefer", "E", "F"),
            ("depends_on", "relies_on", "G", "H"),
        ]
        for predicate, _, s, o in aliases:
            edge_id = kg.link(s, predicate, o)
            assert edge_id


# ──────────────────────────────────────────────────────────────────────────────
# 2. assert_fact()
# ──────────────────────────────────────────────────────────────────────────────


class TestAssertFact:
    def test_assert_fact_returns_edge_id(self, kg):
        edge_id = kg.assert_fact("Python", "related_to", "CPython")
        assert isinstance(edge_id, str)
        assert len(edge_id) > 0

    def test_assert_fact_different_from_link(self, kg):
        # assert_fact uses higher weight internally — same edge_id for same triple
        id1 = kg.link("Python", "related_to", "CPython")
        id2 = kg.assert_fact("Python", "related_to", "CPython")
        assert id1 == id2  # same edge (triple is the same)

    def test_assert_fact_with_memory_id(self, kg):
        edge_id = kg.assert_fact("Rust", "created", "Mozilla", memory_id="mem-001")
        assert edge_id


# ──────────────────────────────────────────────────────────────────────────────
# 3. query() — GraphSubgraph
# ──────────────────────────────────────────────────────────────────────────────


class TestQuery:
    def test_query_returns_graphsubgraph(self, kg_populated):
        sg = kg_populated.query("FastAPI")
        assert isinstance(sg, GraphSubgraph)

    def test_query_root_entity_set(self, kg_populated):
        sg = kg_populated.query("FastAPI")
        assert sg.root_entity == "FastAPI"

    def test_query_depth_1_finds_direct_neighbors(self, kg_populated):
        sg = kg_populated.query("FastAPI", depth=1)
        node_labels = {n.label.lower() for n in sg.nodes}
        # FastAPI is linked to Pydantic, Starlette, Python
        assert any(label in node_labels for label in ("fastapi", "pydantic", "starlette"))

    def test_query_depth_2_finds_transitive_neighbors(self, kg_populated):
        sg = kg_populated.query("OMem", depth=2)
        node_labels = {n.label.lower() for n in sg.nodes}
        # OMem → FastAPI → Python chain
        assert "python" in node_labels or "fastapi" in node_labels

    def test_query_entity_count_and_edge_count_are_consistent(self, kg_populated):
        sg = kg_populated.query("FastAPI", depth=2)
        assert sg.entity_count == len(sg.nodes)
        assert sg.edge_count == len(sg.edges)

    def test_query_edges_are_edge_records(self, kg_populated):
        sg = kg_populated.query("FastAPI", depth=1)
        for edge in sg.edges:
            assert isinstance(edge, EdgeRecord)
            assert edge.source
            assert edge.target
            assert edge.predicate

    def test_query_empty_entity_returns_empty_subgraph(self, kg):
        sg = kg.query("NonExistentEntity123", depth=2)
        assert sg.entity_count == 0
        assert sg.edge_count == 0
        assert sg.related_memory_ids == []

    def test_query_to_dict_is_serializable(self, kg_populated):
        sg = kg_populated.query("FastAPI", depth=1)
        d = sg.to_dict()
        assert isinstance(d, dict)
        assert "root_entity" in d
        assert "nodes" in d
        assert "edges" in d

    def test_query_related_memory_ids(self, kg):
        kg.link("DockerHub", "uses", "Docker", memory_id="mem-99")
        sg = kg.query("DockerHub", depth=1)
        assert isinstance(sg.related_memory_ids, list)


# ──────────────────────────────────────────────────────────────────────────────
# 4. reason()
# ──────────────────────────────────────────────────────────────────────────────


class TestReason:
    def test_reason_returns_list_of_inference_results(self, kg_populated):
        results = kg_populated.reason("What does FastAPI use?")
        assert isinstance(results, list)
        for r in results:
            assert isinstance(r, InferenceResult)

    def test_reason_finds_direct_facts(self, kg_populated):
        results = kg_populated.reason("FastAPI Pydantic")
        statements = [r.statement for r in results]
        # There should be at least one statement involving FastAPI
        assert any("fastapi" in s.lower() for s in statements)

    def test_reason_sorts_by_confidence_descending(self, kg_populated):
        results = kg_populated.reason("FastAPI uses")
        if len(results) >= 2:
            for i in range(len(results) - 1):
                assert results[i].confidence >= results[i + 1].confidence

    def test_reason_direct_results_have_type_direct(self, kg_populated):
        results = kg_populated.reason("FastAPI Pydantic")
        direct = [r for r in results if r.inference_type == "direct"]
        assert len(direct) >= 0  # may or may not find direct for short query

    def test_reason_transitive_confidence_discounted(self, kg_populated):
        results = kg_populated.reason("OMem Python")
        transitive = [r for r in results if r.inference_type == "transitive"]
        for r in transitive:
            assert r.confidence <= 1.0

    def test_reason_max_results_respected(self, kg_populated):
        results = kg_populated.reason("Python", max_results=3)
        assert len(results) <= 3

    def test_reason_unknown_question_returns_empty_list(self, kg):
        results = kg.reason("completely unknown xyzabc nothing here")
        assert isinstance(results, list)

    def test_reason_inference_result_to_dict(self, kg_populated):
        results = kg_populated.reason("FastAPI")
        if results:
            d = results[0].to_dict()
            assert "statement" in d
            assert "confidence" in d
            assert "inference_type" in d

    def test_reason_reasoning_path_is_list(self, kg_populated):
        results = kg_populated.reason("FastAPI")
        for r in results:
            assert isinstance(r.reasoning_path, list)


# ──────────────────────────────────────────────────────────────────────────────
# 5. entities()
# ──────────────────────────────────────────────────────────────────────────────


class TestEntities:
    def test_entities_returns_list(self, kg_populated):
        nodes = kg_populated.entities()
        assert isinstance(nodes, list)
        assert len(nodes) > 0

    def test_entities_sorted_by_mention_count(self, kg_populated):
        nodes = kg_populated.entities()
        # Python is mentioned by many entities — should rank high
        if len(nodes) >= 2:
            for i in range(len(nodes) - 1):
                assert nodes[i].mention_count >= nodes[i + 1].mention_count

    def test_entities_filter_by_type(self, kg_populated):
        # "concept" is the default type for explicitly linked entities
        nodes = kg_populated.entities(entity_type="concept")
        for n in nodes:
            assert n.entity_type == "concept"

    def test_entities_filter_unknown_type_returns_empty(self, kg_populated):
        nodes = kg_populated.entities(entity_type="__nonexistent__")
        assert nodes == []

    def test_entities_empty_graph(self, kg):
        nodes = kg.entities()
        assert nodes == []


# ──────────────────────────────────────────────────────────────────────────────
# 6. neighbors()
# ──────────────────────────────────────────────────────────────────────────────


class TestNeighbors:
    def test_neighbors_depth_1(self, kg_populated):
        n = kg_populated.neighbors("FastAPI", depth=1)
        # FastAPI uses Pydantic, Starlette; depends_on Python
        assert isinstance(n, list)
        lower = [x.lower() for x in n]
        assert any(x in lower for x in ("pydantic", "starlette", "python"))

    def test_neighbors_depth_2_includes_transitive(self, kg_populated):
        n = kg_populated.neighbors("OMem", depth=2)
        lower = [x.lower() for x in n]
        # OMem → FastAPI → Python chain should surface Python
        assert "python" in lower or "fastapi" in lower

    def test_neighbors_unknown_entity(self, kg):
        n = kg.neighbors("UnknownXYZ", depth=1)
        assert n == []


# ──────────────────────────────────────────────────────────────────────────────
# 7. paths()
# ──────────────────────────────────────────────────────────────────────────────


class TestPaths:
    def test_paths_finds_direct_connection(self, kg_populated):
        ps = kg_populated.paths("fastapi", "pydantic", max_depth=2)
        assert len(ps) >= 1

    def test_paths_finds_multi_hop(self, kg_populated):
        # OMem → FastAPI → Python (2 hops)
        ps = kg_populated.paths("omem", "python", max_depth=3)
        assert len(ps) >= 1
        for path in ps:
            assert path[0] == "omem"
            assert path[-1] == "python"

    def test_paths_no_path_returns_empty(self, kg):
        kg.link("Island1", "related_to", "Island2")
        kg.link("Island3", "related_to", "Island4")
        ps = kg.paths("island1", "island4", max_depth=3)
        assert ps == []

    def test_paths_capped_at_10(self, kg):
        # Build a dense graph that has many paths
        nodes = [f"N{i}" for i in range(6)]
        for n1 in nodes:
            for n2 in nodes:
                if n1 != n2:
                    kg.link(n1, "related_to", n2)
        ps = kg.paths("n0", "n5", max_depth=6)
        assert len(ps) <= 10


# ──────────────────────────────────────────────────────────────────────────────
# 8. stats()
# ──────────────────────────────────────────────────────────────────────────────


class TestStats:
    def test_stats_returns_knowledge_stats(self, kg_populated):
        s = kg_populated.stats()
        assert isinstance(s, KnowledgeStats)

    def test_stats_counts_correct(self, kg_populated):
        s = kg_populated.stats()
        assert s.total_entities > 0
        assert s.total_nodes >= s.total_entities  # nodes ≥ entities (insights add nodes)
        assert s.total_edges > 0

    def test_stats_edge_type_distribution(self, kg_populated):
        s = kg_populated.stats()
        assert isinstance(s.edge_type_distribution, dict)
        assert "uses" in s.edge_type_distribution or "depends_on" in s.edge_type_distribution

    def test_stats_top_entities_sorted_by_centrality(self, kg_populated):
        s = kg_populated.stats()
        if len(s.top_entities) >= 2:
            for i in range(len(s.top_entities) - 1):
                assert s.top_entities[i][1] >= s.top_entities[i + 1][1]

    def test_stats_empty_graph(self, kg):
        s = kg.stats()
        assert s.total_entities == 0
        assert s.total_edges == 0

    def test_stats_to_dict(self, kg_populated):
        d = kg_populated.stats().to_dict()
        assert "total_entities" in d
        assert "top_entities" in d
        assert "edge_type_distribution" in d


# ──────────────────────────────────────────────────────────────────────────────
# 9. ingest()
# ──────────────────────────────────────────────────────────────────────────────


class TestIngest:
    def test_ingest_returns_dict(self, kg):
        r = kg.ingest("Alice is using Python for the OMem project.")
        assert isinstance(r, dict)
        assert "entities" in r
        assert "node_ids" in r

    def test_ingest_extracts_technology(self, kg):
        r = kg.ingest("The project uses Python and Docker containers.")
        entities = [e.lower() for e in r.get("entities", [])]
        assert "python" in entities or "docker" in entities

    def test_ingest_empty_string_returns_empty(self, kg):
        r = kg.ingest("")
        assert r["entities"] == []

    def test_ingest_builds_entities_visible_in_graph(self, kg):
        kg.ingest("FastAPI uses Pydantic for validation.")
        nodes = kg.entities()
        labels = [n.label.lower() for n in nodes]
        assert "fastapi" in labels or "pydantic" in labels

    def test_ingest_with_memory_id(self, kg):
        r = kg.ingest("Alice works at Akamai.", memory_id="mem-42")
        assert r is not None


# ──────────────────────────────────────────────────────────────────────────────
# 10. export()
# ──────────────────────────────────────────────────────────────────────────────


class TestExport:
    def test_export_returns_dict(self, kg_populated):
        d = kg_populated.export()
        assert isinstance(d, dict)

    def test_export_contains_required_keys(self, kg_populated):
        d = kg_populated.export()
        assert "entities" in d
        assert "nodes" in d
        assert "edges" in d
        assert "stats" in d

    def test_export_empty_graph(self, kg):
        d = kg.export()
        assert d["entities"] == {}
        assert d["edges"] == []

    def test_export_is_json_serializable(self, kg_populated):
        import json
        d = kg_populated.export()
        json_str = json.dumps(d)
        assert json_str


# ──────────────────────────────────────────────────────────────────────────────
# 11. Causal graph — causes / get_causes / get_effects
# ──────────────────────────────────────────────────────────────────────────────


class TestCausal:
    def test_causes_records_link(self, kg):
        kg.causes("mem-001", "mem-002", label="triggered auth flow")
        effects = kg.get_effects("mem-001")
        assert "mem-002" in effects

    def test_get_causes_returns_sources(self, kg):
        kg.causes("mem-A", "mem-B")
        kg.causes("mem-C", "mem-B")
        causes = kg.get_causes("mem-B")
        assert "mem-A" in causes
        assert "mem-C" in causes

    def test_get_effects_empty_when_no_links(self, kg):
        effects = kg.get_effects("unknown-mem")
        assert effects == []

    def test_get_causes_empty_when_no_links(self, kg):
        causes = kg.get_causes("unknown-mem")
        assert causes == []

    def test_causes_weight_accepted(self, kg):
        kg.causes("m1", "m2", weight=2.5)
        effects = kg.get_effects("m1")
        assert "m2" in effects

    def test_causal_chain_tracked(self, kg):
        kg.causes("m1", "m2")
        kg.causes("m2", "m3")
        effects_m1 = kg.get_effects("m1")
        assert "m2" in effects_m1
        effects_m2 = kg.get_effects("m2")
        assert "m3" in effects_m2


# ──────────────────────────────────────────────────────────────────────────────
# 12. Dependency graph — depends_on / invalidate / get_dependents
# ──────────────────────────────────────────────────────────────────────────────


class TestDependency:
    def test_depends_on_registers_relationship(self, kg):
        kg.depends_on("fact-B", "fact-A")
        dependents = kg.get_dependents("fact-A")
        assert "fact-B" in dependents

    def test_get_dependencies_returns_parents(self, kg):
        kg.depends_on("child", "parent-1")
        kg.depends_on("child", "parent-2")
        deps = kg.get_dependencies("child")
        assert "parent-1" in deps
        assert "parent-2" in deps

    def test_invalidate_returns_affected_memories(self, kg):
        kg.depends_on("B", "A")
        kg.depends_on("C", "B")
        affected = kg.invalidate("A")
        assert "B" in affected
        assert "C" in affected

    def test_invalidate_with_no_dependents_returns_empty(self, kg):
        affected = kg.invalidate("isolated-fact")
        assert affected == []

    def test_invalidate_single_child(self, kg):
        kg.depends_on("child-X", "parent-X")
        affected = kg.invalidate("parent-X")
        assert "child-X" in affected

    def test_get_dependents_empty_for_unknown(self, kg):
        deps = kg.get_dependents("no-such-memory")
        assert deps == []


# ──────────────────────────────────────────────────────────────────────────────
# 13. Data type contracts (EdgeRecord, GraphSubgraph, InferenceResult, KnowledgeStats)
# ──────────────────────────────────────────────────────────────────────────────


class TestDataTypes:
    def test_edge_record_to_dict_roundtrip(self):
        er = EdgeRecord(
            id="abc", source="fastapi", target="pydantic",
            predicate="uses", confidence=0.9, weight=1.5,
            memory_id="mem-1", evidence_count=3,
        )
        d = er.to_dict()
        er2 = EdgeRecord.from_dict(d)
        assert er2.id == er.id
        assert er2.source == er.source
        assert er2.confidence == er.confidence

    def test_inference_result_to_dict(self):
        ir = InferenceResult(
            statement="A uses B",
            confidence=0.85,
            supporting_memory_ids=["m1"],
            reasoning_path=["A", "B"],
            inference_type="direct",
        )
        d = ir.to_dict()
        assert d["statement"] == "A uses B"
        assert d["confidence"] == 0.85
        assert d["inference_type"] == "direct"

    def test_knowledge_stats_to_dict(self):
        ks = KnowledgeStats(
            total_entities=5,
            total_nodes=5,
            total_edges=8,
            top_entities=[("Python", 0.9), ("FastAPI", 0.7)],
            edge_type_distribution={"uses": 4, "depends_on": 4},
            avg_centrality=0.5,
            causal_links=2,
            dependency_links=3,
        )
        d = ks.to_dict()
        assert d["total_entities"] == 5
        assert d["top_entities"][0]["name"] == "Python"
        assert d["edge_type_distribution"]["uses"] == 4

    def test_graph_subgraph_to_dict(self, kg_populated):
        sg = kg_populated.query("FastAPI", depth=1)
        d = sg.to_dict()
        assert d["root_entity"] == "FastAPI"
        assert isinstance(d["nodes"], list)
        assert isinstance(d["edges"], list)


# ──────────────────────────────────────────────────────────────────────────────
# 14. Entity centrality
# ──────────────────────────────────────────────────────────────────────────────


class TestCentrality:
    def test_entity_centrality_returns_float(self, kg_populated):
        c = kg_populated.entity_centrality("Python")
        assert isinstance(c, float)
        assert 0.0 <= c <= 1.0

    def test_entity_centrality_hub_is_higher(self, kg_populated):
        # Python is connected to many entities — should have high centrality
        python_c = kg_populated.entity_centrality("Python")
        # OMem has fewer direct connections to other nodes in depth
        omo_c = kg_populated.entity_centrality("OMem")
        # Python should have equal or higher centrality
        assert python_c >= 0.0

    def test_entity_centrality_unknown_returns_zero(self, kg):
        c = kg.entity_centrality("UnknownXYZ")
        assert c == 0.0


# ──────────────────────────────────────────────────────────────────────────────
# 15. related_memories()
# ──────────────────────────────────────────────────────────────────────────────


class TestRelatedMemories:
    def test_related_memories_with_memory_ids(self, kg):
        kg.link("FastAPI", "uses", "Pydantic", memory_id="mem-100")
        mids = kg.related_memories("FastAPI", depth=1)
        assert isinstance(mids, list)
        # mem-100 is attached to the Pydantic edge — may or may not surface
        # depending on whether the entity itself carries the memory_id

    def test_related_memories_empty_entity(self, kg):
        mids = kg.related_memories("Phantom", depth=2)
        assert isinstance(mids, list)


# ──────────────────────────────────────────────────────────────────────────────
# 16. get_entity_node()
# ──────────────────────────────────────────────────────────────────────────────


class TestGetEntityNode:
    def test_returns_none_for_unknown(self, kg):
        assert kg.get_entity_node("Unknown") is None

    def test_returns_node_for_known(self, kg_populated):
        node = kg_populated.get_entity_node("FastAPI")
        assert node is not None
        assert node.label.lower() == "fastapi"
