"""TypeScript / JavaScript symbol extraction without tree-sitter or an LLM.

Brace-matched scan for functions, classes, methods, interfaces, and types.
Good enough for SuperMemory-style code chunking with structure.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from .types import CodeSymbol, SymbolType
from .utils import hash_text

_FUNC_RE = re.compile(
    r"(?:export\s+)?(?:default\s+)?(?:async\s+)?function\s*\*?\s+(\w+)\s*\("
)
_CLASS_RE = re.compile(
    r"(?:export\s+)?(?:default\s+)?(?:abstract\s+)?class\s+(\w+)"
)
_INTERFACE_RE = re.compile(r"(?:export\s+)?interface\s+(\w+)")
_TYPE_RE = re.compile(r"(?:export\s+)?type\s+(\w+)\s*=")
_CONST_FN_RE = re.compile(
    r"(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$]\w*)\s*=>"
)
_METHOD_RE = re.compile(
    r"(?:(?:public|private|protected|static|async|get|set|readonly)\s+)*(\w+)\s*\("
)
_SKIP_METHODS = frozenset(
    {
        "if",
        "for",
        "while",
        "switch",
        "catch",
        "function",
        "constructor",
        "return",
        "typeof",
        "switch",
    }
)


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _jsdoc_before(text: str, index: int) -> Optional[str]:
    prefix = text[:index].rstrip()
    if not prefix.endswith("*/"):
        return None
    start = prefix.rfind("/**")
    if start < 0:
        return None
    raw = prefix[start + 3 : -2]
    cleaned = re.sub(r"^\s*\*\s?", "", raw, flags=re.MULTILINE).strip()
    return cleaned or None


def _match_braces(text: str, open_idx: int) -> int:
    """Return index after the matching closing brace, or len(text)."""
    depth = 0
    i = open_idx
    n = len(text)
    in_str = None
    escape = False
    while i < n:
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == in_str:
                in_str = None
            i += 1
            continue
        if ch in ('"', "'", "`"):
            in_str = ch
            i += 1
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return n


def _body_span(text: str, from_idx: int) -> Tuple[int, int]:
    brace = text.find("{", from_idx)
    if brace < 0:
        semi = text.find(";", from_idx)
        end = semi + 1 if semi >= 0 else min(from_idx + 200, len(text))
        return from_idx, end
    return brace, _match_braces(text, brace)


def _symbol(
    *,
    symbol_id: str,
    symbol_type: SymbolType,
    file_path: str,
    name: str,
    start: int,
    end: int,
    parent_id: Optional[str],
    docstring: Optional[str],
    signature: str,
    source: str,
    dependencies: Optional[List[str]] = None,
) -> CodeSymbol:
    return CodeSymbol(
        symbol_id=symbol_id,
        symbol_type=symbol_type,
        file_path=file_path,
        name=name,
        start_line=start,
        end_line=end,
        parent_id=parent_id,
        docstring=docstring,
        signature=signature.strip()[:240],
        content_hash=hash_text(source),
        dependencies=dependencies or [],
    )


def parse_typescript(source: str, file_path: str, module_name: str) -> List[CodeSymbol]:
    """Extract structural symbols from TS/JS source."""
    lines = source.splitlines()
    module = CodeSymbol(
        symbol_id=module_name,
        symbol_type=SymbolType.MODULE,
        file_path=file_path,
        name=module_name,
        start_line=1,
        end_line=max(1, len(lines)),
        parent_id=None,
        docstring=None,
        signature=None,
        content_hash=hash_text(source),
        dependencies=[],
    )
    symbols: List[CodeSymbol] = [module]
    occupied: List[Tuple[int, int]] = []

    def _take(span: Tuple[int, int]) -> bool:
        a, b = span
        for x, y in occupied:
            if a < y and b > x:
                return False
        occupied.append((a, b))
        return True

    # Classes first so methods can be nested without double-counting top-level funcs
    for match in _CLASS_RE.finditer(source):
        name = match.group(1)
        start_i = match.start()
        _, end_i = _body_span(source, match.end())
        if not _take((start_i, end_i)):
            continue
        body = source[start_i:end_i]
        class_id = f"{module_name}.{name}"
        symbols.append(
            _symbol(
                symbol_id=class_id,
                symbol_type=SymbolType.CLASS,
                file_path=file_path,
                name=name,
                start=_line_of(source, start_i),
                end=_line_of(source, end_i),
                parent_id=module_name,
                docstring=_jsdoc_before(source, start_i),
                signature=source[start_i : source.find("{", start_i) or match.end()],
                source=body,
            )
        )
        inner = source[source.find("{", start_i) + 1 : end_i - 1] if "{" in source[start_i:end_i] else ""
        for meth in _METHOD_RE.finditer(inner):
            mname = meth.group(1)
            if mname in _SKIP_METHODS or mname == name:
                continue
            m_abs = (source.find("{", start_i) + 1) + meth.start()
            # skip call-looking matches without a following { or :
            peek = inner[meth.end() - 1 : meth.end() + 40]
            if "{" not in peek and ":" not in peek:
                continue
            m_end_rel = _match_braces(inner, inner.find("{", meth.end())) if "{" in inner[meth.end() :] else meth.end()
            mbody = inner[meth.start() : m_end_rel]
            symbols.append(
                _symbol(
                    symbol_id=f"{class_id}.{mname}",
                    symbol_type=SymbolType.METHOD,
                    file_path=file_path,
                    name=mname,
                    start=_line_of(source, m_abs),
                    end=_line_of(source, m_abs + max(0, m_end_rel - meth.start())),
                    parent_id=class_id,
                    docstring=_jsdoc_before(inner, meth.start()),
                    signature=inner[meth.start() : meth.end() + 1],
                    source=mbody,
                )
            )

    for regex, stype in (
        (_INTERFACE_RE, SymbolType.INTERFACE),
        (_TYPE_RE, SymbolType.TYPE),
        (_FUNC_RE, SymbolType.FUNCTION),
        (_CONST_FN_RE, SymbolType.FUNCTION),
    ):
        for match in regex.finditer(source):
            name = match.group(1)
            start_i = match.start()
            _, end_i = _body_span(source, match.end())
            if stype == SymbolType.TYPE:
                semi = source.find(";", match.end())
                end_i = semi + 1 if 0 <= semi < match.end() + 400 else min(match.end() + 120, len(source))
            if not _take((start_i, end_i)):
                continue
            snippet = source[start_i:end_i]
            symbols.append(
                _symbol(
                    symbol_id=f"{module_name}.{name}",
                    symbol_type=stype,
                    file_path=file_path,
                    name=name,
                    start=_line_of(source, start_i),
                    end=_line_of(source, end_i),
                    parent_id=module_name,
                    docstring=_jsdoc_before(source, start_i),
                    signature=source[start_i : min(start_i + 120, end_i)],
                    source=snippet,
                )
            )

    return symbols
