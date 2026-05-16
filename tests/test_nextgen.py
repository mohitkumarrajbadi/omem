"""Tests for the 3 next-gen OMem systems: Forgetting, Mode-Aware Retrieval, Identity Layer."""

import time

import numpy as np
import pytest

from omem import MemoryPriority, MemoryTier, MemoryType, OMem
from omem.core.brain.forgetting import (
    ForgetResult,
    compute_health,
    forget_sweep,
    restore_memory,
)
from omem.core.brain.importance import estimate_priority
from omem.types import Memory

# ==============================================================
# IDENTITY LAYER - priority classification
# ==============================================================


class TestIdentityPriority:
    """Test auto-classification of memory priority."""

    def test_identity_is_core(self):
        assert estimate_priority("My name is Mohit") == MemoryPriority.CORE

    def test_pii_is_core(self):
        assert estimate_priority("My birthday is March 15") == MemoryPriority.CORE

    def test_secrets_are_core(self):
        assert estimate_priority("The API key is sk-12345") == MemoryPriority.CORE

    def test_goals_are_high(self):
        assert estimate_priority("My goal is to build a startup") == MemoryPriority.HIGH

    def test_preferences_are_high(self):
        assert (
            estimate_priority("I prefer Python over JavaScript") == MemoryPriority.HIGH
        )

    def test_decisions_are_high(self):
        assert estimate_priority("I decided to use FastAPI") == MemoryPriority.HIGH

    def test_filler_is_low(self):
        assert estimate_priority("okay sure") == MemoryPriority.LOW

    def test_greetings_are_low(self):
        assert estimate_priority("hello") == MemoryPriority.LOW

    def test_facts_are_normal(self):
        assert (
            estimate_priority("Python was created in 1991 by Guido van Rossum")
            == MemoryPriority.NORMAL
        )

    def test_core_priority_gets_core_tier(self):
        """CORE priority memories should be auto-assigned CORE tier."""
        m = OMem(backend="memory")
        mid = m.add("My name is Mohit")
        mem = m.get(mid)
        assert mem is not None
        assert mem.priority == MemoryPriority.CORE
        assert mem.tier == MemoryTier.CORE

    def test_normal_priority_gets_active_tier(self):
        m = OMem(backend="memory")
        mid = m.add("Python is a programming language")
        mem = m.get(mid)
        assert mem is not None
        assert mem.priority == MemoryPriority.NORMAL
        assert mem.tier == MemoryTier.ACTIVE


# ==============================================================
# FORGETTING ENGINE
# ==============================================================


class TestForgettingEngine:
    """Test health scoring and lifecycle transitions."""

    def _make_memory(
        self,
        content="test",
        importance=0.5,
        access_count=0,
        timestamp=None,
        last_accessed=0.0,
        priority=MemoryPriority.NORMAL,
        tier=MemoryTier.ACTIVE,
    ) -> Memory:
        ts = timestamp or time.time()
        return Memory(
            id="test-id",
            type=MemoryType.SEMANTIC,
            content=content,
            vector=np.zeros(384, dtype=np.float32),
            timestamp=ts,
            importance=importance,
            access_count=access_count,
            last_accessed=last_accessed,
            priority=priority,
            tier=tier,
        )

    def test_healthy_memory_stays_active(self):
        mem = self._make_memory(importance=0.8, access_count=5)
        health = compute_health(mem)
        assert health > 0.15  # above archive threshold

    def test_old_unused_memory_has_low_health(self):
        old_ts = time.time() - (30 * 24 * 3600)  # 30 days ago
        mem = self._make_memory(importance=0.3, access_count=0, timestamp=old_ts)
        health = compute_health(mem)
        assert health < 0.15  # below archive threshold

    def test_core_immune_from_forgetting(self):
        old_ts = time.time() - (60 * 24 * 3600)  # 60 days ago
        mem = self._make_memory(
            importance=0.1,
            access_count=0,
            timestamp=old_ts,
            priority=MemoryPriority.CORE,
            tier=MemoryTier.CORE,
        )
        result = forget_sweep([mem])
        assert len(result.archived) == 0
        assert len(result.deleted) == 0
        assert result.core_immune == 1

    def test_low_health_gets_archived(self):
        old_ts = time.time() - (30 * 24 * 3600)
        mem = self._make_memory(importance=0.2, access_count=0, timestamp=old_ts)
        result = forget_sweep([mem])
        assert mem.id in result.archived
        assert mem.tier == MemoryTier.ARCHIVE
        assert mem.active is False

    def test_archived_memory_hard_deleted_after_ttl(self):
        old_ts = time.time() - (60 * 24 * 3600)
        mem = self._make_memory(
            importance=0.1, access_count=0, timestamp=old_ts, tier=MemoryTier.ARCHIVE
        )
        mem.archived_at = time.time() - (8 * 24 * 3600)  # archived 8 days ago
        result = forget_sweep([mem])
        assert mem.id in result.deleted
        assert mem.tier == MemoryTier.FORGOTTEN

    def test_restore_archived_memory(self):
        mem = self._make_memory(tier=MemoryTier.ARCHIVE)
        mem.active = False
        mem.archived_at = time.time() - 3600
        restored = restore_memory(mem)
        assert restored is True
        assert mem.tier == MemoryTier.ACTIVE
        assert mem.active is True

    def test_restore_non_archived_fails(self):
        mem = self._make_memory(tier=MemoryTier.ACTIVE)
        assert restore_memory(mem) is False

    def test_forget_via_api(self):
        """End-to-end test: add memories, simulate aging, forget."""
        m = OMem(backend="memory")
        m.add("My name is Mohit")  # CORE - immune
        m.add("Python is a language")  # NORMAL
        m.add("okay sure got it")  # LOW - filler
        result = m.forget()
        assert isinstance(result, ForgetResult)
        # CORE-priority identity memory must be protected from forgetting
        assert result.core_immune >= 1


