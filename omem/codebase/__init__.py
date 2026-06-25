"""Deprecated compatibility shim — codebase cognition lives under ``omem.knowledge.codebase``."""

from omem.knowledge.codebase import (
    CodeRetriever,
    CodeSymbol,
    ProjectGraph,
    ProjectIngester,
    ProjectSync,
    SymbolType,
)

__all__ = [
    "CodeSymbol",
    "SymbolType",
    "ProjectIngester",
    "ProjectGraph",
    "ProjectSync",
    "CodeRetriever",
]
