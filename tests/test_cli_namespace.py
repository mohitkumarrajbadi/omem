"""CLI ns / use / remember --personal / recall cascade smoke."""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from omem.cli.app import cli


@pytest.fixture
def runner_env(tmp_path: Path, monkeypatch):
    for var in ("OMEM_NS", "OMEM_NAMESPACE", "OMEM_PROJECT_ROOT", "OMEM_DB"):
        monkeypatch.delenv(var, raising=False)
    home = tmp_path / "omem-home"
    home.mkdir()
    monkeypatch.setattr("omem.namespace_resolve.omem_home", lambda: str(home))
    db = tmp_path / "cli.db"
    return CliRunner(), str(db), home


def test_ns_and_use(runner_env, monkeypatch):
    runner, db, _home = runner_env
    monkeypatch.setenv("OMEM_NS", "from-env")
    result = runner.invoke(cli, ["--db-path", db, "ns", "--json"])
    assert result.exit_code == 0, result.output
    assert "from-env" in result.output

    monkeypatch.delenv("OMEM_NS", raising=False)
    result = runner.invoke(cli, ["--db-path", db, "use", "trading"])
    assert result.exit_code == 0, result.output
    assert "trading" in result.output

    result = runner.invoke(cli, ["--db-path", db, "ns"])
    assert result.exit_code == 0
    assert "trading" in result.output

    result = runner.invoke(cli, ["--db-path", db, "use", "--auto"])
    assert result.exit_code == 0


def test_remember_personal_and_recall(runner_env, monkeypatch):
    runner, db, _home = runner_env
    monkeypatch.setenv("OMEM_NS", "trading")

    result = runner.invoke(
        cli,
        ["--db-path", db, "remember", "prefer dark mode always", "--personal"],
    )
    assert result.exit_code == 0, result.output
    assert "personal" in result.output

    result = runner.invoke(
        cli,
        ["--db-path", db, "remember", "NSE BSE arb uses Zerodha MIS charges"],
    )
    assert result.exit_code == 0, result.output
    assert "trading" in result.output or "wrote_to" in result.output

    result = runner.invoke(
        cli,
        ["--db-path", db, "recall", "Zerodha MIS", "-f", "json"],
    )
    assert result.exit_code == 0, result.output
    assert "trading" in result.output or "Zerodha" in result.output
