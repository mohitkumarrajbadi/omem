"""Tests for Phase 8 — GovernanceOS.

Validates: retention policy registration and enforcement, audit delegation,
deletion scopes, RBAC primitives, and integration with AgentState.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from omem.governance.layer import (
    DeletionReport,
    GovernanceOS,
    RetentionPolicy,
    Role,
    ROLE_ADMIN,
    ROLE_EDITOR,
    ROLE_VIEWER,
)


# ──────────────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def gov_no_omem():
    """GovernanceOS without an OMem instance (for policy/audit tests)."""
    return GovernanceOS()


@pytest.fixture
def mock_omem():
    m = MagicMock()
    m.delete.return_value = True
    m.all.return_value = []
    return m


@pytest.fixture
def mock_state():
    m = MagicMock()
    m.list_sessions.return_value = []
    return m


@pytest.fixture
def gov(mock_omem, mock_state):
    return GovernanceOS(omem=mock_omem, state=mock_state)


# ──────────────────────────────────────────────────────────────────────────────
# RetentionPolicy
# ──────────────────────────────────────────────────────────────────────────────


class TestRetentionPolicy:
    def test_matches_exact(self):
        p = RetentionPolicy("org/acme")
        assert p.matches("org/acme") is True

    def test_matches_glob_star(self):
        p = RetentionPolicy("org/acme/*")
        assert p.matches("org/acme/team") is True
        assert p.matches("org/other/team") is False

    def test_matches_wildcard_all(self):
        p = RetentionPolicy("*")
        assert p.matches("org/acme") is True
        assert p.matches("personal/alice") is True

    def test_not_matches(self):
        p = RetentionPolicy("team/*")
        assert p.matches("org/acme") is False

    def test_to_dict(self):
        p = RetentionPolicy("ns/*", max_age_days=30, max_count=100)
        d = p.to_dict()
        assert d["namespace_pattern"] == "ns/*"
        assert d["max_age_days"] == 30
        assert d["max_count"] == 100


# ──────────────────────────────────────────────────────────────────────────────
# RBAC: Role
# ──────────────────────────────────────────────────────────────────────────────


class TestRole:
    def test_admin_can_all(self):
        assert ROLE_ADMIN.can("read") is True
        assert ROLE_ADMIN.can("write") is True
        assert ROLE_ADMIN.can("delete") is True
        assert ROLE_ADMIN.can("admin") is True

    def test_editor_can_read_write_delete(self):
        assert ROLE_EDITOR.can("read") is True
        assert ROLE_EDITOR.can("write") is True
        assert ROLE_EDITOR.can("delete") is True
        assert ROLE_EDITOR.can("admin") is False

    def test_viewer_can_only_read(self):
        assert ROLE_VIEWER.can("read") is True
        assert ROLE_VIEWER.can("write") is False
        assert ROLE_VIEWER.can("delete") is False

    def test_namespace_restriction(self):
        role = Role("limited", namespaces=["team/eng/*"], permissions=["read"])
        assert role.can("read", "team/eng/docs") is True
        assert role.can("read", "team/other/docs") is False

    def test_to_dict(self):
        d = ROLE_EDITOR.to_dict()
        assert d["name"] == "editor"
        assert "write" in d["permissions"]


# ──────────────────────────────────────────────────────────────────────────────
# Policy management
# ──────────────────────────────────────────────────────────────────────────────


class TestGovernancePolicies:
    def test_set_and_list_policy(self, gov_no_omem):
        p = RetentionPolicy("org/*", max_age_days=90)
        gov_no_omem.set_policy(p)
        policies = gov_no_omem.list_policies()
        assert len(policies) == 1
        assert policies[0].namespace_pattern == "org/*"

    def test_set_policy_replaces_same_pattern(self, gov_no_omem):
        gov_no_omem.set_policy(RetentionPolicy("org/*", max_age_days=90))
        gov_no_omem.set_policy(RetentionPolicy("org/*", max_age_days=30))
        policies = gov_no_omem.list_policies()
        assert len(policies) == 1
        assert policies[0].max_age_days == 30

    def test_set_multiple_policies(self, gov_no_omem):
        gov_no_omem.set_policy(RetentionPolicy("org/*", max_age_days=90))
        gov_no_omem.set_policy(RetentionPolicy("team/*", max_count=1000))
        assert len(gov_no_omem.list_policies()) == 2

    def test_remove_policy(self, gov_no_omem):
        gov_no_omem.set_policy(RetentionPolicy("org/*", max_age_days=90))
        removed = gov_no_omem.remove_policy("org/*")
        assert removed is True
        assert len(gov_no_omem.list_policies()) == 0

    def test_remove_nonexistent_policy(self, gov_no_omem):
        assert gov_no_omem.remove_policy("nonexistent/*") is False


# ──────────────────────────────────────────────────────────────────────────────
# Retention enforcement
# ──────────────────────────────────────────────────────────────────────────────


class TestRetentionEnforcement:
    def test_enforce_with_no_omem_returns_error(self, gov_no_omem):
        gov_no_omem.set_policy(RetentionPolicy("*", max_age_days=1))
        report = gov_no_omem.enforce_retention()
        assert len(report.errors) > 0

    def test_enforce_no_policies_is_noop(self, gov):
        report = gov.enforce_retention()
        assert report.policies_applied == 0
        assert report.memories_evicted == 0

    def test_enforce_age_policy_evicts_old_memories(self, gov, mock_omem):
        old_memory = MagicMock()
        old_memory.id = "old-mem"
        old_memory.namespace = "team/eng"
        old_memory.created_at = time.time() - 100 * 86400  # 100 days old
        old_memory.importance = 0.5
        old_memory.tier = None
        mock_omem.all.return_value = [old_memory]

        gov.set_policy(RetentionPolicy("team/eng", max_age_days=30))
        report = gov.enforce_retention()
        assert report.memories_evicted == 1
        mock_omem.delete.assert_called_once_with("old-mem")

    def test_enforce_age_policy_keeps_recent_memories(self, gov, mock_omem):
        new_memory = MagicMock()
        new_memory.id = "new-mem"
        new_memory.namespace = "team/eng"
        new_memory.created_at = time.time() - 5 * 86400  # 5 days old
        new_memory.importance = 0.5
        new_memory.tier = None
        mock_omem.all.return_value = [new_memory]

        gov.set_policy(RetentionPolicy("team/eng", max_age_days=30))
        report = gov.enforce_retention()
        assert report.memories_evicted == 0

    def test_enforce_count_policy_evicts_excess(self, gov, mock_omem):
        mems = []
        for i in range(5):
            m = MagicMock()
            m.id = f"m{i}"
            m.namespace = "org/big"
            m.created_at = time.time()
            m.importance = float(i) / 4
            m.tier = None
            mems.append(m)
        mock_omem.all.return_value = mems

        gov.set_policy(RetentionPolicy("org/big", max_count=3))
        report = gov.enforce_retention()
        # Should evict 2 (lowest importance)
        assert report.memories_evicted == 2

    def test_enforce_pattern_no_match(self, gov, mock_omem):
        mem = MagicMock()
        mem.id = "m1"
        mem.namespace = "personal/alice"
        mem.created_at = time.time() - 200 * 86400
        mem.importance = 0.5
        mem.tier = None
        mock_omem.all.return_value = [mem]

        gov.set_policy(RetentionPolicy("org/*", max_age_days=30))
        report = gov.enforce_retention()
        assert report.memories_evicted == 0


# ──────────────────────────────────────────────────────────────────────────────
# Deletion
# ──────────────────────────────────────────────────────────────────────────────


class TestDeletion:
    def test_delete_scope_no_omem_returns_error(self, gov_no_omem):
        report = gov_no_omem.delete_scope("namespace", "test-ns")
        assert len(report.errors) > 0

    def test_delete_memory_id(self, gov, mock_omem):
        mock_omem.delete.return_value = True
        report = gov.delete_scope("memory_id", "mem-abc")
        assert report.deleted_memories == 1
        mock_omem.delete.assert_called_with("mem-abc")

    def test_delete_namespace_lists_and_deletes(self, gov, mock_omem):
        mems = [MagicMock(id=f"m{i}") for i in range(3)]
        mock_omem.all.return_value = mems
        report = gov.delete_scope("namespace", "team/old", cascade=False)
        assert report.deleted_memories == 3

    def test_delete_user_resolves_personal_namespace(self, gov, mock_omem):
        mems = [MagicMock(id="pu1")]
        mock_omem.all.return_value = mems
        report = gov.delete_scope("user", "alice", cascade=False)
        assert report.deleted_memories == 1

    def test_delete_unknown_scope_errors(self, gov):
        report = gov.delete_scope("planet", "earth", cascade=False)
        assert len(report.errors) > 0

    def test_deletion_report_total(self):
        r = DeletionReport(deleted_memories=5, deleted_snapshots=2)
        assert r.total_deleted == 7


# ──────────────────────────────────────────────────────────────────────────────
# RBAC registration
# ──────────────────────────────────────────────────────────────────────────────


class TestGovernanceRBAC:
    def test_register_role(self, gov_no_omem):
        role = Role("data-scientist", permissions=["read"])
        gov_no_omem.register_role(role)
        found = gov_no_omem.get_role("data-scientist")
        assert found is not None
        assert found.name == "data-scientist"

    def test_get_nonexistent_role(self, gov_no_omem):
        assert gov_no_omem.get_role("ghost") is None

    def test_list_roles_includes_builtins(self, gov_no_omem):
        roles = gov_no_omem.list_roles()
        names = {r.name for r in roles}
        assert "admin" in names
        assert "editor" in names
        assert "viewer" in names

    def test_check_permission_admin(self, gov_no_omem):
        assert gov_no_omem.check_permission("admin", "delete", "org/*") is True

    def test_check_permission_viewer_cannot_write(self, gov_no_omem):
        assert gov_no_omem.check_permission("viewer", "write", "default") is False

    def test_check_permission_unknown_role(self, gov_no_omem):
        assert gov_no_omem.check_permission("ghost", "read") is False


# ──────────────────────────────────────────────────────────────────────────────
# Integration: AgentState governance
# ──────────────────────────────────────────────────────────────────────────────


class TestAgentStateGovernance:
    def test_audit_returns_list(self):
        from omem import AgentState
        agent = AgentState(session_id="gov-test", backend="memory")
        # AuditLogger uses SQLite so no memories to audit in memory-only mode
        entries = agent.governance.audit(limit=5)
        assert isinstance(entries, list)

    def test_set_policy_does_not_raise(self):
        from omem import AgentState
        agent = AgentState(backend="memory")
        agent.governance.set_policy(RetentionPolicy("*", max_age_days=90))
        assert len(agent.governance.list_policies()) == 1

    def test_enforce_retention_with_no_memories(self):
        from omem import AgentState
        agent = AgentState(backend="memory")
        agent.governance.set_policy(RetentionPolicy("*", max_age_days=1))
        report = agent.governance.enforce_retention()
        assert report.memories_evicted == 0

    def test_check_permission_admin(self):
        from omem import AgentState
        agent = AgentState(backend="memory")
        assert agent.governance.check_permission("admin", "delete") is True
