"""Phase 2 tests: multi-objective retrieval, explainability, tier filtering."""


from omem import MemoryLevel, MemoryTier, OMem, RetrievalExplanation
from omem.core.retrieval.ranker import MODE_WEIGHT_PROFILES, weights_for_mode


class TestFusionProfiles:
    def test_mode_profiles_exist(self):
        assert "planning" in MODE_WEIGHT_PROFILES
        assert "coding" in MODE_WEIGHT_PROFILES

    def test_weight_overrides(self):
        w = weights_for_mode("default", {"semantic": 0.5})
        assert w.semantic == 0.5


class TestExplainability:
    def test_inspect_includes_fusion_components(self):
        m = OMem(backend="memory")
        m.add("The team uses Python and FastAPI for backend services")
        exps = m.inspect("Python backend", mode="coding")
        assert exps
        e = exps[0]
        assert hasattr(e, "confidence_score")
        assert hasattr(e, "graph_score")
        assert hasattr(e, "personalization_score")
        text = e.explain()
        assert "confidence" in text.lower()
        assert "graph" in text.lower()

    def test_recall_with_explain_populates_explanations(self):
        m = OMem(backend="memory")
        m.add("User prefers dark mode in the IDE")
        m.recall("dark mode preference", k=3, explain=True)
        exps = m.get_explanations()
        assert isinstance(exps[0], RetrievalExplanation)


class TestTierRetrieval:
    def test_level_working_filter(self):
        m = OMem(backend="memory")
        mid = m.add("Temporary working context note")
        mem = m.get(mid)
        assert mem.level == "working"

        results = m.recall("working context", k=5, level=MemoryLevel.WORKING.value)
        assert all(r.level == "working" for r in results)

    def test_recall_excludes_archive_by_default(self):
        m = OMem(backend="memory")
        mid = m.add("Old note to archive")
        mem = m.get(mid)
        mem.tier = MemoryTier.ARCHIVE
        mem.active = False
        m.brain.kv.set(mid, mem)

        results = m.recall("Old note", k=5)
        assert all(r.id != mid for r in results)

    def test_recall_include_archive(self):
        m = OMem(backend="memory")
        mid = m.add("Archived project decision")
        mem = m.get(mid)
        mem.tier = MemoryTier.ARCHIVE
        mem.active = False
        m.brain.kv.set(mid, mem)

        results = m.recall(
            "Archived project",
            k=5,
            include_archive=True,
            level=MemoryLevel.ARCHIVE.value,
        )
        assert any(r.id == mid for r in results)


class TestFusionTuning:
    def test_set_and_get_fusion_weights(self):
        m = OMem(backend="memory")
        m.set_fusion_weights({"graph": 0.25, "semantic": 0.25})
        weights = m.get_fusion_weights()
        assert weights["graph"] == 0.25

    def test_recall_mode_planning(self):
        m = OMem(backend="memory")
        m.add("Strategic goal: launch MVP by Q3")
        results = m.recall("launch goal", k=3, mode="planning")
        assert len(results) >= 1


class TestOnlineReinforcement:
    def test_recall_boosts_importance(self):
        m = OMem(backend="memory")
        mid = m.add("Repeat access memory about Redis caching")
        before = m.get(mid).importance
        m.recall("Redis caching", k=3)
        after = m.get(mid).importance
        assert after >= before

    def test_entity_centrality(self):
        m = OMem(backend="memory")
        m.add("Service uses Python and FastAPI")
        m.add("API layer built with FastAPI and Redis")
        m.add("Frontend uses React")
        centrality = m.brain.knowledge_graph.entity_centrality("FastAPI")
        assert centrality > 0.0
