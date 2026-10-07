"""First-run story: init seeds it, demo and lineage name the causing memory."""

import json
import os

from click.testing import CliRunner

from omem import OMem
from omem.cli import cli
from omem.demo.story import (
    ACTION_TEXT,
    LATER_ID,
    STALE_ID,
    STALE_TEXT,
    lineage_report,
    mcp_config,
    merge_cursor_mcp,
    seed_story,
)
from omem.integrations.mcp_server import lineage


def test_seed_and_lineage_names_causing_memory(tmp_path):
    brain = OMem(db_path=str(tmp_path / "brain.db"))
    assert seed_story(brain) is True
    assert seed_story(brain) is False

    report = lineage_report(brain)
    assert report["caused_by"]["id"] == STALE_ID
    assert report["caused_by"]["content"] == STALE_TEXT
    assert report["lost"]["id"] == LATER_ID
    assert "importance" in report["caused_by"]["why"] or "recency" in report["caused_by"]["why"]
    assert report["decision"]["content"] == ACTION_TEXT
    assert report["decision"]["caused_by"] == STALE_ID


def test_init_prints_mcp_line_and_seeds_empty_db(tmp_path):
    db = tmp_path / "brain.db"
    runner = CliRunner()
    result = runner.invoke(cli, ["--db-path", str(db), "init"])
    assert result.exit_code == 0, result.output
    assert "initialized" in result.output.lower()
    line = next(ln for ln in result.output.splitlines() if ln.startswith("{"))
    block = json.loads(line)
    assert block["mcpServers"]["omem"]["args"][0] == "serve"
    assert str(db) in block["mcpServers"]["omem"]["args"]

    brain = OMem(db_path=str(db))
    report = lineage_report(brain)
    assert report["caused_by"]["id"] == STALE_ID


def test_demo_poison_recovery(tmp_path):
    db = tmp_path / "brain.db"
    runner = CliRunner()
    result = runner.invoke(cli, ["--db-path", str(db), "demo", "poison-recovery"])
    assert result.exit_code == 0, result.output
    assert "pre-tool-execution" in result.output
    assert "Memory poisoned" in result.output
    assert "REMEDIATED" in result.output

    result_json = runner.invoke(
        cli, ["--db-path", str(db), "demo", "poison-recovery", "--json"]
    )
    assert result_json.exit_code == 0, result_json.output
    payload = json.loads(result_json.output)
    assert payload["ok"] is True
    assert payload["poison_gone"] is True
    assert payload["baseline_ok"] is True
    assert payload["erased"] is True


def test_init_does_not_seed_a_nonempty_db(tmp_path):
    db = tmp_path / "brain.db"
    brain = OMem(db_path=str(db))
    brain.add("already here", namespace="notes")
    brain.brain.write_buffer.flush()
    runner = CliRunner()
    result = runner.invoke(cli, ["--db-path", str(db), "init"])
    assert result.exit_code == 0, result.output
    reopened = OMem(db_path=str(db))
    assert reopened.get(STALE_ID) is None


def test_cursor_merge_keeps_other_servers(tmp_path):
    cursor = tmp_path / "mcp.json"
    cursor.write_text(json.dumps({"mcpServers": {"other": {"command": "echo"}}}), encoding="utf-8")
    block = mcp_config(str(tmp_path / "brain.db"))
    written = merge_cursor_mcp(block, path=str(cursor))
    saved = json.loads(open(written, encoding="utf-8").read())
    assert saved["mcpServers"]["other"]["command"] == "echo"
    assert saved["mcpServers"]["omem"]["args"][0] == "serve"


def test_mcp_lineage_tool(tmp_path, monkeypatch):
    db = tmp_path / "brain.db"
    monkeypatch.setenv("OMEM_DB_PATH", str(db))
    from omem.integrations import mcp_server

    mcp_server.configure_mcp_server(db_path=str(db), namespace="demo", backend="sqlite")
    report = lineage()
    assert report["caused_by"]["id"] == STALE_ID
    assert os.path.exists(db)
