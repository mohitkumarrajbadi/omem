"""Experimental / Alpha surfaces — not part of the GA enterprise pitch.

Enable explicitly::

    export OMEM_ENABLE_EXPERIMENTAL_AST=1

The Python AST codebase index (``ProjectIngester`` / ``query_code`` / MCP
``ingest_codebase``) lives behind this flag so default runtimes, MCP tool
lists, and CLI help stay focused on governed memory, state, and audit.
"""

from __future__ import annotations

import os
from typing import Final

_TRUTHY: Final = frozenset({"1", "true", "yes", "on"})


def ast_enabled() -> bool:
    """Return True when the experimental AST code index is opted in."""
    raw = os.getenv("OMEM_ENABLE_EXPERIMENTAL_AST", "").strip().lower()
    return raw in _TRUTHY


def require_ast(feature: str = "AST code index") -> None:
    """Raise ``RuntimeError`` when the AST experiment is not enabled."""
    if ast_enabled():
        return
    raise RuntimeError(
        f"{feature} is experimental and disabled by default. "
        "Set OMEM_ENABLE_EXPERIMENTAL_AST=1 to enable, or use "
        "omem.experimental.ast_index explicitly in Alpha deployments."
    )


__all__ = ["ast_enabled", "require_ast"]
