"""Project Memory — AST ingestion, code graph, and hybrid code retrieval.

Alpha surface. Prefer ``omem.experimental.ast_index`` and set
``OMEM_ENABLE_EXPERIMENTAL_AST=1`` before using from CLI / MCP / ``OMem`` APIs.
Direct imports of this package remain available for unit tests.
"""

from .graph import ProjectGraph
from .ingester import ProjectIngester
from .retriever import CodeRetriever
from .sync import ProjectSync
from .types import CodeSymbol, SymbolType

__all__ = [
    "CodeSymbol",
    "SymbolType",
    "ProjectIngester",
    "ProjectGraph",
    "ProjectSync",
    "CodeRetriever",
]
