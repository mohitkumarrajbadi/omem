"""Remember a document as RAG chunks (+ optional frontmatter facts). No LLM."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .chunker import chunk_text, extract_text, parse_frontmatter


@dataclass
class DocumentIngestResult:
    source: str
    kind: str
    chunk_ids: List[str] = field(default_factory=list)
    chunk_count: int = 0
    char_count: int = 0
    frontmatter: Dict[str, Any] = field(default_factory=dict)
    fact_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "kind": self.kind,
            "chunk_ids": self.chunk_ids,
            "chunk_count": self.chunk_count,
            "char_count": self.char_count,
            "frontmatter": self.frontmatter,
            "fact_ids": self.fact_ids,
        }


def remember_document(
    memory_os,
    source: Union[str, bytes, Path],
    *,
    namespace: str = "default",
    filename: Optional[str] = None,
    max_chars: int = 1200,
    overlap: int = 150,
    importance: float = 0.55,
    extra_metadata: Optional[Dict[str, Any]] = None,
) -> DocumentIngestResult:
    """Chunk a document and store each chunk as a memory.

    Markdown ``---`` frontmatter keys are stored as explicit facts
    (``remember`` with a triplet), not LLM-extracted summaries.
    """
    text, kind = extract_text(source, filename=filename)
    meta, body = parse_frontmatter(text) if kind in ("markdown", "text") else ({}, text)
    chunks = chunk_text(body, max_chars=max_chars, overlap=overlap, kind=kind)
    label = filename or (str(source) if isinstance(source, (str, Path)) else "upload")
    result = DocumentIngestResult(
        source=label,
        kind=kind,
        char_count=len(body),
        frontmatter=meta,
    )

    extra = extra_metadata or {}

    for key, val in meta.items():
        if not val:
            continue
        content = f"{key} is {val}"
        mid = memory_os.remember(
            content,
            namespace=namespace,
            importance=min(0.9, importance + 0.2),
            metadata={
                "kind": "document_fact",
                "source_path": label,
                "triplet": ("document", key, val),
                **extra,
            },
            force=True,
        )
        if mid:
            result.fact_ids.append(mid)

    for i, chunk in enumerate(chunks):
        mid = memory_os.remember(
            chunk,
            namespace=namespace,
            importance=importance,
            metadata={
                "kind": "chunk",
                "source_path": label,
                "chunk_index": i,
                "chunk_count": len(chunks),
                "doc_kind": kind,
                **extra,
            },
            force=True,
        )
        if mid:
            result.chunk_ids.append(mid)

    result.chunk_count = len(result.chunk_ids)
    return result
