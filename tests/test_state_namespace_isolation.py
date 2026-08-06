"""Cross-namespace state isolation — guards the multi-tenant IDOR class."""

from __future__ import annotations

import pytest

from omem.state import (
    SessionNamespaceConflictError,
    SessionNotFoundError,
    StateOS,
)
from omem.types import StatePayload


@pytest.fixture
def state() -> StateOS:
    return StateOS()  # in-memory, no namespace bound (OSS local)


def test_load_scoped_by_namespace(state: StateOS) -> None:
    state.save("sess-1", StatePayload(session_id="sess-1", namespace="org-a/shared", goal="A"))
    assert state._backend.load_session("sess-1", namespace="org-a/shared") is not None
    assert state._backend.load_session("sess-1", namespace="org-b/shared") is None


def test_bound_stateos_rejects_foreign_session() -> None:
    shared = StateOS()
    shared.save("sess-1", StatePayload(session_id="sess-1", namespace="org-a/shared", goal="secret"))

    tenant_b = StateOS(backend=shared._backend, namespace="org-b/shared")
    with pytest.raises(SessionNotFoundError):
        tenant_b.load("sess-1")


def test_get_or_create_conflict_on_cross_namespace() -> None:
    shared = StateOS()
    shared.get_or_create("sess-1", namespace="org-a/shared")

    tenant_b = StateOS(backend=shared._backend, namespace="org-b/shared")
    with pytest.raises(SessionNamespaceConflictError):
        tenant_b.get_or_create("sess-1", namespace="org-b/shared")


def test_save_refuses_namespace_overwrite(state: StateOS) -> None:
    state.save("sess-1", StatePayload(session_id="sess-1", namespace="org-a", goal="A"))
    with pytest.raises(SessionNamespaceConflictError):
        state.save("sess-1", StatePayload(session_id="sess-1", namespace="org-b", goal="B"))


def test_snapshot_and_rollback_scoped() -> None:
    backend_owner = StateOS()
    backend_owner.get_or_create("sess-1", namespace="org-a")
    backend_owner.set_goal("sess-1", "keep-secret")
    # Bind namespace for snapshot path
    a = StateOS(backend=backend_owner._backend, namespace="org-a")
    snap = a.snapshot("sess-1", label="t0")

    b = StateOS(backend=backend_owner._backend, namespace="org-b")
    with pytest.raises(Exception):
        b.rollback(snap.id)
