"""P2: usage-trained sleep importance, 3-way merge, TS AST, Rust/NumPy ANN."""

import time

import numpy as np
import pytest

from omem import AgentState, OMem
from omem.core.brain.importance import apply_sleep_importance
from omem.core.retrieval.vector import VectorIndex
from omem.knowledge.codebase.ingester import ProjectIngester
from omem.knowledge.codebase.types import SymbolType
from omem.state import InMemoryStateBackend, StateOS, StatePayload, three_way_merge
from omem.types import Memory, MemoryPriority, MemoryType


def test_sleep_promotes_used_and_demotes_idle():
    now = time.time()
    used = Memory(
        id="used",
        type=MemoryType.SEMANTIC,
        content="Production database is PostgreSQL",
        vector=np.zeros(8, dtype=np.float32),
        importance=0.4,
        initial_importance=0.4,
        timestamp=now - 10 * 24 * 3600,
        last_accessed=now,
    )
    used.packed_count = 2
    used.retrieved_count = 1
    idle = Memory(
        id="idle",
        type=MemoryType.EPISODIC,
        content="random chitchat about the weather",
        vector=np.zeros(8, dtype=np.float32),
        importance=0.85,
        initial_importance=0.85,
        timestamp=now - 10 * 24 * 3600,
        last_accessed=now - 10 * 24 * 3600,
        priority=MemoryPriority.LOW,
    )
    stats = apply_sleep_importance([used, idle], now=now)
    assert stats["promoted"] >= 1
    assert stats["demoted"] >= 1
    assert used.importance > 0.4
    assert idle.importance < 0.85


def test_sleep_cycle_reports_importance(monkeypatch):
    monkeypatch.setenv("OMEM_EMBEDDER", "hash")
    m = OMem(backend="memory")
    mid = m.add("The checkout SKU is SKU-p2-sleep", importance=0.4)
    m.recall("SKU-p2-sleep", k=3)
    result = m.sleep(include_dream=False)
    assert "importance" in result
    assert "promoted" in result["importance"]
    mem = m.get(mid)
    assert mem is not None
    assert mem.importance >= 0.4


def test_three_way_merge_takes_side_that_changed():
    base = StatePayload(session_id="base", goal="Deploy API", plan=["a", "b"], step=0)
    ours = StatePayload(
        session_id="parent",
        goal="Deploy API",
        plan=["a", "b", "c"],
        step=1,
        workflow_state={"keep": 1},
    )
    theirs = StatePayload(
        session_id="fork",
        goal="Ship to EU first",
        plan=["a", "b"],
        step=0,
        workflow_state={"keep": 1, "region": "eu"},
    )
    merged = three_way_merge(base, ours, theirs, target_session_id="parent")
    assert merged.goal == "Ship to EU first"
    assert "c" in merged.plan
    assert merged.workflow_state.get("region") == "eu"
    assert merged.workflow_state.get("keep") == 1
    assert merged.session_id == "parent"
    assert "_omem_merge" not in merged.workflow_state


def test_three_way_merge_records_goal_conflict():
    base = StatePayload(session_id="base", goal="A")
    ours = StatePayload(session_id="parent", goal="B")
    theirs = StatePayload(session_id="fork", goal="C")
    merged = three_way_merge(base, ours, theirs, target_session_id="parent")
    assert merged.goal == "B"
    conflicts = merged.workflow_state["_omem_merge"]["conflicts"]
    assert any(c["field"] == "goal" for c in conflicts)


def test_stateos_merge_is_three_way_not_clobber():
    state = StateOS(backend=InMemoryStateBackend())
    state.save("base", StatePayload(session_id="base", goal="Deploy the new API"))
    state.set_plan("base", ["Audit", "Implement", "Release"])
    snap = state.snapshot("base", label="pre-fork")
    child = state.fork(snap.id, new_session_id="plan-b")
    state.set_goal(child, "EU rollout first")
    state.set_workflow(child, "region", "eu")
    state.set_plan("base", ["Audit", "Implement", "Load test", "Release"])
    merged = state.merge(child, "base")
    assert merged.session_id == "base"
    assert merged.goal == "EU rollout first"
    assert "Load test" in merged.plan
    assert merged.workflow_state.get("region") == "eu"
    parent = state.load("base")
    assert parent.goal == "EU rollout first"


def test_merge_fork_writes_into_parent():
    agent = AgentState(backend="memory", session_id="p2-parent")
    try:
        agent.set_goal("parent goal")
        snap = agent.snapshot()
        fork_id = agent.fork(snap.id, new_session_id="p2-fork")
        forked = agent.with_session(fork_id)
        forked.set_goal("fork goal")
        merged = agent.merge_fork(fork_id)
        assert merged.session_id == "p2-parent"
        assert merged.goal == "fork goal"
        assert agent.state.load("p2-parent").goal == "fork goal"
    finally:
        agent.close()


def test_typescript_ingester_extracts_structure(tmp_path):
    src = tmp_path / "users.ts"
    src.write_text(
        """
export interface User {
  id: string;
  email: string;
}

export type UserId = string;

export class UserService {
  constructor(private db: unknown) {}
  async fetchUser(id: string): Promise<User> {
    return { id, email: "a@b.c" };
  }
}

export function formatUser(user: User): string {
  return user.email;
}

export const loadUsers = async () => {
  return [];
};
""",
        encoding="utf-8",
    )
    symbols = ProjectIngester(str(tmp_path)).parse_file(str(src))
    names = {s.name for s in symbols}
    types = {s.symbol_type for s in symbols}
    assert "User" in names
    assert "UserService" in names
    assert "formatUser" in names
    assert SymbolType.INTERFACE in types
    assert SymbolType.CLASS in types
    assert SymbolType.FUNCTION in types
    assert any(s.symbol_type == SymbolType.MODULE for s in symbols)


def test_ingester_crawl_mixes_python_and_ts(tmp_path):
    (tmp_path / "a.py").write_text("def hello():\n    return 1\n", encoding="utf-8")
    (tmp_path / "b.ts").write_text("export function world() { return 2; }\n", encoding="utf-8")
    symbols = ProjectIngester(str(tmp_path)).crawl()
    names = {s.name for s in symbols}
    assert "hello" in names
    assert "world" in names


def test_vector_index_ann_top1():
    rng = np.random.default_rng(0)
    dim = 32
    idx = VectorIndex(dim=dim)
    mat = rng.normal(size=(20, dim)).astype(np.float32)
    mat /= np.linalg.norm(mat, axis=1, keepdims=True)
    for row in mat:
        idx.add(row)
    q = mat[7]
    scores, indices = idx.search(q, top_k=3)
    assert int(indices[0]) == 7
    assert float(scores[0]) > 0.99
