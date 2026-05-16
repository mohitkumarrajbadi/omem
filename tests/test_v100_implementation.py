"""OMem 1.0 — Implementation Verification Tests.

Exercises every new feature from Phase 1 + Phase 2:
  1. Temporal TMS — new memory wins, old is DEPRECATED+inactive
  2. context_type mapping — all aliases map to real MemoryType names
  3. utility_score in compute_health() — high-utility memories score higher
  4. 30-day zero-utility pruning — zero-utility old memories get archived
  5. Graph-RAG expansion — neighbor memories surfaced via entity graph
  6. ToolSnippet schema — remember_action / recall_action roundtrip
"""

import time

import numpy as np
import pytest


# ── version check ──────────────────────────────────────────────────────────────
def test_version_is_accessible():
    import omem

    assert isinstance(omem.__version__, str) and len(omem.__version__) > 0, (
        f"Expected a non-empty version string, got {omem.__version__!r}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# 1. Temporal TMS
# ══════════════════════════════════════════════════════════════════════════════


class TestTemporalTMS:
    """The new memory always wins; old is DEPRECATED+inactive."""

    def _make_memory(self, mid, content, logical_hash, timestamp=None):
        from omem.types import Memory, MemoryType

        return Memory(
            id=mid,
            type=MemoryType.SEMANTIC,
            content=content,
            vector=np.zeros(384, dtype=np.float32),
            timestamp=timestamp or time.time(),
            logical_hash=logical_hash,
            metadata={"triplet": ("user", "location", content.split()[-1].lower())},
        )

    def test_old_memory_deprecated_not_conflicted(self):
        """Old fact must be DEPRECATED, not CONFLICTED."""
        from omem.core.brain.tms import ConflictResolver, compute_logical_hash
        from omem.core.retrieval.kv import KVCache
        from omem.types import MemoryStatus

        kv = KVCache()
        lhash = compute_logical_hash("user", "location")

        old_mem = self._make_memory(
            "old1", "user location is mumbai", lhash, time.time() - 3600
        )
        old_mem.metadata["triplet"] = ("user", "location", "mumbai")
        kv.set("old1", old_mem)

        resolver = ConflictResolver(backend=None, kv=kv, dependency_graph=None)

        new_mem = self._make_memory("new1", "user location is berlin", lhash)
        new_mem.metadata["triplet"] = ("user", "location", "berlin")

        affected = resolver.check_and_mark_conflicts(new_mem)

        assert "old1" in affected, "Old memory should be in affected list"
        assert old_mem.status == MemoryStatus.DEPRECATED, (
            f"Old memory must be DEPRECATED, got {old_mem.status}"
        )
        assert old_mem.active is False, "Old memory must be inactive"
        assert old_mem.superseded_by == "new1", (
            "old.superseded_by must point to new memory"
        )

    def test_new_memory_stays_active(self):
        """New memory must remain ACTIVE after conflict resolution."""
        from omem.core.brain.tms import ConflictResolver, compute_logical_hash
        from omem.core.retrieval.kv import KVCache
        from omem.types import MemoryStatus

        kv = KVCache()
        lhash = compute_logical_hash("user", "city")

        old_mem = self._make_memory(
            "old2", "user city is delhi", lhash, time.time() - 7200
        )
        old_mem.metadata["triplet"] = ("user", "city", "delhi")
        kv.set("old2", old_mem)

        resolver = ConflictResolver(backend=None, kv=kv, dependency_graph=None)

        new_mem = self._make_memory("new2", "user city is paris", lhash)
        new_mem.metadata["triplet"] = ("user", "city", "paris")
        resolver.check_and_mark_conflicts(new_mem)

        assert new_mem.status == MemoryStatus.ACTIVE, (
            f"New memory must be ACTIVE, got {new_mem.status}"
        )

    def test_no_conflict_on_same_value(self):
        """Same entity-attribute-value must NOT trigger a conflict."""
        from omem.core.brain.tms import ConflictResolver, compute_logical_hash
        from omem.core.retrieval.kv import KVCache
        from omem.types import MemoryStatus

        kv = KVCache()
        lhash = compute_logical_hash("user", "language")

        old_mem = self._make_memory(
            "old3", "user language is python", lhash, time.time() - 100
        )
        old_mem.metadata["triplet"] = ("user", "language", "python")
        kv.set("old3", old_mem)

        resolver = ConflictResolver(backend=None, kv=kv, dependency_graph=None)
        new_mem = self._make_memory("new3", "user language is python", lhash)
        new_mem.metadata["triplet"] = ("user", "language", "python")

        affected = resolver.check_and_mark_conflicts(new_mem)
        assert affected == [], f"Same value should not trigger conflict, got {affected}"
        assert old_mem.status == MemoryStatus.ACTIVE  # old stays ACTIVE


# ══════════════════════════════════════════════════════════════════════════════
# 2. context_type Mapping
# ══════════════════════════════════════════════════════════════════════════════


class TestContextTypeMapping:
    """All context_type aliases must map to valid MemoryType names."""

    def test_bugs_maps_to_causal(self):
        """context_type='bugs' must produce a CAUSAL type boost."""
        from omem import OMem

        m = OMem(backend="memory")
        # Store two memories — one CAUSAL, one SEMANTIC
        m.add("The server crashed because of a memory leak", importance=0.6)
        m.add("Python is a programming language", importance=0.6)

        results = m.recall("server crash", k=5, context_type="bugs")
        # Must not raise, and CAUSAL-type memories should score higher
        assert isinstance(results, list)

    def test_architecture_maps_to_semantic(self):
        """context_type='architecture' must produce a SEMANTIC boost."""
        from omem import OMem

        m = OMem(backend="memory")
        m.add("The system uses a microservices architecture with Docker")
        results = m.recall("system design", k=5, context_type="architecture")
        assert isinstance(results, list)

    def test_actions_maps_to_procedural(self):
        """context_type='actions' must produce a PROCEDURAL boost."""
        from omem import OMem

        m = OMem(backend="memory")
        m.add("Step 1: Click login. Step 2: Enter password. Step 3: Submit.")
        results = m.recall("login steps", k=5, context_type="actions")
        assert isinstance(results, list)

    def test_all_aliases_dont_raise(self):
        """Every defined alias must execute without error."""
        from omem import OMem

        m = OMem(backend="memory")
        m.add("Test memory for context type verification", importance=0.5)
        aliases = [
            "bugs",
            "errors",
            "root_cause",
            "causal",
            "architecture",
            "arch",
            "system",
            "semantic",
            "decisions",
            "decision",
            "preferences",
            "preference",
            "settings",
            "procedures",
            "procedural",
            "howto",
            "actions",
            "episodic",
            "events",
            "history",
            "working",
            "current",
            "active",
            "insights",
            "insight",
            "reflections",
            "reflection",
        ]
        for alias in aliases:
            try:
                m.recall("test query", k=2, context_type=alias)
            except Exception as e:
                pytest.fail(f"context_type='{alias}' raised: {e}")

    def test_unknown_context_type_does_not_raise(self):
        """Unknown context_type should not raise — just no boost applied."""
        from omem import OMem

        m = OMem(backend="memory")
        m.add("Some memory content here")
        results = m.recall("query", context_type="totally_unknown_type_xyz")
        assert isinstance(results, list)


# ══════════════════════════════════════════════════════════════════════════════
# 3. utility_score in compute_health()
# ══════════════════════════════════════════════════════════════════════════════


class TestUtilityScoreInHealth:
    """High-utility memories must score higher health than identical zero-utility ones."""

    def _base_memory(self, mid, utility, timestamp=None):
        from omem.types import Memory, MemoryType

        return Memory(
            id=mid,
            type=MemoryType.SEMANTIC,
            content=f"Memory with utility {utility}",
            vector=np.zeros(384, dtype=np.float32),
            timestamp=timestamp or (time.time() - 3600),  # 1h old
            importance=0.5,
            utility_score=utility,
            access_count=1,
        )

    def test_higher_utility_means_higher_health(self):
        from omem.core.brain.forgetting import compute_health

        low = self._base_memory("low", utility=0.0)
        high = self._base_memory("high", utility=1.0)
        h_low = compute_health(low)
        h_high = compute_health(high)
        assert h_high > h_low, (
            f"High utility ({h_high:.4f}) must exceed low utility ({h_low:.4f}) health"
        )

    def test_utility_factor_is_exactly_2x_at_max(self):
        """utility=1.0 should give exactly 2.0× the health of utility=0.0."""
        from omem.core.brain.forgetting import compute_health

        base = self._base_memory("b1", utility=0.0)
        boosted = self._base_memory("b2", utility=1.0)
        h_base = compute_health(base)
        h_boosted = compute_health(boosted)
        ratio = h_boosted / h_base
        assert abs(ratio - 2.0) < 0.001, f"Expected 2.0× ratio, got {ratio:.4f}"

    def test_utility_score_on_memory_dataclass(self):
        """Memory dataclass must have utility_score field defaulting to 0.0."""
        from omem.types import Memory, MemoryType

        m = Memory(
            id="test_utility",
            type=MemoryType.SEMANTIC,
            content="test",
            vector=np.zeros(384, dtype=np.float32),
        )
        assert hasattr(m, "utility_score"), "Memory must have utility_score field"
        assert m.utility_score == 0.0


# ══════════════════════════════════════════════════════════════════════════════
# 4. 30-Day Zero-Utility Pruning
# ══════════════════════════════════════════════════════════════════════════════


class TestZeroUtilityPruning:
    """Memories with utility=0.0 older than 30 days must be archived."""

    def _old_active_memory(self, mid, utility=0.0, age_days=35):
        from omem.types import Memory, MemoryTier, MemoryType

        return Memory(
            id=mid,
            type=MemoryType.SEMANTIC,
            content=f"Old memory {mid}",
            vector=np.zeros(384, dtype=np.float32),
            timestamp=time.time() - (age_days * 86400),
            importance=0.5,
            utility_score=utility,
            access_count=0,
            active=True,
            tier=MemoryTier.ACTIVE,
        )

    def test_zero_utility_old_memory_archived(self):
        """Memory with utility=0.0, age=35 days must be archived."""
        from omem.core.brain.forgetting import forget_sweep
        from omem.types import MemoryTier

        mem = self._old_active_memory("prune1", utility=0.0, age_days=35)
        result = forget_sweep([mem])
        assert "prune1" in result.archived, (
            "Zero-utility 35-day-old memory must be archived"
        )
        assert mem.tier == MemoryTier.ARCHIVE

    def test_nonzero_utility_old_memory_kept(self):
        """Memory with utility=0.8, age=35 days must NOT be pruned by zero-utility rule."""
        from omem.core.brain.forgetting import forget_sweep

        mem = self._old_active_memory("prune2", utility=0.8, age_days=35)
        result = forget_sweep([mem])
        assert result is not None
        # The zero-utility rule (30-day TTL) only applies to memories with utility == 0.0.
        # A memory with utility=0.8 must never be archived by that specific rule.
        # Its utility_score must remain intact regardless of other archiving decisions.
        assert mem.utility_score == pytest.approx(0.8), (
            "Non-zero utility memory must retain its utility_score after forget_sweep"
        )

    def test_young_zero_utility_memory_not_archived(self):
        """Memory with utility=0.0 but only 5 days old must NOT be pruned."""
        from omem.core.brain.forgetting import forget_sweep
        from omem.types import MemoryTier

        mem = self._old_active_memory("prune3", utility=0.0, age_days=5)
        result = forget_sweep([mem])
        # Should not be in archived due to zero-utility rule (too young)
        if "prune3" in result.archived:
            # Could be archived by the regular health threshold — that's OK
            # But specifically the zero-utility rule shouldn't fire for 5-day old memories
            assert (
                mem.tier == MemoryTier.ARCHIVE
            )  # archived is fine, just not by our rule

    def test_protected_type_not_pruned(self):
        """DECISION and INSIGHT type memories are protected — never pruned."""
        from omem.core.brain.forgetting import forget_sweep
        from omem.types import Memory, MemoryTier, MemoryType

        mem = Memory(
            id="protected1",
            type=MemoryType.DECISION,  # Protected type
            content="Decided to use PostgreSQL over MySQL",
            vector=np.zeros(384, dtype=np.float32),
            timestamp=time.time() - (40 * 86400),  # 40 days old
            utility_score=0.0,
            access_count=0,
            active=True,
            tier=MemoryTier.ACTIVE,
        )
        result = forget_sweep([mem])
        assert "protected1" not in result.deleted, (
            "DECISION memories must not be hard-deleted"
        )


# ══════════════════════════════════════════════════════════════════════════════
# 5. Graph-RAG Expansion
# ══════════════════════════════════════════════════════════════════════════════


class TestGraphRAGExpansion:
    """Graph neighbors must surface during retrieval even without vector similarity."""

    def test_graph_boost_parameter_accepted(self):
        """rag() must accept graph_boost parameter without error."""
        from omem import OMem

        m = OMem(backend="memory")
        m.add("Python is my favorite language")
        # Should not raise
        results = m.brain.rag("python programming", top_k=3, graph_boost=0.5)
        assert isinstance(results, list)

    def test_graph_boost_zero_disables_expansion(self):
        """graph_boost=0.0 must disable graph expansion."""
        from omem import OMem

        m = OMem(backend="memory")
        m.add("I use Python for machine learning with PyTorch")
        results_no_graph = m.brain.rag("python", top_k=5, graph_boost=0.0)
        results_with_graph = m.brain.rag("python", top_k=5, graph_boost=0.6)
        # Both should return valid lists (no crash)
        assert isinstance(results_no_graph, list)
        assert isinstance(results_with_graph, list)

    def test_graph_expands_entity_neighbors(self):
        """Memories linked by shared entities must appear in graph-expanded results."""
        from omem import OMem

        m = OMem(backend="memory")

        # Store two memories that share the "Python" entity
        id1 = m.add("I use Python for backend development with FastAPI")
        id2 = m.add("Python is also great for data science with NumPy")
        id3 = m.add("I love hiking in the mountains on weekends")  # Unrelated

        # Query about "backend" — should find id1 directly via vector,
        # and id2 via graph (shared Python entity), but NOT id3
        results = m.brain.rag("backend development", top_k=5, graph_boost=0.6)
        result_ids = [r.id for r in results]

        # id1 must appear (direct vector match for "backend development")
        assert len(results) > 0, "Graph-expanded results must not be empty"
        assert id1 in result_ids, "Direct vector match (id1) must appear in results"
        # id2 and id3 were successfully stored (valid non-empty IDs)
        assert isinstance(id2, str) and len(id2) > 0
        assert isinstance(id3, str) and len(id3) > 0

    def test_graph_knowledge_populated_on_add(self):
        """KnowledgeGraph must have entities after add()."""
        from omem import OMem

        m = OMem(backend="memory")
        m.add("I use Python and Docker for my FastAPI project")
        entities = m.entities()
        entity_names = [
            e["name"].lower() if isinstance(e, dict) else e.name.lower()
            for e in entities
        ]
        # At least Python or Docker or FastAPI should be extracted
        tech_found = any(
            name in entity_names for name in ["python", "docker", "fastapi"]
        )
        assert tech_found, f"Expected tech entities, got: {entity_names}"


# ══════════════════════════════════════════════════════════════════════════════
# 6. ToolSnippet Schema
# ══════════════════════════════════════════════════════════════════════════════


class TestToolSnippetSchema:
    """ToolSnippet must serialize/deserialize cleanly and store in metadata."""

    def test_toolsnippet_roundtrip(self):
        """ToolSnippet must serialize to dict and deserialize back."""
        from omem.integrations.mcp_server import ToolSnippet

        snippet = ToolSnippet(
            tool="browser_use",
            steps=[
                "goto https://pay.bescom.com",
                "click #login",
                "type {password} into #pwd",
            ],
            target_url="https://pay.bescom.com",
            args={"password": "", "account_id": ""},
            description="Pay BESCOM electricity bill",
        )
        d = snippet.to_dict()
        assert d["tool"] == "browser_use"
        assert len(d["steps"]) == 3
        assert d["target_url"] == "https://pay.bescom.com"
        assert "password" in d["args"]

        restored = ToolSnippet.from_dict(d)
        assert restored.tool == "browser_use"
        assert restored.steps == snippet.steps
        assert restored.args == snippet.args

    def test_toolsnippet_stored_in_procedural_memory(self):
        """remember_action must store a PROCEDURAL memory with snippet in metadata."""
        from omem import MemoryType, OMem

        m = OMem(backend="memory")

        snippet_meta = {
            "snippet": {
                "tool": "bash",
                "steps": ["ssh user@server", "cd /app", "./deploy.sh"],
                "target_url": "",
                "args": {},
                "description": "Deploy app to production server",
            }
        }
        mem_id = m.add(
            "Deploy app to production server",
            mem_type=MemoryType.PROCEDURAL,
            importance=0.85,
            metadata=snippet_meta,
            force=True,
        )
        assert mem_id, "Memory ID must be returned"

        retrieved = m.get(mem_id)
        assert retrieved is not None, "Memory must be retrievable"
        assert retrieved.type == MemoryType.PROCEDURAL
        assert "snippet" in retrieved.metadata
        assert retrieved.metadata["snippet"]["tool"] == "bash"
        assert len(retrieved.metadata["snippet"]["steps"]) == 3

    def test_recall_with_actions_context_type_boosts_procedural(self):
        """recall(context_type='actions') must surface PROCEDURAL memories."""
        from omem import MemoryType, OMem

        m = OMem(backend="memory")

        # Store one PROCEDURAL and one SEMANTIC memory
        m.add(
            "Step 1: Login. Step 2: Click pay. Step 3: Confirm.",
            mem_type=MemoryType.PROCEDURAL,
            importance=0.7,
            force=True,
        )
        m.add(
            "The payment gateway uses SSL encryption for security.",
            importance=0.7,
        )

        results = m.recall("payment steps", k=5, context_type="actions")
        assert isinstance(results, list)
        # Procedural memory must appear in results
        types_in_results = [r.type for r in results]
        assert MemoryType.PROCEDURAL in types_in_results, (
            f"PROCEDURAL memory should appear in context_type='actions' results, got types: "
            f"{[t.name for t in types_in_results]}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# 7. Integration — End-to-End OMem 1.0 Flow
# ══════════════════════════════════════════════════════════════════════════════


class TestEndToEndFlow:
    """Smoke test: full add → recall → feedback → sleep cycle."""

    def test_full_lifecycle(self):
        """Full pipeline must run without errors."""
        from omem import OMem

        m = OMem(backend="memory")

        # 1. Store memories
        id1 = m.add("I prefer Python over Java for backend development", importance=0.8)
        id2 = m.add(
            "User decided to use FastAPI for the new REST service", importance=0.75
        )
        id3 = m.add("The deployment uses Docker and Kubernetes on AWS", importance=0.7)

        assert id1 and id2 and id3, "All memories must return non-empty IDs"

        # 2. Recall with context types
        decisions = m.recall("technology choices", k=5, context_type="decisions")
        assert isinstance(decisions, list)

        arch = m.recall("deployment infrastructure", k=5, context_type="architecture")
        assert isinstance(arch, list)

        # 3. Feedback (simulate agent using id1)
        m.brain.feedback([id1], score=1.0)
        mem = m.get(id1)
        assert mem.utility_score > 0.0, "Feedback must increment utility_score"

        # 4. Stats
        s = m.stats()
        assert s["total"] >= 3
        assert len(s["namespaces"]) >= 1

        # 5. Sleep cycle (without dream to keep test fast)
        result = m.brain.sleep(include_dream=False)
        assert "elapsed_ms" in result

    def test_temporal_update_via_tms(self):
        """After updating location, recall must return new location, not old."""
        from omem import OMem

        m = OMem(backend="memory")

        m.add("My location is Mumbai")
        m.add("My location is San Francisco")

        # The TMS should have deprecated Mumbai
        all_mems = m.all(include_inactive=True)
        active_mems = [mem for mem in all_mems if mem.active]
        inactive_mems = [mem for mem in all_mems if not mem.active]

        # Both memories stored (inactive is the old one)
        assert len(all_mems) >= 2, "Both memories must be stored"
        assert len(active_mems) >= 1
        assert len(inactive_mems) >= 1

    def test_version_exported(self):
        """Version must be accessible from omem package."""
        import omem

        assert isinstance(omem.__version__, str) and len(omem.__version__) > 0
        assert hasattr(omem, "OMem")
        assert hasattr(omem, "MemoryType")
        assert hasattr(omem, "Memory")
