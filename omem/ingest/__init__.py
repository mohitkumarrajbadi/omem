"""Document ingest — chunks + optional frontmatter facts. No LLM."""

from .chunker import chunk_text, extract_text, html_to_text, parse_frontmatter
from .connectors import (
    ConnectorBatchResult,
    SourcePage,
    ingest_drive,
    ingest_folder,
    ingest_notion,
    ingest_pages,
    ingest_url,
    notion_blocks_to_text,
)
from .documents import DocumentIngestResult, remember_document
from .http import StaticTransport, UrllibTransport

__all__ = [
    "chunk_text",
    "extract_text",
    "html_to_text",
    "parse_frontmatter",
    "remember_document",
    "DocumentIngestResult",
    "ConnectorBatchResult",
    "SourcePage",
    "ingest_pages",
    "ingest_folder",
    "ingest_url",
    "ingest_notion",
    "ingest_drive",
    "notion_blocks_to_text",
    "StaticTransport",
    "UrllibTransport",
]
