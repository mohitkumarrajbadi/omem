"""Lightweight causal graph for tracking cause-effect relationships."""

from dataclasses import dataclass
from typing import Dict, List, Set


@dataclass
class CausalEdge:
    src: str
    dst: str
    weight: float = 1.0
    label: str = ""


class CausalGraph:
    """Directed graph where nodes are memory IDs and edges are causal links.

    Purely in-memory; stored edges can be serialised alongside memories
    by the backend layer.
    """

    def __init__(self) -> None:
        self._forward: Dict[str, List[CausalEdge]] = {}  # src → [edges]
        self._backward: Dict[str, List[CausalEdge]] = {}  # dst → [edges]

    @property
    def num_edges(self) -> int:
        return sum(len(v) for v in self._forward.values())

    def add_link(
        self, src: str, dst: str, weight: float = 1.0, label: str = ""
    ) -> CausalEdge:
        """Add a directed causal edge ``src → dst``."""
        edge = CausalEdge(src, dst, weight, label)
        self._forward.setdefault(src, []).append(edge)
        self._backward.setdefault(dst, []).append(edge)
        return edge

    def get_effects(self, memory_id: str) -> List[CausalEdge]:
        """Return edges where *memory_id* is the **cause**."""
        return list(self._forward.get(memory_id, []))

    def get_causes(self, memory_id: str) -> List[CausalEdge]:
        """Return edges where *memory_id* is the **effect**."""
        return list(self._backward.get(memory_id, []))

    def neighbours(self, memory_id: str) -> Set[str]:
        """All directly connected memory IDs (both directions)."""
        ids: Set[str] = set()
        for e in self._forward.get(memory_id, []):
            ids.add(e.dst)
        for e in self._backward.get(memory_id, []):
            ids.add(e.src)
        return ids

    def edge_label(self, src: str, dst: str) -> str:
        """Return the label of the edge src → dst, or '' if none exists."""
        for edge in self._forward.get(src, []):
            if edge.dst == dst:
                return edge.label
        for edge in self._backward.get(src, []):
            if edge.src == dst:
                return edge.label
        return ""

    def clear(self) -> None:
        self._forward.clear()
        self._backward.clear()
