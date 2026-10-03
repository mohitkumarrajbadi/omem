"""Connectors (folder/URL/Notion/Drive) and the no-LLM bakeoff."""

from omem import AgentState, MemoryOS
from omem.ingest.connectors import ingest_drive, ingest_notion, notion_blocks_to_text
from omem.ingest.http import StaticTransport


def test_ingest_folder_markdown(tmp_path, monkeypatch):
    monkeypatch.setenv("OMEM_EMBEDDER", "hash")
    doc = tmp_path / "notes.md"
    doc.write_text(
        "---\ntitle: Oncall\n---\n\n# Runbook\nPage the SRE rotation for SKU-CONN-1.\n",
        encoding="utf-8",
    )
    agent = AgentState(backend="memory")
    try:
        batch = agent.ingest_folder(str(tmp_path))
        assert batch.pages == 1
        assert batch.chunk_count >= 1
        hits = agent.recall("SKU-CONN-1", k=5)
        assert any("SKU-CONN-1" in h.content for h in hits)
        listed = agent.memory.list()
        assert any((m.metadata or {}).get("connector") == "folder" for m in listed)
    finally:
        agent.close()


def test_ingest_url_strips_html(monkeypatch):
    monkeypatch.setenv("OMEM_EMBEDDER", "hash")
    html = "<html><body><h1>Alpha</h1><p>Widget SKU-URL-7 is discontinued.</p></body></html>"
    transport = StaticTransport(text_routes={"https://example.test/a": html})
    mem = MemoryOS(backend="memory")
    batch = mem.ingest_url("https://example.test/a", transport=transport)
    assert batch.pages == 1
    assert batch.chunk_count >= 1
    hits = mem.recall("SKU-URL-7", k=5)
    assert any("SKU-URL-7" in h.content for h in hits)


def test_notion_blocks_to_text():
    blocks = [
        {"type": "heading_1", "heading_1": {"rich_text": [{"plain_text": "Policy"}]}},
        {"type": "paragraph", "paragraph": {"rich_text": [{"plain_text": "Retention is 90 days."}]}},
        {"type": "bulleted_list_item", "bulleted_list_item": {"rich_text": [{"plain_text": "No LLM extract"}]}},
    ]
    text = notion_blocks_to_text(blocks)
    assert "# Policy" in text
    assert "90 days" in text
    assert "No LLM extract" in text


def test_ingest_notion_static_transport(monkeypatch):
    monkeypatch.setenv("OMEM_EMBEDDER", "hash")
    page_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    transport = StaticTransport(
        post_routes={
            "https://api.notion.com/v1/search": {
                "results": [
                    {
                        "id": page_id,
                        "url": "https://notion.so/retention",
                        "properties": {
                            "Name": {
                                "type": "title",
                                "title": [{"plain_text": "Retention"}],
                            }
                        },
                    }
                ],
                "has_more": False,
            }
        },
        json_routes={
            f"https://api.notion.com/v1/blocks/{page_id}/children": {
                "results": [
                    {
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{"plain_text": "Episodic rows expire after ninety unique days."}]
                        },
                    }
                ],
                "has_more": False,
            }
        },
    )
    mem = MemoryOS(backend="memory")
    batch = mem.ingest_notion(token="secret", transport=transport)
    assert batch.pages == 1
    hits = mem.recall("ninety unique days", k=5)
    assert any("ninety unique days" in h.content.lower() for h in hits)


def test_ingest_drive_static_transport(monkeypatch):
    monkeypatch.setenv("OMEM_EMBEDDER", "hash")
    fid = "file-1"
    transport = StaticTransport(
        json_routes={
            "https://www.googleapis.com/drive/v3/files": {
                "files": [
                    {
                        "id": fid,
                        "name": "runbook.md",
                        "mimeType": "text/markdown",
                        "webViewLink": "https://drive.google.com/file/d/file-1",
                    }
                ]
            }
        },
        text_routes={
            f"https://www.googleapis.com/drive/v3/files/{fid}": (
                "On-call alias is pager-CONN-9 for the payments service."
            )
        },
    )
    mem = MemoryOS(backend="memory")
    batch = mem.ingest_drive(token="ya29.token", transport=transport)
    assert batch.pages == 1
    hits = mem.recall("pager-CONN-9", k=5)
    assert any("pager-CONN-9" in h.content for h in hits)


def test_ingest_notion_requires_token():
    mem = MemoryOS(backend="memory")
    try:
        mem.ingest_notion(token="")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "token" in str(exc).lower()


def test_bakeoff_omem_no_llm(monkeypatch):
    monkeypatch.setenv("OMEM_EMBEDDER", "hash")
    from benchmarks.bakeoff import run_omem, CASES

    report = run_omem(CASES, k=5)
    assert report["no_llm"] is True
    assert report["hit_at_k_pct"] >= 50
    by_id = {c["id"]: c for c in report["cases"]}
    assert by_id["exact_sku"]["hit"]
def test_bakeoff_omem_pack_answer_in_budget(monkeypatch):
    monkeypatch.setenv("OMEM_EMBEDDER", "hash")
    from benchmarks.bakeoff import CASES, run_omem_pack

    report = run_omem_pack(CASES, budget_tokens=220)
    assert report["no_llm"] is True
    assert report["answer_in_budget_pct"] >= 50
    by_id = {c["id"]: c for c in report["cases"]}
    assert by_id["exact_sku"]["hit"]
    assert by_id["location_revision"]["hit"]


def test_local_quality_cost_chart_skips_competitors(monkeypatch, tmp_path):
    monkeypatch.setenv("OMEM_EMBEDDER", "hash")
    from benchmarks.bakeoff import render_quality_cost_svg, run_bakeoff

    report = run_bakeoff(include_vector=False)
    by_name = {row["system"]: row for row in report["systems"]}
    for name in ("omem", "omem_pack", "naive_full_history", "summarize_rag"):
        assert by_name[name].get("skipped") is not True
        assert "hit_at_k_pct" in by_name[name]
        assert "mean_prompt_tokens" in by_name[name]
    for name in ("mem0", "zep", "letta", "graphiti"):
        assert by_name[name]["skipped"] is True
        assert "hit_at_k_pct" not in by_name[name]
    svg = render_quality_cost_svg(report)
    assert "naive_full_history" in svg
    assert "summarize_rag" in svg
    assert "mem0" not in svg
    chart = tmp_path / "quality_cost.svg"
    chart.write_text(svg, encoding="utf-8")
    assert chart.stat().st_size > 100


def test_cli_ingest_docs_help():
    from click.testing import CliRunner

    from omem.cli import cli

    result = CliRunner().invoke(cli, ["ingest-docs", "--help"])
    assert result.exit_code == 0
    assert "markdown" in result.output.lower() or "folder" in result.output.lower()
