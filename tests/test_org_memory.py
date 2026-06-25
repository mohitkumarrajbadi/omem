"""Tests for Phase 10 — OrgMemoryOS and NamespaceResolver.

Validates: namespace parsing, parent hierarchy, scope resolution,
scoped recall, memory sharing/promotion, and AgentState integration.
"""

from __future__ import annotations

import pytest

from omem.memory.org.namespace import NamespaceResolver

# ──────────────────────────────────────────────────────────────────────────────
# NamespaceResolver
# ──────────────────────────────────────────────────────────────────────────────


class TestNamespaceResolverParse:
    def test_parse_global(self):
        node = NamespaceResolver.parse("global")
        assert node.kind == "global"
        assert node.raw == "global"

    def test_parse_personal(self):
        node = NamespaceResolver.parse("personal/alice")
        assert node.kind == "personal"
        assert node.user_id == "alice"

    def test_parse_team(self):
        node = NamespaceResolver.parse("team/eng")
        assert node.kind == "team"
        assert node.team_id == "eng"

    def test_parse_org(self):
        node = NamespaceResolver.parse("org/acme")
        assert node.kind == "org"
        assert node.org_id == "acme"
        assert node.team_id is None

    def test_parse_org_with_team(self):
        node = NamespaceResolver.parse("org/acme/team/eng")
        assert node.kind == "org"
        assert node.org_id == "acme"
        assert node.team_id == "eng"

    def test_parse_leading_slash(self):
        node = NamespaceResolver.parse("/team/eng")
        assert node.kind == "team"

    def test_parse_unknown(self):
        node = NamespaceResolver.parse("custom/namespace")
        assert node.kind == "other"
        assert node.raw == "custom/namespace"


class TestNamespaceResolverParents:
    def test_global_has_no_parents(self):
        parents = NamespaceResolver.parents("global")
        assert "global" not in parents or len(parents) == 0

    def test_personal_parent_is_global(self):
        parents = NamespaceResolver.parents("personal/alice")
        assert "global" in parents

    def test_team_parent_is_global(self):
        parents = NamespaceResolver.parents("team/eng")
        assert "global" in parents

    def test_org_team_parent_is_org(self):
        parents = NamespaceResolver.parents("org/acme/team/eng")
        assert "org/acme" in parents
        assert "global" in parents


class TestNamespaceResolverScoped:
    def test_personal_scope(self):
        ns = NamespaceResolver.scoped("personal", user_id="alice")
        assert ns == ["personal/alice"]

    def test_personal_scope_no_user_id(self):
        ns = NamespaceResolver.scoped("personal")
        assert ns == []

    def test_team_scope(self):
        ns = NamespaceResolver.scoped("team", team_id="eng", org_id="acme")
        assert "team/eng" in ns
        assert "org/acme" in ns
        assert "global" in ns

    def test_team_scope_no_org(self):
        ns = NamespaceResolver.scoped("team", team_id="eng")
        assert "team/eng" in ns
        assert "global" in ns
        assert "org" not in str(ns)

    def test_org_scope(self):
        ns = NamespaceResolver.scoped("org", org_id="acme")
        assert "org/acme" in ns
        assert "global" in ns

    def test_global_scope(self):
        ns = NamespaceResolver.scoped("global")
        assert ns == ["global"]

    def test_all_scope(self):
        ns = NamespaceResolver.scoped("all", user_id="alice", team_id="eng", org_id="acme")
        assert "personal/alice" in ns
        assert "team/eng" in ns
        assert "org/acme" in ns
        assert "global" in ns

    def test_literal_namespace_scope(self):
        ns = NamespaceResolver.scoped("custom/ns")
        assert ns == ["custom/ns"]

    def test_no_duplicates(self):
        ns = NamespaceResolver.scoped("all", user_id="u", team_id="t", org_id="o")
        assert len(ns) == len(set(ns))


class TestNamespaceResolverBuild:
    def test_build_personal(self):
        ns = NamespaceResolver.build("personal", user_id="alice")
        assert ns == "personal/alice"

    def test_build_team(self):
        ns = NamespaceResolver.build("team", team_id="eng")
        assert ns == "team/eng"

    def test_build_org(self):
        ns = NamespaceResolver.build("org", org_id="acme")
        assert ns == "org/acme"

    def test_build_global(self):
        assert NamespaceResolver.build("global") == "global"

    def test_build_personal_requires_user_id(self):
        with pytest.raises(ValueError):
            NamespaceResolver.build("personal")

    def test_build_team_requires_team_id(self):
        with pytest.raises(ValueError):
            NamespaceResolver.build("team")


# ──────────────────────────────────────────────────────────────────────────────
# OrgMemoryOS — through AgentState
# ──────────────────────────────────────────────────────────────────────────────


