"""Tests for Phase 6 — ObserveOS.

Validates: TraceEvent storage, metrics computation, replay, OTel export,
and the instrumentation integration with AgentState.
"""

from __future__ import annotations

import time

import pytest

from omem.observe.events import (
    ObserveOS,
    TraceEvent,
    _percentile,
    new_trace_id,
)

# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def obs():
    return ObserveOS()


def _event(event_type: str, session_id: str = "s1", duration_ms: float = 10.0,
           namespace: str = "default", **payload) -> TraceEvent:
    return TraceEvent(
        id=new_trace_id(),
        session_id=session_id,
        event_type=event_type,
        timestamp=time.time(),
        duration_ms=duration_ms,
        namespace=namespace,
        payload=payload,
    )


# ──────────────────────────────────────────────────────────────────────────────
# TraceEvent and helpers
# ──────────────────────────────────────────────────────────────────────────────


class TestTraceEvent:
    def test_new_trace_id_prefix(self):
        tid = new_trace_id()
        assert tid.startswith("tr_")

    def test_new_trace_id_unique(self):
        ids = {new_trace_id() for _ in range(100)}
        assert len(ids) == 100

    def test_trace_event_to_dict(self):
        ev = _event("recall", duration_ms=25.5)
        d = ev.to_dict()
        assert d["event_type"] == "recall"
        assert d["duration_ms"] == 25.5
        assert "session_id" in d
        assert "payload" in d

    def test_percentile_empty(self):
        assert _percentile([], 50) == 0.0

    def test_percentile_single(self):
        assert _percentile([42.0], 50) == 42.0
        assert _percentile([42.0], 99) == 42.0

    def test_percentile_p50(self):
        data = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert _percentile(data, 50) == pytest.approx(3.0)

    def test_percentile_p99(self):
        data = list(range(1, 101))
        p99 = _percentile([float(x) for x in data], 99)
        assert 98.0 <= p99 <= 100.0


# ──────────────────────────────────────────────────────────────────────────────
# EventStore and ObserveOS
# ──────────────────────────────────────────────────────────────────────────────


class TestObserveOS:
    def test_record_and_traces(self, obs):
        ev = _event("recall", session_id="abc")
        obs.record(ev)
        traces = obs.traces("abc")
        assert len(traces) == 1
        assert traces[0].event_type == "recall"

    def test_traces_empty_session(self, obs):
        assert obs.traces("nonexistent") == []

    def test_record_multiple_sessions(self, obs):
        for _ in range(3):
            obs.record(_event("snapshot", session_id="s1"))
        for _ in range(2):
            obs.record(_event("recall", session_id="s2"))
        assert len(obs.traces("s1")) == 3
        assert len(obs.traces("s2")) == 2

    def test_replay_yields_in_order(self, obs):
        for i in range(5):
            obs.record(_event("remember", session_id="r1", memory_id=str(i)))
        replayed = list(obs.replay("r1"))
        assert len(replayed) == 5
        assert all(e.event_type == "remember" for e in replayed)

    def test_replay_empty_session(self, obs):
        assert list(obs.replay("empty")) == []

    def test_metrics_empty(self, obs):
        m = obs.metrics()
        assert m["total_events"] == 0
        assert m["recall_count"] == 0

    def test_metrics_recall_count(self, obs):
        for _ in range(7):
            obs.record(_event("recall", session_id="m1", duration_ms=20.0))
        m = obs.metrics(session_id="m1")
        assert m["recall_count"] == 7

    def test_metrics_recall_latency(self, obs):
        durations = [10.0, 20.0, 30.0, 40.0, 50.0]
        for d in durations:
            obs.record(_event("recall", session_id="lat", duration_ms=d))
        m = obs.metrics(session_id="lat")
        assert m["recall_latency_p50_ms"] == pytest.approx(30.0, abs=1.0)
        assert m["recall_latency_p99_ms"] >= 45.0

    def test_metrics_context_savings(self, obs):
        obs.record(_event("context_build", session_id="ctx", duration_ms=50.0,
                          savings_pct=68.0, token_count=4000))
        obs.record(_event("context_build", session_id="ctx", duration_ms=50.0,
                          savings_pct=72.0, token_count=3800))
        m = obs.metrics(session_id="ctx")
        assert m["context_build_count"] == 2
        assert m["context_tokens_saved_pct"] == pytest.approx(70.0, abs=1.0)

    def test_metrics_snapshot_count(self, obs):
        for _ in range(4):
            obs.record(_event("snapshot", session_id="snp"))
        m = obs.metrics(session_id="snp")
        assert m["snapshot_count"] == 4

    def test_metrics_namespace_filter(self, obs):
        obs.record(_event("recall", session_id="s1", namespace="ns-a"))
        obs.record(_event("recall", session_id="s2", namespace="ns-b"))
        m = obs.metrics(namespace="ns-a")
        assert m["recall_count"] == 1

    def test_metrics_restore_success_rate_all_success(self, obs):
        obs.record(_event("rollback", session_id="rb"))
        obs.record(_event("rollback", session_id="rb"))
        m = obs.metrics(session_id="rb")
        assert m["restore_success_rate"] == 1.0

    def test_metrics_restore_success_rate_with_error(self, obs):
        obs.record(_event("rollback", session_id="rb2"))
        obs.record(_event("rollback", session_id="rb2", error="snapshot not found"))
        m = obs.metrics(session_id="rb2")
        assert 0.0 <= m["restore_success_rate"] <= 1.0

    def test_session_ids(self, obs):
        obs.record(_event("recall", session_id="x1"))
        obs.record(_event("recall", session_id="x2"))
        ids = obs.session_ids()
        assert "x1" in ids
        assert "x2" in ids

    def test_event_count(self, obs):
        for _ in range(5):
            obs.record(_event("remember", session_id="cnt"))
        assert obs.event_count(session_id="cnt") == 5
        assert obs.event_count() >= 5

    def test_clear_session(self, obs):
        obs.record(_event("recall", session_id="clr"))
        obs.clear("clr")
        assert obs.traces("clr") == []

    def test_clear_all(self, obs):
        obs.record(_event("recall", session_id="a"))
        obs.record(_event("recall", session_id="b"))
        obs.clear()
        assert obs.event_count() == 0

    def test_record_never_raises_on_bad_event(self, obs):
        # Should silently swallow any internal error
        obs.record(None)  # type: ignore[arg-type]


