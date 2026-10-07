"""GovernedMem0 audits writes, access, and erasure without a live Mem0 backend."""

from __future__ import annotations

import json
import sys
from unittest.mock import MagicMock

import pytest

from omem import AgentState


@pytest.fixture
def agent(monkeypatch):
    monkeypatch.setenv("OMEM_EMBEDDER", "hash")
    return AgentState(session_id="gov-mem0-test", backend="memory")


@pytest.fixture
def fake_mem0():
    m = MagicMock()
    m.add.return_value = {
        "results": [{"id": "m-1", "memory": "Wire beneficiary is acct-100"}]
    }
    m.search.return_value = {
        "results": [{"id": "m-1", "memory": "Wire beneficiary is acct-100"}]
    }
    m.delete.return_value = True
    m.delete_all.return_value = True
    return m


@pytest.fixture
def mem0_installed(monkeypatch):
    """Satisfy _require_mem0 without installing mem0ai."""
    package = MagicMock()
    package.Memory = MagicMock()
    monkeypatch.setitem(sys.modules, "mem0", package)
    return package


def test_import_error_without_mem0(monkeypatch, fake_mem0):
    monkeypatch.delitem(sys.modules, "mem0", raising=False)

    import omem.adapters.mem0 as mod

    real_import = __import__

    def blocked(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "mem0" or name.startswith("mem0."):
            raise ImportError("No module named 'mem0'")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("builtins.__import__", blocked)
    with pytest.raises(ImportError, match=r"omem-os\[mem0\]"):
        mod.GovernedMem0(fake_mem0)


def test_add_search_delete_write_audit(agent, fake_mem0, mem0_installed):
    from omem.adapters.mem0 import GovernedMem0

    store = GovernedMem0(fake_mem0, agent=agent)
    store.add(
        "Wire beneficiary is acct-100",
        user_id="u1",
        provenance={
            "source": "verified_erp",
            "actor": "cfo",
            "sensitivity": "pii",
        },
    )
    fake_mem0.add.assert_called_once()
    _, kwargs = fake_mem0.add.call_args
    assert kwargs["user_id"] == "u1"
    assert kwargs["metadata"]["source"] == "verified_erp"
    assert kwargs["metadata"]["actor"] == "cfo"
    assert "omem_provenance" in kwargs["metadata"]

    store.search("beneficiary", user_id="u1")
    fake_mem0.search.assert_called()

    store.delete("m-1", user_id="u1")
    fake_mem0.delete.assert_called_with("m-1", user_id="u1")

    body = store.export_audit(format="json", limit=100)
    payload = json.loads(body)
    entries = payload["entries"] if isinstance(payload, dict) else payload
    ops = {e["operation"] for e in entries}
    assert "memory_write" in ops
    assert "memory_accessed" in ops
    assert "memory_erasure" in ops


def test_delete_all_logs_bulk_erasure(agent, fake_mem0, mem0_installed):
    from omem.adapters.mem0 import GovernedMem0

    store = GovernedMem0(fake_mem0, agent=agent)
    store.delete_all(user_id="u1")
    fake_mem0.delete_all.assert_called_once()
    payload = json.loads(store.export_audit(format="json", limit=50))
    entries = payload["entries"] if isinstance(payload, dict) else payload
    assert any(e["operation"] == "memory_erasure_all" for e in entries)


def test_lazy_export_from_adapters_package(mem0_installed, fake_mem0, agent):
    from omem.adapters import GovernedMem0

    store = GovernedMem0(fake_mem0, agent=agent)
    assert store.mem0 is fake_mem0
    assert store.agent is agent
