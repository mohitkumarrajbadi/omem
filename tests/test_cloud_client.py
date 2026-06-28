"""Tests for OMem Cloud client and agent pool."""

from __future__ import annotations

import json
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from omem.cloud.client import OMemCloudClient
from omem.cloud.exceptions import CloudAuthError, CloudError
from omem.cloud.pool import AgentPool, reset_pool
from omem.cloud.config import CloudServerConfig


@pytest.fixture(autouse=True)
def _reset_pool():
    reset_pool()
    yield
    reset_pool()


def _mock_response(status_code: int, payload: Dict[str, Any]) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.is_success = 200 <= status_code < 300
    resp.content = json.dumps(payload).encode()
    resp.json.return_value = payload
    resp.text = json.dumps(payload)
    return resp


def test_cloud_client_remember_minimal_body():
    """Content-only body — CLI simplicity."""
    client = OMemCloudClient("http://testserver", session_id="s1")

    with patch.object(
        client._client,
        "request",
        return_value=_mock_response(200, {"memory_id": "mem-1"}),
    ) as mock_req:
        mem_id = client.remember("just content")

    assert mem_id == "mem-1"
    body = mock_req.call_args.kwargs["json"]
    assert body == {"content": "just content", "session_id": "s1", "namespace": "default"}
    client.close()


def test_cloud_client_status():
    client = OMemCloudClient("http://testserver")
    with patch.object(
        client._client,
        "request",
        return_value=_mock_response(200, {"backend": "cloud"}),
    ):
        data = client.status()
    assert data["backend"] == "cloud"
    client.close()


    client = OMemCloudClient("http://testserver", api_key="")
    calls = []

    def handler(method, url, **kwargs):
        path = getattr(url, "path", str(url))
        if not path.startswith("/"):
            path = "/" + path.split("/", 3)[-1] if "://" in str(url) else path
        calls.append((method, path))
        if path.endswith("/v1/remember") or path == "/v1/remember":
            return _mock_response(200, {"memory_id": "mem-1", "session_id": "s1"})
        if path.endswith("/v1/recall") or path == "/v1/recall":
            return _mock_response(
                200,
                {
                    "memories": [
                        {
                            "id": "mem-1",
                            "content": "hello",
                            "importance": 0.8,
                            "score": 0.9,
                            "type": "EPISODIC",
                            "namespace": "default",
                            "timestamp": 1.0,
                        }
                    ],
                    "count": 1,
                },
            )
        return _mock_response(404, {"detail": "not found"})

    with patch.object(client._client, "request", side_effect=handler):
        mem_id = client.remember("hello", session_id="s1")
        rows = client.recall("hello", session_id="s1")

    assert mem_id == "mem-1"
    assert len(rows) == 1
    assert rows[0]["content"] == "hello"
    assert ("POST", "/v1/remember") in calls
    assert ("POST", "/v1/recall") in calls
    client.close()


def test_cloud_client_auth_error():
    client = OMemCloudClient("http://testserver", api_key="bad")

    with patch.object(
        client._client,
        "request",
        return_value=_mock_response(401, {"detail": "Invalid or missing API key"}),
    ):
        with pytest.raises(CloudAuthError):
            client.health()
    client.close()


def test_cloud_client_state_checkpoint():
    client = OMemCloudClient("http://testserver")

    with patch.object(
        client._client,
        "request",
        return_value=_mock_response(200, {"checkpoint_id": "chk-99", "session_id": "s1"}),
    ):
        chk = client.state_checkpoint("s1")

    assert chk == "chk-99"
    client.close()


def test_cloud_client_requires_endpoint():
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(ValueError, match="endpoint is required"):
            OMemCloudClient()


def test_agent_pool_reuses_instances():
    cfg = CloudServerConfig(backend="memory", db_path=":memory:", agent_pool_size=4)
    pool = AgentPool(cfg)

    with patch("omem.cloud.pool.AgentState") as mock_cls:
        inst_a = MagicMock(ping=MagicMock(return_value=True))
        inst_b = MagicMock(ping=MagicMock(return_value=True))
        mock_cls.side_effect = [inst_a, inst_b]
        a1 = pool.get("session-a", "ns1")
        a2 = pool.get("session-a", "ns1")
        a3 = pool.get("session-b", "ns1")

    assert a1 is a2
    assert a1 is not a3
    assert mock_cls.call_count == 2


def test_remote_agent_state_routing():
    from omem.agent_config import AgentConfig
    from omem.cloud.remote import RemoteAgentState

    cfg = AgentConfig(session_id="remote-1", endpoint="http://localhost:8080")
    agent = RemoteAgentState(config=cfg)

    with patch.object(agent._client, "remember", return_value="mem-x") as mock_remember:
        mid = agent.remember("cloud memory")

    assert mid == "mem-x"
    mock_remember.assert_called_once()
    agent.close()


def test_agent_state_routes_to_remote_when_endpoint_set(monkeypatch):
    from omem.agent_state import AgentState
    from omem.cloud.remote import RemoteAgentState

    monkeypatch.setenv("OMEM_ENDPOINT", "http://localhost:8080")
    monkeypatch.delenv("OMEM_API_KEY", raising=False)
    agent = AgentState(session_id="x")

    assert isinstance(agent, RemoteAgentState)
    agent.close()