class TestOtelExport:
    def test_export_structure(self, obs):
        obs.record(_event("recall", session_id="otel1"))
        export = obs.export_otel(session_id="otel1")
        assert "resourceSpans" in export
        rs = export["resourceSpans"]
        assert len(rs) >= 1
        ss = rs[0]["scopeSpans"]
        assert len(ss) >= 1
        spans = ss[0]["spans"]
        assert len(spans) == 1
        span = spans[0]
        assert span["operationName"] == "recall"
        assert "traceId" in span
        assert "spanId" in span

    def test_export_empty_session(self, obs):
        export = obs.export_otel(session_id="empty-otel")
        assert "resourceSpans" in export

    def test_export_service_name(self, obs):
        obs.record(_event("snapshot", session_id="svc"))
        export = obs.export_otel(service_name="my-agent", session_id="svc")
        attrs = export["resourceSpans"][0]["resource"]["attributes"]
        names = {a["key"]: a["value"]["stringValue"] for a in attrs}
        assert names["service.name"] == "my-agent"


# ──────────────────────────────────────────────────────────────────────────────
# Integration: AgentState emits traces
# ──────────────────────────────────────────────────────────────────────────────


class TestAgentStateInstrumentation:
    def test_remember_emits_trace(self):
        from omem import AgentState
        agent = AgentState(session_id="trace-test", backend="memory")
        agent.remember("FastAPI uses Pydantic")
        m = agent.observe.metrics(session_id="trace-test")
        assert m["remember_count"] == 1

    def test_recall_emits_trace(self):
        from omem import AgentState
        agent = AgentState(session_id="recall-trace", backend="memory")
        agent.remember("Python is a language")
        agent.recall("Python")
        m = agent.observe.metrics(session_id="recall-trace")
        assert m["recall_count"] == 1

    def test_snapshot_emits_trace(self):
        from omem import AgentState
        agent = AgentState(session_id="snap-trace", backend="memory")
        agent.set_goal("do something")
        agent.snapshot("v1")
        m = agent.observe.metrics(session_id="snap-trace")
        assert m["snapshot_count"] == 1

    def test_checkpoint_emits_trace(self):
        from omem import AgentState
        agent = AgentState(session_id="ckpt-trace", backend="memory")
        agent.checkpoint()
        m = agent.observe.metrics(session_id="ckpt-trace")
        assert m["checkpoint_count"] == 1

    def test_learn_emits_trace(self):
        from omem import AgentState
        agent = AgentState(session_id="learn-trace", backend="memory")
        agent.learn("Python", "has", "GIL")
        m = agent.observe.metrics(session_id="learn-trace")
        assert m["knowledge_link_count"] == 1

    def test_no_session_no_trace(self):
        from omem import AgentState
        agent = AgentState(backend="memory")  # no session_id
        agent._emit("recall", 5.0)  # should not crash
        # No session means no events stored
        assert agent.observe.event_count() == 0
