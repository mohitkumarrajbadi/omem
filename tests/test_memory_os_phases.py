"""Regression tests for Memory OS gap-closure phases A–E."""

import time

import numpy as np

from benchmarks.slo_recall_latency import run_recall_slo
from omem import OMem, resolve_hierarchy_level
from omem.core.brain.hierarchy import run_hierarchy_conveyor
from omem.core.brain.ingest_pipeline import IngestItem, IngestPipeline
from omem.core.brain.lifecycle_fsm import advance_stage, mark_reinforced
from omem.core.retrieval.bm25 import keyword_bm25_blend
from omem.core.retrieval.type_strategies import fusion_for_type, strategy_for
from omem.memory import MemoryOS
from omem.types import LifecycleStage, Memory, MemoryType


class TestPhaseABM25AndSLO:
    def test_bm25_ranks_relevant_higher(self):
        docs = [
            "cats and dogs are pets",
            "PostgreSQL SCRAM authentication upgrade checklist",
            "weather is nice today",
        ]
        scores = keyword_bm25_blend(docs, "PostgreSQL SCRAM upgrade")
        assert scores[1] == max(scores)

    def test_slo_p95_under_threshold_small_n(self):
        # Smaller corpus for CI speed; charter gate uses 500 in benchmark module
        report = run_recall_slo(n_memories=80, n_queries=40, k=5, threshold_p95_ms=50.0)
        assert report.p95_ms < 50.0
        assert report.as_dict()["passed"] is True


class TestPhaseBTypeAndFSM:
    def test_type_strategy_tool_exact(self):
        s = strategy_for(MemoryType.TOOL)
        assert s.lookup.value == "exact"
        w = fusion_for_type(MemoryType.TOOL)
        assert w.keyword >= w.semantic

    def test_fsm_transitions(self):
        mem = Memory(
            id="x",
            type=MemoryType.EPISODIC,
            content="hi",
            vector=np.zeros(8, dtype=np.float32),
        )
        assert mark_reinforced(mem)
        assert mem.lifecycle_stage == LifecycleStage.REINFORCED.value
        assert advance_stage(mem, LifecycleStage.CONSOLIDATED.value)
        assert not advance_stage(mem, LifecycleStage.NEW.value)  # no backward


class TestPhaseCHierarchy:
    def test_promote_working_to_short_term(self):
        now = time.time()
        mem = Memory(
            id="m1",
            type=MemoryType.WORKING,
            content="active task",
            vector=np.zeros(8, dtype=np.float32),
            level="working",
            access_count=5,
            timestamp=now - 10,
        )
        out = run_hierarchy_conveyor([mem], now=now)
        assert mem.level == "short_term"
        assert "m1" in out["promoted"]


class TestPhaseDIngest:
    def test_ingest_batch_throughput_path(self):
        brain = OMem()
        pipe = IngestPipeline(brain.brain, defer_embed=True)
        items = [
            IngestItem(content=f"fact number {i} about postgres incidents")
            for i in range(50)
        ]
        result = pipe.ingest_batch(items)
        assert result.accepted == 50
        assert result.ops_per_sec > 0
        # Deferred path should be much faster than naive sequential embed
        assert result.elapsed_ms < 5000


class TestPhaseETenantAndGraph:
    def test_memory_os_ingest_batch_api(self):
        mos = MemoryOS()
        out = mos.ingest_batch(["ADR-1 use Postgres", "incident INC-9 timeout"], defer_embed=True)
        assert out["accepted"] == 2

    def test_hierarchy_aliases_still(self):
        assert resolve_hierarchy_level("L3") == "long_term"
