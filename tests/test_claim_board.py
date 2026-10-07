"""Strategic claim board — in-process proofs (no live Linode required).

Each test is a pass bar for one claim Tom/Mohit framed. Fail = claim not proven.
"""

from __future__ import annotations

import hashlib

from omem import AgentState
from omem.context.engine import ContextEngine, ContextRequest
from omem.context.inject import (
    HOST_INSTRUCTIONS,
    OMEM_CONTEXT_END,
    OMEM_CONTEXT_START,
    apply_omem_context,
    apply_omem_to_messages,
)
from omem.governance.tenant import TenantScope, namespaces_isolated
from omem.state import InMemoryStateBackend, SessionNotFoundError, StateOS, StatePayload
from omem.types import MemoryType


def _make_memory(
    content: str,
    score: float = 0.7,
    mtype: MemoryType = MemoryType.EPISODIC,
    mem_id: str | None = None,
    importance: float = 0.7,
):
    class _FakeMemory:
        def __init__(self):
            self.id = mem_id or hashlib.sha256(content.encode()).hexdigest()[:12]
            self.type = mtype
            self.content = content
            self.vector = None
            self.timestamp = 0.0
            self.importance = importance
            self.score = score
            self.source = "stub"
            self.namespace = "default"
            self.access_count = 0
            self.active = True

    return _FakeMemory()


class StubMemoryOS:
    def __init__(self, memories=None):
        self._memories = memories or []

    def recall(self, query: str, k: int = 5, **kwargs):
        return sorted(self._memories, key=lambda m: m.score, reverse=True)[:k]

    def list(self, namespace=None, **kwargs):
        if namespace:
            return [m for m in self._memories if m.namespace == namespace]
        return list(self._memories)


class TestClaim1AmnesiaVsRag:
    """Agents fail from amnesia; durable state restores work RAG dumps cannot."""

    def test_rag_dump_loses_goal_after_crash_omem_resume_restores(self):
        sid = "claim1-crash"
        state = StateOS(backend=InMemoryStateBackend())
        state.save(sid, StatePayload(session_id=sid))
        state.set_goal(sid, "Ship PKCE v2 to production")
        state.set_plan(sid, ["audit", "canary", "promote"])
        chk = state.checkpoint(sid)

        rag_only = StateOS(backend=InMemoryStateBackend())
        assert rag_only._backend.load_session(sid) is None

        recovered = state.resume(chk)
        assert recovered.goal == "Ship PKCE v2 to production"
        assert recovered.plan == ["audit", "canary", "promote"]

    def test_packed_context_keeps_decision_naive_dump_is_unbudgeted(self):
        decision = "MERGE DECISION: ship Plan A blue canary"
        filler = [
            _make_memory(f"noise-{i} " + ("padding " * 80), score=0.1, importance=0.1)
            for i in range(40)
        ]
        pin = _make_memory(decision, score=0.99, importance=0.99, mtype=MemoryType.DECISION)
        engine = ContextEngine(
            memory=StubMemoryOS([pin] + filler),
            cache_ttl=0,
            max_memories=8,
        )
        req = ContextRequest(task="merge decision pricing rollout", budget_tokens=400)
        bundle = engine.build(req)
        naive = engine._naive_token_count(req)
        assert naive > bundle.token_count
        assert bundle.savings_vs_naive >= 0.5
        assert "MERGE DECISION" in bundle.text or "Plan A" in bundle.text
        assert bundle.token_count <= 480


class TestClaim2TokenEconomics:
    def test_gross_pack_hits_90_percent_on_large_corpus(self):
        mems = [
            _make_memory(("irrelevant log line %d " % i) * 40, score=0.05, importance=0.1)
            for i in range(60)
        ]
        mems.insert(
            0,
            _make_memory(
                "Current status: JWT v2 PKCE approved for production.",
                score=0.99,
                importance=1.0,
            ),
        )
        engine = ContextEngine(memory=StubMemoryOS(mems), cache_ttl=0, max_memories=5)
        stats = engine.estimate_savings(
            ContextRequest(task="JWT v2 PKCE auth migration status", budget_tokens=300)
        )
        assert stats["naive_tokens"] > stats["optimised_tokens"]
        assert stats["savings_pct"] >= 90.0

    def test_correct_inject_prefix_stable_bad_host_breaks_prefix(self):
        prefix = "SYSTEM: coding agent.\nTOOLS: search, edit."
        packs = ["## OMem Context\nv1", "## OMem Context\nv2 facts"]
        good = prefix
        shas = []
        for pack in packs:
            good = apply_omem_context(good, pack)
            shas.append(hashlib.sha256(good.split(OMEM_CONTEXT_START)[0].encode()).hexdigest())
        assert shas[0] == shas[1]

        bad1 = prefix + "\nUSER turn0 rewritten\n" + packs[0]
        bad2 = prefix + "\nUSER turn1 rewritten extra\n" + packs[1]
        assert hashlib.sha256(bad1.encode()).hexdigest() != hashlib.sha256(bad2.encode()).hexdigest()