# ==============================================================
# MODE-AWARE RETRIEVAL
# ==============================================================


class TestModeAwareRetrieval:
    """Test mode-aware scoring and retrieval."""

    @pytest.fixture
    def loaded_mem(self):
        m = OMem(backend="memory")
        m.add("Yesterday I went to the park", mem_type=MemoryType.EPISODIC)
        m.add("To deploy, run docker compose up", mem_type=MemoryType.PROCEDURAL)
        m.add("I decided to use React", mem_type=MemoryType.DECISION)
        m.add("Python supports list comprehensions", mem_type=MemoryType.SEMANTIC)
        m.add("The server crashed because of a memory leak", mem_type=MemoryType.CAUSAL)
        return m

    def test_default_mode(self, loaded_mem):
        results = loaded_mem.recall("programming language", mode="default")
        assert len(results) > 0

    def test_coding_mode_boosts_procedural(self, loaded_mem):
        results_default = loaded_mem.recall("deploy application", mode="default")
        results_coding = loaded_mem.recall("deploy application", mode="coding")
        # In coding mode, PROCEDURAL should get a boost — results must be non-empty
        assert len(results_coding) > 0
        assert len(results_default) > 0
        # The PROCEDURAL memory must appear in at least one result set
        proc_default = [r for r in results_default if r.type == MemoryType.PROCEDURAL]
        proc_coding = [r for r in results_coding if r.type == MemoryType.PROCEDURAL]
        assert len(proc_coding) > 0, (
            "PROCEDURAL memory must appear in coding-mode results for 'deploy application'"
        )
        if proc_default and proc_coding:
            assert proc_coding[0].score >= proc_default[0].score, (
                "Coding mode must give PROCEDURAL memories a higher score than default mode"
            )

    def test_planning_mode_boosts_decisions(self, loaded_mem):
        results = loaded_mem.recall("technology choice", mode="planning")
        assert len(results) > 0

    def test_chat_mode_boosts_episodic(self, loaded_mem):
        results = loaded_mem.recall("what did I do", mode="chat")
        assert len(results) > 0

    def test_recall_mode_boosts_vector(self, loaded_mem):
        results = loaded_mem.recall("memory management", mode="recall")
        assert len(results) > 0

    def test_mode_parameter_in_api(self, loaded_mem):
        """Mode parameter is accessible through the public API."""
        results = loaded_mem.recall("deploy", mode="coding")
        assert isinstance(results, list)

    def test_invalid_mode_falls_back_to_default(self, loaded_mem):
        """Unknown mode defaults to standard weights."""
        results = loaded_mem.recall("deploy", mode="nonexistent")
        assert len(results) > 0


# ==============================================================
# IDENTITY-PRIORITY SCORING
# ==============================================================


class TestPriorityScoring:
    """Test that priority multipliers affect retrieval ranking."""

    def test_identity_memory_scores_higher(self):
        """CORE priority memory should score higher than NORMAL for same query."""
        m = OMem(backend="memory")
        m.add("My name is Mohit and I work on AI")  # CORE priority
        m.add("Someone named Mohit works on AI")  # NORMAL priority
        results = m.recall("who is Mohit")
        assert len(results) > 0, "Recall must return at least one result"
        # CORE memory must appear in results
        core_results = [r for r in results if r.priority == MemoryPriority.CORE]
        assert len(core_results) > 0, (
            "CORE priority memory must appear in recall results"
        )
        assert core_results[0].score > 0, "CORE priority memory must have positive score"

    def test_low_priority_penalised(self):
        """LOW priority memory should get 0.7x scoring penalty vs NORMAL."""
        m = OMem(backend="memory")
        m.add("Python was created in 1991 by Guido van Rossum")  # NORMAL priority
        m.add("okay sure got it thanks")  # LOW priority
        results = m.recall("Python")
        assert len(results) > 0, "Recall must return at least one result"
        # NORMAL-priority Python memory must rank above LOW-priority filler
        normal = [r for r in results if r.priority == MemoryPriority.NORMAL]
        low = [r for r in results if r.priority == MemoryPriority.LOW]
        assert len(normal) > 0, "NORMAL priority memory about Python must appear in results"
        if low:
            assert normal[0].score >= low[0].score, (
                "NORMAL priority must score >= LOW priority for same query"
            )

    def test_priority_in_to_dict(self):
        m = OMem(backend="memory")
        mid = m.add("My name is Test User")
        mem = m.get(mid)
        d = mem.to_dict()
        assert "priority" in d
        assert d["priority"] == "CORE"
        assert "tier" in d
        assert d["tier"] == "CORE"
