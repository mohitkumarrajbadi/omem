"""Tests for shared namespace resolution and sticky override."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _clean_ns_env(monkeypatch, tmp_path: Path):
    for var in ("OMEM_NS", "OMEM_NAMESPACE", "OMEM_PROJECT_ROOT"):
        monkeypatch.delenv(var, raising=False)
    home = tmp_path / "omem-home"
    home.mkdir()
    monkeypatch.setattr("omem.namespace_resolve.omem_home", lambda: str(home))
    yield home


def test_env_beats_sticky(monkeypatch, _clean_ns_env):
    from omem import namespace_resolve as nr

    nr.write_sticky("sticky-ns")
    monkeypatch.setenv("OMEM_NS", "env-ns")
    res = nr.resolve_active_namespace()
    assert res.namespace == "env-ns"
    assert res.source == "env"


def test_sticky_file(monkeypatch, _clean_ns_env):
    from omem import namespace_resolve as nr

    assert nr.read_sticky() is None
    nr.write_sticky("trading")
    res = nr.resolve_active_namespace()
    assert res.namespace == "trading"
    assert res.source == "sticky"
    assert nr.clear_sticky() is True
    res2 = nr.resolve_active_namespace(cwd=str(_clean_ns_env))
    assert res2.namespace
    assert res2.source in ("cwd", "default", "git")


def test_git_root_basename(tmp_path: Path, monkeypatch, _clean_ns_env):
    from omem import namespace_resolve as nr

    repo = tmp_path / "neteng-app"
    repo.mkdir()
    (repo / ".git").mkdir()
    nested = repo / "app" / "core"
    nested.mkdir(parents=True)
    res = nr.resolve_active_namespace(cwd=str(nested))
    assert res.namespace == "neteng-app"
    assert res.source == "git"
    assert res.git_root == str(repo)


def test_normalize_scope_personal(monkeypatch, _clean_ns_env):
    from omem import namespace_resolve as nr

    monkeypatch.setenv("OMEM_NS", "trading")
    assert nr.normalize_scope_target(scope="personal") == "personal"
    assert nr.normalize_scope_target(is_global=True) == "personal"
    assert nr.normalize_scope_target(scope="project") == "trading"
    assert nr.normalize_scope_target(explicit_namespace="custom") == "custom"


def test_smart_bypasses_sticky_personal_inside_git(tmp_path: Path, monkeypatch, _clean_ns_env):
    from omem import namespace_resolve as nr

    repo = tmp_path / "trading"
    repo.mkdir()
    (repo / ".git").mkdir()
    nr.write_sticky("personal")
    res = nr.resolve_active_namespace(cwd=str(repo))
    assert res.namespace == "trading"
    assert res.source == "git"
    assert res.bypassed_bridge_pin == "personal"


def test_force_namespace_keeps_personal_pin(tmp_path: Path, monkeypatch, _clean_ns_env):
    from omem import namespace_resolve as nr

    repo = tmp_path / "trading"
    repo.mkdir()
    (repo / ".git").mkdir()
    monkeypatch.setenv("OMEM_NAMESPACE", "personal")
    monkeypatch.setenv("OMEM_FORCE_NAMESPACE", "1")
    res = nr.resolve_active_namespace(cwd=str(repo))
    assert res.namespace == "personal"
    assert res.source == "env"