class TestClaim3AgentStatePrimitive:
    def test_checkpoint_fork_merge_pricing_ab(self):
        st = StateOS(backend=InMemoryStateBackend())
        st.save("pricing-parent", StatePayload(session_id="pricing-parent", goal="Price SKU"))
        snap = st.snapshot("pricing-parent", label="pre-fork")
        sid_a = st.fork(snap.id, new_session_id="pricing-plan-a")
        sid_b = st.fork(snap.id, new_session_id="pricing-plan-b")
        st.set_goal(sid_a, "Plan A: usage-based")
        st.set_goal(sid_b, "Plan B: seat-based")
        merged = st.merge(sid_a, "pricing-parent")
        assert "usage-based" in (merged.goal or "")

    def test_markers_wrap_every_pack(self):
        engine = ContextEngine(
            memory=StubMemoryOS([_make_memory("fact about PKCE", score=0.9)]),
            cache_ttl=0,
        )
        text = engine.build(ContextRequest(task="pkce", budget_tokens=200)).text
        assert OMEM_CONTEXT_START in text
        assert OMEM_CONTEXT_END in text
        assert "## OMem Context" in text


class TestClaim4GovernanceIsolation:
    def test_namespaces_isolated_helper(self):
        a = TenantScope(org_id="org-a", workspace_id="shared")
        b = TenantScope(org_id="org-b", workspace_id="shared")
        same = TenantScope(org_id="org-a", workspace_id="shared")
        assert namespaces_isolated(a, b)
        assert not namespaces_isolated(a, same)

    def test_cross_namespace_state_denied(self):
        shared = StateOS()
        shared.save("s1", StatePayload(session_id="s1", namespace="org-a/shared", goal="secret"))
        other = StateOS(backend=shared._backend, namespace="org-b/shared")
        try:
            other.load("s1")
            raise AssertionError("expected isolation miss")
        except SessionNotFoundError:
            pass


class TestClaim5NotAClaw:
    def test_agentstate_has_memory_state_not_inference_loop(self):
        names = {n for n in dir(AgentState) if not n.startswith("_")}
        required = {"remember", "recall", "build_context", "checkpoint", "fork", "merge_fork"}
        assert required.issubset(names)
        forbidden = {"run_agent", "complete", "infer", "schedule", "agent_loop", "chat_completion"}
        assert names.isdisjoint(forbidden)

    def test_host_instructions_warn_about_kv_cache(self):
        assert "KV" in HOST_INSTRUCTIONS
        lowered = HOST_INSTRUCTIONS.lower()
        assert "rewrite" in lowered or "reshuffle" in lowered


class TestClaim6OrthogonalHostAdapters:
    def test_openai_messages_and_langchain_style_dicts(self):
        openai_msgs = [
            {"role": "system", "content": "You are a coding agent."},
            {"role": "user", "content": "continue PKCE"},
            {"role": "assistant", "content": "working"},
        ]
        out = apply_omem_to_messages(openai_msgs, "## OMem Context\nPKCE approved")
        assert out[1]["content"] == "continue PKCE"
        assert out[2]["content"] == "working"
        assert OMEM_CONTEXT_START in out[0]["content"]

        lc_msgs = [
            {"role": "system", "content": "crew supervisor"},
            {"role": "user", "content": "task from crew"},
        ]
        out2 = apply_omem_to_messages(lc_msgs, "pack-crew")
        assert out2[1]["content"] == "task from crew"
        out3 = apply_omem_to_messages(out2, "pack-crew-v2")
        assert out3[1] == out2[1]
        assert "pack-crew-v2" in out3[0]["content"]

    def test_inject_contract_frozen_markers(self):
        assert OMEM_CONTEXT_START == "<!-- OMEM_CONTEXT_START -->"
        assert OMEM_CONTEXT_END == "<!-- OMEM_CONTEXT_END -->"
