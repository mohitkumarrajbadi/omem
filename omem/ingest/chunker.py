"""LLM-free document loading and chunking."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Optional, Tuple, Union

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_HEADING_RE = re.compile(r"(?=^#{1,6}\s)", re.MULTILINE)
_TAG_RE = re.compile(r"<[^>]+>")


def extract_text(
    source: Union[str, bytes, Path],
    *,
    filename: Optional[str] = None,
) -> Tuple[str, str]:
    """Return ``(text, kind)`` where kind is markdown|text|html|pdf.

    ``source`` may be a filesystem path, raw text, or file bytes.
    """
    if isinstance(source, Path) or (
        isinstance(source, str)
        and len(source) < 4096
        and "\n" not in source
        and Path(source).exists()
    ):
        path = Path(source)
        filename = filename or path.name
        data = path.read_bytes()
        return _decode_file(data, filename)

    if isinstance(source, bytes):
        return _decode_file(source, filename or "upload.bin")

    text = str(source)
    kind = "html" if "<html" in text.lower()[:200] else "markdown" if text.lstrip().startswith("#") else "text"
    if kind == "html":
        text = html_to_text(text)
    return text, kind


def _decode_file(data: bytes, filename: str) -> Tuple[str, str]:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return pdf_to_text(data), "pdf"
    raw = data.decode("utf-8", errors="replace")
    if lower.endswith((".html", ".htm")) or raw.lstrip()[:32].lower().startswith("<!doctype") or "<html" in raw[:400].lower():
        return html_to_text(raw), "html"
    if lower.endswith((".md", ".markdown", ".mdx")):
        return raw, "markdown"
    return raw, "text"


def html_to_text(html: str) -> str:
    """Strip tags; keep text order. No external parser required."""
    cleaned = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    cleaned = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", cleaned)
    cleaned = _TAG_RE.sub(" ", cleaned)
    cleaned = re.sub(r"&nbsp;", " ", cleaned)
    cleaned = re.sub(r"&amp;", "&", cleaned)
    cleaned = re.sub(r"&lt;", "<", cleaned)
    cleaned = re.sub(r"&gt;", ">", cleaned)
    return re.sub(r"[ \t]+\n", "\n", re.sub(r"[ \t]{2,}", " ", cleaned)).strip()


def pdf_to_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
        import io

        reader = PdfReader(io.BytesIO(data))
        pages = []
        for page in reader.pages:
            pages.append(page.extract_text() or "")
        return "\n\n".join(pages).strip()
    except ImportError as exc:
        raise ImportError(
            "PDF ingest requires pypdf. Install with: pip install 'omem-os[ingest]'"
        ) from exc


def parse_frontmatter(text: str) -> Tuple[dict, str]:
    """Pull simple ``key: value`` YAML-ish frontmatter. No PyYAML."""
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    meta: dict = {}
    for line in match.group(1).splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        meta[key.strip()] = val.strip().strip("'\"")
    return meta, text[match.end() :]


def chunk_text(
    text: str,
    *,
    max_chars: int = 1200,
    overlap: int = 150,
    kind: str = "text",
) -> List[str]:
    """Split into overlapping chunks. Markdown splits on headings first."""
    text = (text or "").strip()
    if not text:
        return []
    parts = _HEADING_RE.split(text) if kind == "markdown" else [text]
    parts = [p.strip() for p in parts if p and p.strip()]
    if not parts:
        parts = [text]

    chunks: List[str] = []
    buf = ""
    for part in parts:
        if len(part) <= max_chars:
            if buf and len(buf) + 2 + len(part) > max_chars:
                chunks.append(buf.strip())
                buf = (buf[-overlap:] if overlap and len(buf) > overlap else "") + part
            else:
                buf = f"{buf}\n\n{part}".strip() if buf else part
            continue
        if buf:
            chunks.append(buf.strip())
            buf = ""
        chunks.extend(_window(part, max_chars, overlap))
    if buf.strip():
        chunks.append(buf.strip())
    return [c for c in chunks if c]


def _window(text: str, max_chars: int, overlap: int) -> List[str]:
    out: List[str] = []
    start = 0
    n = len(text)
    while start < n:
        end = min(start + max_chars, n)
        if end < n:
            cut = text.rfind("\n", start, end)
            if cut <= start:
                cut = text.rfind(" ", start, end)
            if cut > start:
                end = cut
        out.append(text[start:end].strip())
        if end >= n:
            break
        start = max(end - overlap, start + 1)
    return [c for c in out if c]
