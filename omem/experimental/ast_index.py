"""Alpha Python AST codebase index (opt-in via OMEM_ENABLE_EXPERIMENTAL_AST).

Prefer importing from here in new code::

    from omem.experimental.ast_index import ProjectIngester, ProjectGraph

The implementation still lives under ``omem.knowledge.codebase``; this module
is the supported public entry for Alpha consumers.
"""

from __future__ import annotations

from omem.experimental import require_ast
from omem.knowledge.codebase import (
    CodeRetriever,
    CodeSymbol,
    ProjectGraph,
    ProjectIngester,
    ProjectSync,
    SymbolType,
)

require_ast("omem.experimental.ast_index")

__all__ = [
    "CodeSymbol",
    "SymbolType",
    "ProjectIngester",
    "ProjectGraph",
    "ProjectSync",
    "CodeRetriever",
]
