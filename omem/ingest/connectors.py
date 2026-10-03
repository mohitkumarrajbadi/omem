"""Source connectors that feed ``remember_document``. No LLM extract.

Notion and Google Drive talk REST with a Bearer token. Tests inject
``StaticTransport``. Folder and URL ingest need no third-party SDK.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .chunker import html_to_text
from .documents import DocumentIngestResult, remember_document
from .http import UrllibTransport

_DOC_EXTS = {".md", ".markdown", ".txt", ".html", ".htm", ".pdf"}
_GOOGLE_DOC = "application/vnd.google-apps.document"
_GOOGLE_SHEET = "application/vnd.google-apps.spreadsheet"


@dataclass
class SourcePage:
    title: str
    text: str
    url: str = ""
    source: str = "connector"
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConnectorBatchResult:
    source: str
    pages: int = 0
    chunk_count: int = 0
    fact_count: int = 0
    documents: List[DocumentIngestResult] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "pages": self.pages,
            "chunk_count": self.chunk_count,
            "fact_count": self.fact_count,
            "errors": self.errors,
            "documents": [d.to_dict() for d in self.documents],
        }


def ingest_pages(
    memory_os,
    pages: Iterable[SourcePage],
    *,
    namespace: str = "default",
    max_chars: int = 1200,
    overlap: int = 150,
    importance: float = 0.55,
) -> ConnectorBatchResult:
    """Store connector pages as document chunks. No LLM."""
    result = ConnectorBatchResult(source="pages")
    for page in pages:
        if not (page.text or "").strip():
            continue
        body = page.text
        if page.title and page.title.lower() not in body[:200].lower():
            body = f"# {page.title}\n\n{body}"
        doc = remember_document(
            memory_os,
            body,
            namespace=namespace,
            filename=page.title or page.url or "page.md",
            max_chars=max_chars,
            overlap=overlap,
            importance=importance,
            extra_metadata={
                "connector": page.source,
                "source_url": page.url,
                "title": page.title,
                **page.extra,
            },
        )
        result.documents.append(doc)
        result.pages += 1
        result.chunk_count += doc.chunk_count
        result.fact_count += len(doc.fact_ids)
    return result


def ingest_folder(
    memory_os,
    path: str,
    *,
    namespace: str = "default",
    max_chars: int = 1200,
    overlap: int = 150,
    importance: float = 0.55,
) -> ConnectorBatchResult:
    """Walk a directory of markdown/HTML/PDF/text files."""
    root = Path(path).expanduser().resolve()
    result = ConnectorBatchResult(source="folder")
    if not root.exists():
        result.errors.append(f"missing path: {root}")
        return result
    files: List[Path] = []
    if root.is_file():
        files = [root]
    else:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".") and d not in {"node_modules", ".git"}]
            for name in filenames:
                p = Path(dirpath) / name
                if p.suffix.lower() in _DOC_EXTS:
                    files.append(p)
    for fp in files:
        try:
            doc = remember_document(
                memory_os,
                fp,
                namespace=namespace,
                filename=str(fp.relative_to(root) if root.is_dir() else fp.name),
                max_chars=max_chars,
                overlap=overlap,
                importance=importance,
                extra_metadata={"connector": "folder", "source_url": str(fp)},
            )
            result.documents.append(doc)
            result.pages += 1
            result.chunk_count += doc.chunk_count
            result.fact_count += len(doc.fact_ids)
        except Exception as exc:
            result.errors.append(f"{fp}: {exc}")
    return result


def ingest_url(
    memory_os,
    url: str,
    *,
    namespace: str = "default",
    transport: Any = None,
    headers: Optional[Dict[str, str]] = None,
    max_chars: int = 1200,
    overlap: int = 150,
    importance: float = 0.55,
) -> ConnectorBatchResult:
    """Fetch a URL, strip HTML, and ingest. No LLM."""
    http = transport or UrllibTransport()
    raw = http.get_text(url, headers=headers)
    lower = raw.lstrip()[:200].lower()
    text = html_to_text(raw) if "<html" in lower or "<!doctype" in lower else raw
    title = url.rstrip("/").rsplit("/", 1)[-1] or url
    pages = [SourcePage(title=title, text=text, url=url, source="url")]
    batch = ingest_pages(
        memory_os,
        pages,
        namespace=namespace,
        max_chars=max_chars,
        overlap=overlap,
        importance=importance,
    )
    batch.source = "url"
    return batch


def _rich_text(block: Dict[str, Any], key: str = "rich_text") -> str:
    bits = []
    for run in (block.get(key) or []):
        bits.append(run.get("plain_text") or "")
    return "".join(bits)


def notion_blocks_to_text(blocks: Sequence[Dict[str, Any]]) -> str:
    """Flatten Notion block JSON to markdown-ish text. No LLM."""
    lines: List[str] = []
    for block in blocks:
        btype = block.get("type") or ""
        payload = block.get(btype) or {}
        if btype in ("paragraph", "quote", "callout", "toggle"):
            text = _rich_text(payload)
            if text:
                lines.append(text)
        elif btype == "heading_1":
            lines.append(f"# {_rich_text(payload)}")
        elif btype == "heading_2":
            lines.append(f"## {_rich_text(payload)}")
        elif btype == "heading_3":
            lines.append(f"### {_rich_text(payload)}")
        elif btype == "bulleted_list_item":
            lines.append(f"- {_rich_text(payload)}")
        elif btype == "numbered_list_item":
            lines.append(f"1. {_rich_text(payload)}")
        elif btype == "to_do":
            mark = "x" if payload.get("checked") else " "
            lines.append(f"- [{mark}] {_rich_text(payload)}")
        elif btype == "code":
            lang = payload.get("language") or ""
            lines.append(f"```{lang}\n{_rich_text(payload)}\n```")
        elif btype == "child_page":
            title = (payload.get("title") or "").strip()
            if title:
                lines.append(f"## {title}")
    return "\n\n".join(line for line in lines if line.strip())


def ingest_notion(
    memory_os,
    *,
    token: Optional[str] = None,
    query: str = "",
    namespace: str = "default",
    transport: Any = None,
    max_pages: int = 50,
    max_chars: int = 1200,
    overlap: int = 150,
    importance: float = 0.55,
) -> ConnectorBatchResult:
    """Search Notion pages and ingest block text. Token via arg or NOTION_TOKEN."""
    token = token or os.environ.get("OMEM_NOTION_TOKEN") or os.environ.get("NOTION_TOKEN") or ""
    if not token:
        raise ValueError("Notion token required (OMEM_NOTION_TOKEN / NOTION_TOKEN)")
    http = transport or UrllibTransport()
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    pages: List[SourcePage] = []
    cursor = None
    result = ConnectorBatchResult(source="notion")
    while len(pages) < max_pages:
        body: Dict[str, Any] = {
            "page_size": min(100, max_pages - len(pages)),
            "filter": {"property": "object", "value": "page"},
        }
        if query:
            body["query"] = query
        if cursor:
            body["start_cursor"] = cursor
        try:
            data = http.post_json(
                "https://api.notion.com/v1/search",
                headers=headers,
                json_body=body,
            )
        except Exception as exc:
            result.errors.append(str(exc))
            break
        for item in data.get("results") or []:
            page_id = item.get("id") or ""
            title = _notion_title(item) or page_id
            try:
                blocks = _notion_all_blocks(http, headers, page_id)
            except Exception as exc:
                result.errors.append(f"{page_id}: {exc}")
                continue
            text = notion_blocks_to_text(blocks)
            url = (item.get("url") or f"https://notion.so/{page_id.replace('-', '')}")
            pages.append(
                SourcePage(
                    title=title,
                    text=text or title,
                    url=url,
                    source="notion",
                    extra={"notion_id": page_id},
                )
            )
            if len(pages) >= max_pages:
                break
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
        if not cursor:
            break
    batch = ingest_pages(
        memory_os,
        pages,
        namespace=namespace,
        max_chars=max_chars,
        overlap=overlap,
        importance=importance,
    )
    batch.source = "notion"
    batch.errors.extend(result.errors)
    return batch


def _notion_title(page: Dict[str, Any]) -> str:
    props = page.get("properties") or {}
    for val in props.values():
        if val.get("type") == "title":
            return _rich_text(val, "title")
    return ""


def _notion_all_blocks(http, headers: Dict[str, str], page_id: str) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = []
    cursor = None
    while True:
        params: Dict[str, Any] = {"page_size": 100}
        if cursor:
            params["start_cursor"] = cursor
        data = http.get_json(
            f"https://api.notion.com/v1/blocks/{page_id}/children",
            headers=headers,
            params=params,
        )
        blocks.extend(data.get("results") or [])
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
        if not cursor:
            break
    return blocks


def ingest_drive(
    memory_os,
    *,
    token: Optional[str] = None,
    folder_id: Optional[str] = None,
    namespace: str = "default",
    transport: Any = None,
    max_files: int = 50,
    max_chars: int = 1200,
    overlap: int = 150,
    importance: float = 0.55,
) -> ConnectorBatchResult:
    """List Google Drive files and ingest exported text. Token via OMEM_DRIVE_TOKEN."""
    token = token or os.environ.get("OMEM_DRIVE_TOKEN") or os.environ.get("GOOGLE_DRIVE_TOKEN") or ""
    if not token:
        raise ValueError("Drive token required (OMEM_DRIVE_TOKEN / GOOGLE_DRIVE_TOKEN)")
    http = transport or UrllibTransport()
    headers = {"Authorization": f"Bearer {token}"}
    q = "trashed = false"
    if folder_id:
        q = f"'{folder_id}' in parents and trashed = false"
    result = ConnectorBatchResult(source="drive")
    pages: List[SourcePage] = []
    page_token = None
    while len(pages) < max_files:
        params: Dict[str, Any] = {
            "q": q,
            "pageSize": min(100, max_files - len(pages)),
            "fields": "nextPageToken,files(id,name,mimeType,webViewLink)",
        }
        if page_token:
            params["pageToken"] = page_token
        try:
            data = http.get_json(
                "https://www.googleapis.com/drive/v3/files",
                headers=headers,
                params=params,
            )
        except Exception as exc:
            result.errors.append(str(exc))
            break
        for item in data.get("files") or []:
            fid = item.get("id") or ""
            name = item.get("name") or fid
            mime = item.get("mimeType") or ""
            try:
                text = _drive_file_text(http, headers, fid, mime, name)
            except Exception as exc:
                result.errors.append(f"{name}: {exc}")
                continue
            if not text.strip():
                continue
            pages.append(
                SourcePage(
                    title=name,
                    text=text,
                    url=item.get("webViewLink") or f"https://drive.google.com/file/d/{fid}",
                    source="drive",
                    extra={"drive_id": fid, "mime_type": mime},
                )
            )
            if len(pages) >= max_files:
                break
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    batch = ingest_pages(
        memory_os,
        pages,
        namespace=namespace,
        max_chars=max_chars,
        overlap=overlap,
        importance=importance,
    )
    batch.source = "drive"
    batch.errors.extend(result.errors)
    return batch


def _drive_file_text(http, headers: Dict[str, str], file_id: str, mime: str, name: str) -> str:
    export_mime = None
    if mime == _GOOGLE_DOC:
        export_mime = "text/plain"
    elif mime == _GOOGLE_SHEET:
        export_mime = "text/csv"
    if export_mime:
        return http.get_text(
            f"https://www.googleapis.com/drive/v3/files/{file_id}/export",
            headers=headers,
            params={"mimeType": export_mime},
        )
    lower = name.lower()
    if mime.startswith("text/") or lower.endswith((".md", ".txt", ".html", ".csv")):
        return http.get_text(
            f"https://www.googleapis.com/drive/v3/files/{file_id}",
            headers=headers,
            params={"alt": "media"},
        )
    if mime == "application/pdf" or lower.endswith(".pdf"):
        data = http.get_bytes(
            f"https://www.googleapis.com/drive/v3/files/{file_id}",
            headers=headers,
            params={"alt": "media"},
        )
        from .chunker import pdf_to_text

        return pdf_to_text(data)
    return ""