class TestOrgMemoryOS:
    @pytest.fixture
    def agent(self):
        from omem import AgentState
        return AgentState(session_id="org-test", backend="memory")

    def test_org_accessible(self, agent):
        from omem.memory.org.layer import OrgMemoryOS
        assert isinstance(agent.org, OrgMemoryOS)

    def test_remember_personal_scope(self, agent):
        agent.org._user_id = "alice"
        mid = agent.org.remember("Alice's personal note", scope="personal")
        assert mid  # returned a memory ID

    def test_remember_team_scope(self, agent):
        agent.org._team_id = "eng"
        mid = agent.org.remember("Team API rate limit", scope="team")
        assert mid

    def test_remember_org_scope(self, agent):
        agent.org._org_id = "acme"
        mid = agent.org.remember("Org-wide oncall policy", scope="org")
        assert mid

    def test_remember_literal_namespace(self, agent):
        mid = agent.org.remember("Special memo", scope="custom/docs")
        assert mid

    def test_recall_scoped_team_finds_org_memory(self, agent):
        agent.org._team_id = "eng"
        agent.org._org_id = "acme"
        # Store a memory at org level
        agent.org.remember("API v2 deprecation notice", scope="org")
        # Recall with team scope (should search team + org + global)
        results = agent.org.recall_scoped("API deprecation", scope="team", k=5)
        assert isinstance(results, list)

    def test_recall_scoped_deduplication(self, agent):
        agent.org._user_id = "alice"
        agent.org._team_id = "eng"
        # A memory in personal scope
        agent.org.remember("Alice knows Python", scope="personal")
        results_all = agent.org.recall_scoped("Alice Python", scope="all", k=10)
        # IDs should be unique
        ids = [getattr(m, "id", None) for m in results_all]
        non_none_ids = [i for i in ids if i is not None]
        assert len(non_none_ids) == len(set(non_none_ids))

    def test_namespaces_returns_list(self, agent):
        agent.org._user_id = "alice"
        agent.org._team_id = "eng"
        agent.org._org_id = "acme"
        infos = agent.org.namespaces()
        assert isinstance(infos, list)
        ns_strings = [i.namespace for i in infos]
        assert "personal/alice" in ns_strings
        assert "team/eng" in ns_strings
        assert "org/acme" in ns_strings
        assert "global" in ns_strings

    def test_namespaces_memory_count(self, agent):
        agent.org._team_id = "eng"
        agent.org.remember("Memory in team", scope="team")
        infos = agent.org.namespaces()
        team_info = next((i for i in infos if i.namespace == "team/eng"), None)
        assert team_info is not None
        assert team_info.memory_count >= 1

    def test_namespace_summary(self, agent):
        agent.org._user_id = "bob"
        s = agent.org.namespace_summary()
        assert "total_namespaces" in s
        assert "total_memories" in s
        assert "namespaces" in s

    def test_share_memory_to_team(self, agent):
        agent.org._user_id = "alice"
        agent.org._team_id = "eng"
        # Write personal memory
        mid = agent.org.remember("Alice's unique team insight", scope="personal")
        # Promote to team
        result = agent.org.share(mid, target_namespace="team/eng")
        assert result.original_id == mid
        assert result.new_id  # returns a valid (non-empty) memory ID
        assert result.target_namespace == "team/eng"
        assert result.source_namespace is not None

    def test_share_nonexistent_memory_raises(self, agent):
        with pytest.raises(ValueError, match="not found"):
            agent.org.share("mem-nonexistent-abc", target_namespace="team/eng")

    def test_promote_alias(self, agent):
        agent.org._team_id = "eng"
        mid = agent.org.remember("Team insight", scope="team")
        result = agent.org.promote(mid, to="org")
        assert result.new_id is not None

    def test_with_identity_does_not_mutate_original(self, agent):
        agent.org._user_id = "alice"
        new_org = agent.org.with_identity(user_id="bob")
        assert agent.org.user_id == "alice"
        assert new_org.user_id == "bob"


# ──────────────────────────────────────────────────────────────────────────────
# Integration: AgentState.share() shorthand
# ──────────────────────────────────────────────────────────────────────────────


class TestAgentStateShare:
    def test_share_shorthand(self):
        from omem import AgentState
        agent = AgentState(session_id="share-test", backend="memory")
        mid = agent.remember("Important finding")
        result = agent.share(mid, target_namespace="team/eng")
        assert result["original_id"] == mid
        assert result["new_id"]  # returns a valid memory ID
        assert result["target_namespace"] == "team/eng"

    def test_share_emits_observe_trace(self):
        from omem import AgentState
        agent = AgentState(session_id="share-obs", backend="memory")
        mid = agent.remember("Shared memory")
        agent.share(mid, target_namespace="org/acme")
        m = agent.observe.metrics(session_id="share-obs")
        assert m["share_count"] == 1

    def test_share_records_provenance(self):
        from omem import AgentState
        agent = AgentState(session_id="share-prov", backend="memory")
        mid = agent.remember("Provenance share test")
        result = agent.share(mid, target_namespace="team/ops")
        # The new memory should have a provenance record
        chain = agent.provenance.trace(result["new_id"])
        assert len(chain.events) >= 1
