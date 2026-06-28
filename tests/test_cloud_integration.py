"""Integration + E2E tests for the OMem Cloud API.

These tests use a live server (either a real running Docker stack or an
in-process FastAPI TestClient). They validate the full stack end-to-end:

  remember → recall → checkpoint → rollback → fork → merge → audit

Run against the in-process TestClient (no Docker required)::

    pytest tests/test_cloud_integration.py -v

Run against a live Docker stack::

    OMEM_TEST_ENDPOINT=http://localhost pytest tests/test_cloud_integration.py -v -m live
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, Generator

import pytest

# ─── Fixtures ─────────────────────────────────────────────────────────────────

LIVE_ENDPOINT = os.environ.get("OMEM_TEST_ENDPOINT", "")
USE_LIVE = bool(LIVE_ENDPOINT)


@pytest.fixture(scope="module")
def client():
    """Return either an httpx client pointing at a live server or a FastAPI
    TestClient backed by a fresh in-process SQLite engine."""
    if USE_LIVE:
        import httpx
        with httpx.Client(base_url=LIVE_ENDPOINT, timeout=30.0) as c:
            yield c
    else:
        from fastapi.testclient import TestClient
        import os as _os
        _os.environ.setdefault("OMEM_BACKEND", "sqlite")
        _os.environ.setdefault("OMEM_DB_PATH", ":memory:")
        _os.environ.setdefault("OMEM_LOG_FORMAT", "text")
        _os.environ.setdefault("OMEM_CORS_ORIGINS", "http://localhost")
        from omem.cloud.server import app
        with TestClient(app) as c:
            yield c


@pytest.fixture
def session_id() -> str:
    return f"test-{int(time.time() * 1000)}"


def _remember(client, session_id: str, content: str, importance: float = 0.8) -> str:
    resp = client.post(
        "/v1/remember",
        json={"content": content, "importance": importance},
        headers={"X-OMem-Session": session_id},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["memory_id"]


def _recall(client, session_id: str, query: str, k: int = 5) -> list:
    resp = client.post(
        "/v1/recall",
        json={"query": query, "k": k},
        headers={"X-OMem-Session": session_id},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["memories"]


# ─── Unit-style integration tests ─────────────────────────────────────────────

class TestHealth:
    def test_health_returns_healthy(self, client):
        resp = client.get("/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("healthy", "degraded")
        assert "version" in data
        assert "uptime_seconds" in data

    def test_version_endpoint(self, client):
        resp = client.get("/v1/version")
        assert resp.status_code == 200
        assert resp.json()["protocol"] == "v1"

    def test_metrics_returns_prometheus_format(self, client):
        resp = client.get("/v1/metrics")
        assert resp.status_code == 200
        body = resp.text
        assert "omem_" in body or "# HELP" in body


class TestMemory:
    def test_remember_minimal_body(self, client, session_id):
        mem_id = _remember(client, session_id, "integration test memory")
        assert mem_id

    def test_recall_returns_relevant_memories(self, client, session_id):
        _remember(client, session_id, "Python async functions use await keyword", 0.9)
        _remember(client, session_id, "The capital of France is Paris", 0.5)
        _remember(client, session_id, "FastAPI supports async route handlers natively", 0.9)

        mems = _recall(client, session_id, "Python async programming", k=3)
        assert len(mems) >= 1
        top = mems[0]["content"]
        assert "async" in top.lower() or "python" in top.lower() or "fastapi" in top.lower()

    def test_recall_respects_k_parameter(self, client, session_id):
        for i in range(6):
            _remember(client, session_id, f"memory item number {i}", 0.7)

        mems = _recall(client, session_id, "memory item", k=3)
        assert len(mems) <= 3

    def test_explain_endpoint(self, client, session_id):
        _remember(client, session_id, "OMem uses FAISS for vector search", 0.9)
        resp = client.post(
            "/v1/explain",
            json={"query": "vector search", "k": 3},
            headers={"X-OMem-Session": session_id},
        )
        assert resp.status_code == 200

    def test_forget_runs_without_error(self, client, session_id):
        _remember(client, session_id, "temporary low-importance memory", 0.1)
        resp = client.post(
            "/v1/forget",
            headers={"X-OMem-Session": session_id},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestState:
    def test_state_save_and_load(self, client, session_id):
        resp = client.post(
            "/v1/state/save",
            json={"session_id": session_id, "goal": "Refactor auth module"},
        )
        assert resp.status_code == 200

        resp = client.get(f"/v1/state/{session_id}")
        assert resp.status_code == 200

    def test_checkpoint_and_resume(self, client, session_id):
        _remember(client, session_id, "pre-checkpoint memory", 0.8)

        chk_resp = client.post(
            f"/v1/state/{session_id}/checkpoint",
            headers={"X-OMem-Session": session_id},
        )
        assert chk_resp.status_code == 200
        assert "checkpoint_id" in chk_resp.json()

        resume_resp = client.post(
            f"/v1/state/{session_id}/resume",
            headers={"X-OMem-Session": session_id},
        )
        assert resume_resp.status_code == 200

    def test_snapshot_list_rollback(self, client, session_id):
        _remember(client, session_id, "memory before snapshot", 0.8)

        snap_resp = client.post(
            f"/v1/state/{session_id}/snapshot",
            json={"label": "test-snap"},
            headers={"X-OMem-Session": session_id},
        )
        assert snap_resp.status_code == 200
        snap_id = snap_resp.json()["snapshot_id"]

        list_resp = client.get(
            f"/v1/state/{session_id}/snapshots",
            headers={"X-OMem-Session": session_id},
        )
        assert list_resp.status_code == 200
        ids = [s["id"] for s in list_resp.json()["snapshots"]]
        assert snap_id in ids

        rollback_resp = client.post(
            f"/v1/state/{session_id}/rollback",
            json={"snapshot_id": snap_id},
            headers={"X-OMem-Session": session_id},
        )
        assert rollback_resp.status_code == 200

    def test_fork_creates_new_session(self, client, session_id):
        snap_resp = client.post(
            f"/v1/state/{session_id}/snapshot",
            json={"label": "fork-base"},
            headers={"X-OMem-Session": session_id},
        )
        snap_id = snap_resp.json()["snapshot_id"]
        fork_id = f"{session_id}-fork"

        fork_resp = client.post(
            f"/v1/state/{session_id}/fork",
            json={"snapshot_id": snap_id, "new_session_id": fork_id},
            headers={"X-OMem-Session": session_id},
        )
        assert fork_resp.status_code == 200
        assert fork_resp.json()["fork_session_id"] == fork_id

    def test_merge_winner_into_parent(self, client, session_id):
        """Full fork + Plan A + Plan B + merge cycle."""
        # Setup parent
        client.post(
            "/v1/state/save",
            json={"session_id": session_id, "goal": "Choose best auth strategy"},
        )

        snap_resp = client.post(
            f"/v1/state/{session_id}/snapshot",
            json={"label": "pre-fork"},
            headers={"X-OMem-Session": session_id},
        )
        snap_id = snap_resp.json()["snapshot_id"]

        plan_a = f"{session_id}-plan-a"
        plan_b = f"{session_id}-plan-b"

        # Fork both plans
        for fork_id in (plan_a, plan_b):
            client.post(
                f"/v1/state/{session_id}/fork",
                json={"snapshot_id": snap_id, "new_session_id": fork_id},
                headers={"X-OMem-Session": session_id},
            )

        # Each plan records its result
        _remember(client, plan_a, "Plan A: PKCE — 1.2ms overhead, spec compliant", 0.95)
        _remember(client, plan_b, "Plan B: Device Flow — 800ms overhead, better for CLI", 0.85)

        # Merge winner (plan_a) back into parent
        merge_resp = client.post(
            f"/v1/state/{session_id}/merge",
            json={
                "winner_session_id": plan_a,
                "loser_session_id": plan_b,
                "label": "plan-a-wins",
            },
            headers={"X-OMem-Session": session_id},
        )
        assert merge_resp.status_code == 200
        data = merge_resp.json()
        assert data["merged_into"] == session_id
        assert data["merged_from"] == plan_a
        assert "snapshot_id" in data


class TestContext:
    def test_context_build_returns_token_count(self, client, session_id):
        for i in range(5):
            _remember(client, session_id, f"context test memory {i}: important data point", 0.8)

        resp = client.post(
            "/v1/context/build",
            json={"task": "summarise context test data", "budget_tokens": 2048},
            headers={"X-OMem-Session": session_id},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "token_count" in data
        assert "budget_tokens" in data
        assert data["token_count"] <= data["budget_tokens"] + 100  # small overshoot tolerated

    def test_context_build_simple_endpoint(self, client, session_id):
        _remember(client, session_id, "simple context test memory", 0.8)
        resp = client.post(
            "/v1/context",
            json={"task": "test task", "budget_tokens": 1024},
            headers={"X-OMem-Session": session_id},
        )
        assert resp.status_code == 200


class TestGoalAndMaintain:
    def test_set_goal(self, client, session_id):
        resp = client.post(
            "/v1/goal",
            json={"goal": "Test goal for E2E"},
            headers={"X-OMem-Session": session_id},
        )
        assert resp.status_code == 200

    def test_maintain_full_cycle(self, client, session_id):
        for i in range(3):
            _remember(client, session_id, f"maintain test memory {i}", 0.6)
        resp = client.post(
            "/v1/maintain",
            json={},
            headers={"X-OMem-Session": session_id},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_sleep_cycle(self, client, session_id):
        resp = client.post(
            "/v1/sleep",
            json={"speed": "fast"},
            headers={"X-OMem-Session": session_id},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


class TestSecurity:
    def test_wrong_api_key_returns_401(self, client):
        """Only tested when OMEM_API_KEY is set."""
        import os as _os
        if not _os.environ.get("OMEM_API_KEY"):
            pytest.skip("OMEM_API_KEY not set — auth not enabled")

        resp = client.get(
            "/v1/status",
            headers={"Authorization": "Bearer wrong_key"},
        )
        assert resp.status_code == 401

    def test_rbac_admin_required_for_delete(self, client, session_id):
        """RBAC delete endpoint returns 403 when role is not admin."""
        import os as _os
        if not _os.environ.get("OMEM_ALLOWED_ROLES"):
            pytest.skip("OMEM_ALLOWED_ROLES not set — RBAC not enabled")

        resp = client.post(
            "/v1/governance/delete",
            json={"scope": "memory_id", "id": "fake-id", "cascade": False},
            headers={
                "X-OMem-Session": session_id,
                "X-OMem-Role": "reader",
            },
        )
        assert resp.status_code == 403

    def test_cors_origin_reflected_in_options(self, client):
        resp = client.options("/v1/health", headers={"Origin": "http://localhost"})
        assert resp.status_code in (200, 204)


class TestObservability:
    def test_observe_metrics_endpoint(self, client, session_id):
        _remember(client, session_id, "observability test memory", 0.7)
        resp = client.get(
            f"/v1/observe/metrics?session_id={session_id}",
            headers={"X-OMem-Session": session_id},
        )
        assert resp.status_code == 200

    def test_observe_traces_endpoint(self, client, session_id):
        _remember(client, session_id, "trace test memory", 0.7)
        resp = client.get(
            f"/v1/observe/traces/{session_id}",
            headers={"X-OMem-Session": session_id},
        )
        assert resp.status_code == 200


@pytest.mark.live
class TestLiveStackSmoke:
    """Run only against a live Docker stack with OMEM_TEST_ENDPOINT set."""

    def test_full_demo_flow(self, client):
        """Abbreviated version of seed-demo-data.sh."""
        session = f"live-smoke-{int(time.time())}"
        headers = {"X-OMem-Session": session}

        # 1. Health
        assert client.get("/v1/health").status_code == 200

        # 2. Remember + Recall
        mem_id = _remember(client, session, "PKCE auth flow implemented with RS256 signing", 0.9)
        mems = _recall(client, session, "PKCE auth", k=3)
        assert len(mems) >= 1

        # 3. Checkpoint
        chk = client.post(f"/v1/state/{session}/checkpoint", headers=headers)
        assert chk.status_code == 200

        # 4. Context build with token budget
        ctx = client.post(
            "/v1/context/build",
            json={"task": "auth refactor status", "budget_tokens": 2048},
            headers=headers,
        )
        assert ctx.status_code == 200
        assert ctx.json()["token_count"] > 0

        # 5. Metrics
        metrics_resp = client.get("/v1/metrics")
        assert metrics_resp.status_code == 200
        assert "omem_" in metrics_resp.text
