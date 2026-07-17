"""Memory OS Phase 1–4 unit coverage."""

import tempfile

import numpy as np

from omem import OMem, resolve_hierarchy_level
from omem.backends.cold_archive import ColdArchive, ColdArchiveConfig
from omem.core.brain.dream import _extract_semantic_rule
from omem.core.graph.knowledge import EntityType, extract_entities
from omem.core.retrieval.fusion import FusionWeights, fuse_score
from omem.core.retrieval.lookup import LookupKind, resolve_lookup
from omem.governance.tenant import (
    harden_namespace,
    namespaces_isolated,
    resolve_tenant_from_binding,
)
from omem.memory import MemoryOS
from omem.types import LifecycleStage, Memory, MemoryType


def ndcg_at_k(retrieved, ground_truth, k: int = 5) -> float:
    import math

    if not ground_truth:
        return 1.0

    def _relevant(doc: str) -> float:
        return 1.0 if any(gt.lower() in doc.lower() for gt in ground_truth) else 0.0

    dcg = 0.0
    for i, doc in enumerate(retrieved[:k]):
        rel = _relevant(doc)
        dcg += rel if i == 0 else rel / math.log2(i + 1)
    ideal = min(len(ground_truth), k)
    idcg = sum(1.0 if i == 0 else 1.0 / math.log2(i + 1) for i in range(ideal))
    return 0.0 if idcg == 0 else dcg / idcg


class TestHierarchyAliases:
    def test_l0_l4(self):
        assert resolve_hierarchy_level("L0") == "working"
        assert resolve_hierarchy_level("L1") == "short_term"
        assert resolve_hierarchy_level("L2") == "long_term"
        assert resolve_hierarchy_level("L4") == "archive"
        assert resolve_hierarchy_level("skill") == "long_term"


class TestFusionParity:
    def test_success_goal_in_weights(self):
        w = FusionWeights()
        assert "success" in w.as_dict()
        assert "goal" in w.as_dict()
        assert len(w.as_weight_vector()) == 9

    def test_fuse_includes_new_signals(self):
        a = fuse_score(0.5, 0.5, 0.5, 0.5, success=1.0, goal=1.0)
        b = fuse_score(0.5, 0.5, 0.5, 0.5, success=0.0, goal=0.0)
        assert a > b


class TestLookupRouter:
    def test_resolve(self):
        assert resolve_lookup(lookup="temporal") == LookupKind.TEMPORAL
        assert resolve_lookup(memory_type=MemoryType.TOOL) == LookupKind.EXACT
        assert resolve_lookup(lookup="state") == LookupKind.STATE


class TestArchiveFacade:
    def test_archive_marks_l4(self):
        brain = OMem()
        mid = brain.add("Ephemeral note about a meeting", force=True)
        assert mid
        ok = brain.archive(mid)
        assert ok
        mem = brain.get(mid)
        assert mem.level == "archive"
        assert mem.lifecycle_stage == LifecycleStage.ARCHIVED.value


class TestConsolidationRule:
    def test_rule_from_incidents(self):
        vec = np.zeros(8, dtype=np.float32)
        mems = [
            Memory(
                id=f"m{i}",
                type=MemoryType.EPISODIC,
                content=(
                    f"Postgres upgrade incident {i}: SCRAM compatibility failure "
                    f"before upgrade — must verify SCRAM"
                ),
                vector=vec,
            )
            for i in range(3)
        ]
        rule = _extract_semantic_rule(mems)
        assert rule is not None
        assert rule.startswith("Rule:")


class TestGraphEntities:
    def test_charter_types(self):
        ents = extract_entities(
            "See ADR-12 and INC-442 on AuthService. Project omem-cloud task TICKET-9"
        )
        types = {e.type for e in ents}
        assert EntityType.DOCUMENT in types or EntityType.INCIDENT in types or EntityType.SYSTEM in types


class TestTenantHierarchy:
    def test_namespace_and_isolation(self):
        a = resolve_tenant_from_binding(org_id="org-a", workspace_id="ws1")
        b = resolve_tenant_from_binding(org_id="org-b", workspace_id="ws1")
        assert namespaces_isolated(a.scope, b.scope)
        ns = harden_namespace("spoofed-org/evil", a)
        assert ns.startswith("org-a/")
        assert "spoofed-org" not in ns.split("/")[0]


class TestColdArchive:
    def test_local_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = ColdArchiveConfig(enabled=True, backend="local", local_root=tmp)
            cold = ColdArchive(cfg)
            key = cold.put_payload("m1", "full content here", namespace="demo")
            payload = cold.get_payload(key)
            assert payload["content"] == "full content here"


class TestNDCG:
    def test_perfect(self):
        assert ndcg_at_k(["alpha relevant"], ["alpha"], k=5) == 1.0

    def test_empty_gt(self):
        assert ndcg_at_k(["x"], [], k=5) == 1.0


class TestTypeConfidence:
    def test_stored_on_add(self):
        m = MemoryOS()
        mid = m.remember("Step 1: install deps then run tests")
        mem = m.omem.get(mid)
        assert mem is not None
        assert 0.0 < mem.type_confidence <= 1.0
