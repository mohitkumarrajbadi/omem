"""Graph construction utilities for the Project Memory layer.
Creates OMem memories for each :class:`~omem.codebase.types.CodeSymbol` and
establishes hierarchical and dependency edges.
"""

from typing import List

from ..api import OMem
from ..types import MemoryType

from .types import CodeSymbol

class ProjectGraph:
    """Insert symbols into OMem and link them.

    Parameters
    ----------
    omem: OMem
        The core OMem instance (shared across the whole system).
    namespace: str, optional
        Namespace in which project symbols are stored. Defaults to ``"project"``.
    """

    def __init__(self, omem: OMem, namespace: str = "project"):
        self.omem = omem
        self.namespace = namespace

    def _add_symbol(self, sym: CodeSymbol) -> None:
        """Add a single CodeSymbol as a semantic memory.
        The ``metadata`` dict contains the full symbol description and a flag
        ``is_code_symbol`` so downstream tools can recognise it.
        """
        self.omem.add(
            content=sym.to_memory_content(),
            mem_type=MemoryType.SEMANTIC,
            metadata=sym.to_metadata(),
            importance=0.8,  # code structure is generally important
            namespace=self.namespace,
            source="codebase_ingester",
            memory_id=sym.symbol_id,
            force=True,
        )

    def _link(self, src_id: str, dst_id: str, label: str, weight: float = 1.0) -> None:
        """Create a directed edge in the OMem knowledge graph.
        ``label`` describes the relationship (e.g. ``contains``, ``depends_on``).
        """
        self.omem.link(src_id, dst_id, weight=weight, label=label)

    def sync_symbols(self, symbols: List[CodeSymbol]) -> None:
        """Upsert a collection of symbols and create all required edges.
        The method is idempotent – adding the same ``memory_id`` twice simply
        overwrites the existing memory, and duplicate edges are harmless.
        """
        # First add all symbols
        for sym in symbols:
            self._add_symbol(sym)

        # Then create hierarchical edges and dependency edges
        for sym in symbols:
            # Hierarchical containment (parent -> child)
            if sym.parent_id:
                self._link(sym.parent_id, sym.symbol_id, label="contains")
                self._link(sym.symbol_id, sym.parent_id, label="belongs_to")
            # Dependency edges (depends_on and called_by)
            for dep in sym.dependencies:
                # Defensive: ensure dep is a non‑empty string
                if dep:
                    self._link(sym.symbol_id, dep, label="depends_on")
                    self._link(dep, sym.symbol_id, label="called_by")

    # Helper used by sync to cleanup stale symbols – will be called from
    # ProjectSync when a file is deleted.
    def delete_symbol(self, symbol_id: str) -> None:
        try:
            self.omem.delete(symbol_id)
        except Exception:
            # Symbol may already be missing – ignore safely.
            pass
