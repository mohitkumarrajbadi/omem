"""Kill-the-Agent demo + custom loop + concurrency for OMem v1."""

from __future__ import annotations

import threading

import pytest

from omem import AgentState
from omem.demo.kill_resume import run_kill_resume
from omem.integrations.custom_loop import DurableLoop
from omem.integrations.langgraph import OMemCheckpointSaver
from omem.state import InMemoryRunStore, InMemoryStateBackend, RunOS, StateOS
from omem.types import StatePayload


class TestKillResumeDemo:
    def test_demo_ok(self):
        report = run_kill_resume()
        assert report["ok"] is True
        assert report["killed_at_step"] == 6
        assert report["resumed_step"] == 6
        assert report["event_count"] >= 10
        assert report.get("fork_run_id")


class TestCustomLoop:
    def test_step_checkpoint_resume(self, tmp_path):
        db = str(tmp_path / "loop.db")
        agent = AgentState(session_id="loop-1", backend="sqlite", db_path=db)
        loop = DurableLoop.start(agent, goal="do work", worker_id="w1")
        loop.step("a", lambda: {"n": 1})
        loop.step("b", lambda: {"n": 2})
        rid = loop.run.run_id
        step = agent.current_state().step
        assert step == 2

        # Simulate death
        r = agent.runs.get_run(rid)
        r.lease_until = 0.0
        agent.runs._store.save_run(r)
        del agent

        agent2 = AgentState(session_id="loop-1", backend="sqlite", db_path=db)
        loop2 = DurableLoop.resume(agent2, rid, worker_id="w2")
        assert agent2.current_state().step == step
        loop2.step("c", lambda: {"n": 3})
        loop2.complete()
        assert loop2.run.refresh().status == "done"


class TestLangGraphEmit:
    def test_put_emits_checkpoint_event(self):
        state = StateOS(backend=InMemoryStateBackend())
        ros = RunOS(store=InMemoryRunStore(), state=state)
        sid = "lg-thread"
        state.save(sid, StatePayload(session_id=sid))
        active = ros.start_run(sid, goal="lg")
        saver = OMemCheckpointSaver(state=state, run_os=ros, run_id=active.run_id)
        cfg = {"configurable": {"thread_id": sid}}
        out = saver.put(cfg, {"id": "lg_chk_1", "channel_values": {}})
        assert out["configurable"]["checkpoint_id"] == "lg_chk_1"
        types = [e.type for e in active.inspect_events()]
        assert "checkpoint" in types


class TestConcurrentAppend:
    def test_sequences_unique_under_threads(self):
        state = StateOS(backend=InMemoryStateBackend())
        ros = RunOS(store=InMemoryRunStore(), state=state)
        sid = "conc"
        state.save(sid, StatePayload(session_id=sid))
        active = ros.start_run(sid)
        rid = active.run_id
        errors = []

        def writer(n: int):
            try:
                for i in range(20):
                    ros.record_event(
                        rid,
                        "observation",
                        {"w": n, "i": i},
                        idempotency_key=f"w{n}-{i}",
                    )
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(n,)) for n in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        events = ros.list_events(rid)
        seqs = [e.sequence for e in events]
        assert len(seqs) == len(set(seqs))
        assert seqs == sorted(seqs)
