"""Alpha feature isolation — AST code index gated by OMEM_ENABLE_EXPERIMENTAL_AST."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _clear_ast_flag(monkeypatch):
    monkeypatch.delenv("OMEM_ENABLE_EXPERIMENTAL_AST", raising=False)


def test_ast_disabled_by_default():
    from omem.experimental import ast_enabled

    assert ast_enabled() is False


def test_knowledge_package_does_not_export_ast_by_default():
    import omem.knowledge as knowledge

    assert "ProjectIngester" not in knowledge.__all__
    with pytest.raises(RuntimeError, match="experimental"):
        _ = knowledge.ProjectIngester


def test_omem_ingest_requires_flag(tmp_path, monkeypatch):
    monkeypatch.setenv("OMEM_EMBEDDER", "hash")
    from omem.api import OMem

    m = OMem(backend="sqlite", db_path=str(tmp_path / "t.db"))
    with pytest.raises(RuntimeError, match="OMEM_ENABLE_EXPERIMENTAL_AST"):
        m.ingest_project(str(tmp_path))


def test_ast_index_import_requires_flag(monkeypatch):
    with pytest.raises(RuntimeError, match="experimental"):
        from omem.experimental import ast_index  # noqa: F401


def test_ast_enabled_allows_api(tmp_path, monkeypatch):
    monkeypatch.setenv("OMEM_ENABLE_EXPERIMENTAL_AST", "1")
    monkeypatch.setenv("OMEM_EMBEDDER", "hash")
    from omem.api import OMem
    from omem.experimental import ast_enabled

    assert ast_enabled() is True
    (tmp_path / "mod.py").write_text("def hello():\n    return 1\n", encoding="utf-8")
    m = OMem(backend="sqlite", db_path=str(tmp_path / "t.db"))
    n = m.ingest_project(str(tmp_path), namespace="project")
    assert n >= 1
